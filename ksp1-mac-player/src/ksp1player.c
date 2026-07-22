/*
 * KSP 1.00/1.01 desktop player.
 *
 * The SDL/libkss playback layer follows the architecture of the repository's
 * src/kspplayer.c, while all KSP parsing and page construction live in the
 * clean ksp1_runtime module.
 */
#include "ksp1_runtime.h"
#include "ksp1_desktop_bridge.h"
#include "ksp1_channel_control.h"
#include "ksp1_seek_control.h"

#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <conio.h>
#else
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#endif

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wtypedef-redefinition"
#pragma clang diagnostic ignored "-Wstrict-prototypes"
#endif
#include <SDL.h>
#include "kss/kss.h"
#include "kssplay.h"
#include "emu2212/emu2212.h"
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

#define DEFAULT_RATE 44100
#define DEFAULT_CHANNELS 2
#define DEFAULT_FALLBACK_SECONDS 180
#define DEFAULT_FADE_SECONDS 5
#define MAX_RATE 384000
#define MAX_SECONDS 86400
#define KSP1_TRACK_HIDDEN 0x0001u
#define SEEK_RENDER_CHUNK_FRAMES 4096u

static volatile sig_atomic_t g_stop_requested;

typedef struct Options {
    const char *input;
    unsigned song;
    int song_set;
    int rate;
    int channels;
    int seconds;
    int seconds_set;
    int fade_seconds;
    int loops;
    int info_only;
    int validate_only;
} Options;

typedef enum PlayerAction {
    PLAYER_ACTION_NONE = 0,
    PLAYER_ACTION_QUIT,
    PLAYER_ACTION_PREVIOUS,
    PLAYER_ACTION_NEXT,
    PLAYER_ACTION_SEEK_BACKWARD,
    PLAYER_ACTION_SEEK_FORWARD,
    PLAYER_ACTION_SEEK_BACKWARD_LARGE,
    PLAYER_ACTION_SEEK_FORWARD_LARGE,
    PLAYER_ACTION_TOGGLE_CHANNEL_BASE = 100
} PlayerAction;

typedef struct TerminalState {
    int active;
    int escape_state;
    int escape_waits;
#if !defined(_WIN32)
    int original_flags;
    struct termios original_settings;
#endif
} TerminalState;


typedef struct DynamicRuntime {
    KSP1Runtime *runtime;
    KSSPLAY *player;
    const KSP1Engine *engine;
    SCC *secondary_scc;
    uint16_t engine_index;
    uint16_t mailbox_low;
    KSP1DualSccAbi dual_abi;
    int page_switch_enabled;
    int mailbox_low_valid;
    int selected_scc;
    uint32_t primary_scc_mask;
    uint32_t secondary_scc_mask;
    int applying;
    SDL_atomic_t failed;
    char error[256];
} DynamicRuntime;

typedef struct AudioState {
    KSSPLAY *player;
    DynamicRuntime *dynamic;
    uint32_t rate;
    uint8_t channels;
    uint64_t rendered_frames;
    uint64_t fade_start_frame;
    uint64_t end_frame;
    int fade_seconds;
    int loops;
    uint32_t loop_count_base;
    uint16_t song_id;
    int fade_started;
    SDL_atomic_t done;
} AudioState;

static void interrupt_handler(int signal_number) {
    (void)signal_number;
    g_stop_requested = 1;
}

static void usage(FILE *stream, const char *program) {
    fprintf(stream,
        "Usage: %s [options] FILE.ksp\n\n"
        "KSP 1.00/1.01 SDL/libkss player for macOS and other desktop systems.\n\n"
        "Options:\n"
        "  -s N, --song N       Public track index (default: KSP default track)\n"
        "  -p N, --seconds N    Playback seconds; 0 uses track metadata\n"
        "  -f N, --fade N       Fade duration in seconds (default: 5)\n"
        "  -l N, --loops N      Fade after N detected loops; 0 disables\n"
        "  -r N, --rate N       Sample rate (default: 44100)\n"
        "  -n N, --channels N   1 or 2 channels (default: 2)\n"
        "      --info           Show package and track information\n"
        "      --validate       Materialize and validate every page\n"
        "  -h, --help           Show this help\n\n"
        "During playback: Left/Right changes track; Up/Down or [/] seeks 10s; "
        "{/} seeks 60s; 1-5 toggle SCC A; 6-0 toggle SCC B; "
        "Escape or Ctrl-C quits.\n",
        program);
}

static int parse_unsigned(const char *text, unsigned maximum, unsigned *result) {
    char *end = NULL;
    unsigned long value;
    if (!text || !*text) return 0;
    errno = 0;
    value = strtoul(text, &end, 10);
    if (errno == ERANGE || !end || *end || value > maximum) return 0;
    *result = (unsigned)value;
    return 1;
}

static int option_value(int argc, char **argv, int *index, const char *argument,
                        const char *long_name, char short_name, const char **value) {
    size_t long_length = strlen(long_name);
    if (strcmp(argument, long_name) == 0 ||
        (short_name && argument[0] == '-' && argument[1] == short_name && argument[2] == '\0')) {
        if (*index + 1 >= argc) return 0;
        *value = argv[++*index];
        return 1;
    }
    if (strncmp(argument, long_name, long_length) == 0 && argument[long_length] == '=') {
        *value = argument + long_length + 1;
        return **value != '\0';
    }
    if (short_name && argument[0] == '-' && argument[1] == short_name && argument[2] != '\0') {
        *value = argument + 2;
        return 1;
    }
    return -1;
}

static int parse_options(int argc, char **argv, Options *options) {
    int i;
    memset(options, 0, sizeof(*options));
    options->rate = DEFAULT_RATE;
    options->channels = DEFAULT_CHANNELS;
    options->fade_seconds = DEFAULT_FADE_SECONDS;
    options->loops = 1;

    for (i = 1; i < argc; ++i) {
        const char *argument = argv[i];
        const char *value = NULL;
        int matched;
        unsigned number;

        if (argument[0] != '-' || strcmp(argument, "-") == 0) {
            if (options->input) {
                fprintf(stderr, "error: only one input file is supported\n");
                return 0;
            }
            options->input = argument;
            continue;
        }
        if (!strcmp(argument, "-h") || !strcmp(argument, "--help")) {
            usage(stdout, argv[0]);
            exit(0);
        }
        if (!strcmp(argument, "--info")) {
            options->info_only = 1;
            continue;
        }
        if (!strcmp(argument, "--validate")) {
            options->validate_only = 1;
            continue;
        }

#define PARSE_NUMBER(long_name, short_name, max_value, target, set_flag) \
        matched = option_value(argc, argv, &i, argument, long_name, short_name, &value); \
        if (matched != -1) { \
            if (!matched || !parse_unsigned(value, max_value, &number)) { \
                fprintf(stderr, "error: invalid value for %s\n", long_name); \
                return 0; \
            } \
            target = (int)number; \
            set_flag; \
            continue; \
        }
        PARSE_NUMBER("--song", 's', 65535u, options->song, options->song_set = 1)
        PARSE_NUMBER("--seconds", 'p', MAX_SECONDS, options->seconds, options->seconds_set = 1)
        PARSE_NUMBER("--fade", 'f', MAX_SECONDS, options->fade_seconds, (void)0)
        PARSE_NUMBER("--loops", 'l', 65535u, options->loops, (void)0)
        PARSE_NUMBER("--rate", 'r', MAX_RATE, options->rate, (void)0)
        PARSE_NUMBER("--channels", 'n', 2u, options->channels, (void)0)
#undef PARSE_NUMBER

        fprintf(stderr, "error: unknown option: %s\n", argument);
        return 0;
    }

    if (!options->input) {
        fprintf(stderr, "error: no KSP input file specified\n");
        return 0;
    }
    if (options->rate < 8000) {
        fprintf(stderr, "error: sample rate must be at least 8000\n");
        return 0;
    }
    if (options->channels != 1 && options->channels != 2) {
        fprintf(stderr, "error: channels must be 1 or 2\n");
        return 0;
    }
    return 1;
}

static int terminal_prepare(TerminalState *terminal) {
    memset(terminal, 0, sizeof(*terminal));
#if defined(_WIN32)
    terminal->active = 1;
    return 1;
#else
    if (!isatty(STDIN_FILENO)) return 1;
    if (tcgetattr(STDIN_FILENO, &terminal->original_settings) != 0) return 0;
    terminal->original_flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    if (terminal->original_flags < 0) return 0;
    {
        struct termios settings = terminal->original_settings;
        settings.c_lflag &= (tcflag_t)~(ICANON | ECHO);
        settings.c_cc[VMIN] = 0;
        settings.c_cc[VTIME] = 0;
        if (tcsetattr(STDIN_FILENO, TCSANOW, &settings) != 0) return 0;
    }
    if (fcntl(STDIN_FILENO, F_SETFL, terminal->original_flags | O_NONBLOCK) != 0) {
        tcsetattr(STDIN_FILENO, TCSANOW, &terminal->original_settings);
        return 0;
    }
    terminal->active = 1;
    return 1;
#endif
}

static void terminal_restore(TerminalState *terminal) {
#if !defined(_WIN32)
    if (terminal->active) {
        tcsetattr(STDIN_FILENO, TCSANOW, &terminal->original_settings);
        fcntl(STDIN_FILENO, F_SETFL, terminal->original_flags);
    }
#endif
    terminal->active = 0;
}

static PlayerAction seek_action_from_delta(int delta_seconds) {
    if (delta_seconds == -KSP1_SEEK_SMALL_SECONDS)
        return PLAYER_ACTION_SEEK_BACKWARD;
    if (delta_seconds == KSP1_SEEK_SMALL_SECONDS)
        return PLAYER_ACTION_SEEK_FORWARD;
    if (delta_seconds == -KSP1_SEEK_LARGE_SECONDS)
        return PLAYER_ACTION_SEEK_BACKWARD_LARGE;
    if (delta_seconds == KSP1_SEEK_LARGE_SECONDS)
        return PLAYER_ACTION_SEEK_FORWARD_LARGE;
    return PLAYER_ACTION_NONE;
}

static PlayerAction terminal_poll(TerminalState *terminal) {
#if defined(_WIN32)
    while (_kbhit()) {
        int key = _getch();
        int channel = ksp1_channel_index_from_key(key);
        PlayerAction seek_action = seek_action_from_delta(ksp1_seek_delta_from_key(key));
        if (channel >= 0) return (PlayerAction)(PLAYER_ACTION_TOGGLE_CHANNEL_BASE + channel);
        if (seek_action != PLAYER_ACTION_NONE) return seek_action;
        if (key == 27) return PLAYER_ACTION_QUIT;
        if (key == 0 || key == 0xe0) {
            if (!_kbhit()) return PLAYER_ACTION_NONE;
            key = _getch();
            if (key == 72) return PLAYER_ACTION_SEEK_FORWARD;
            if (key == 80) return PLAYER_ACTION_SEEK_BACKWARD;
            if (key == 75) return PLAYER_ACTION_PREVIOUS;
            if (key == 77) return PLAYER_ACTION_NEXT;
        }
    }
    return PLAYER_ACTION_NONE;
#else
    unsigned char input[32];
    ssize_t count;
    size_t i;
    if (!terminal->active) return PLAYER_ACTION_NONE;
    count = read(STDIN_FILENO, input, sizeof(input));
    if (count <= 0) {
        if (terminal->escape_state == 1 && ++terminal->escape_waits >= 2) {
            terminal->escape_state = 0;
            terminal->escape_waits = 0;
            return PLAYER_ACTION_QUIT;
        }
        return PLAYER_ACTION_NONE;
    }
    for (i = 0; i < (size_t)count; ++i) {
        unsigned char key = input[i];
        terminal->escape_waits = 0;
        if (terminal->escape_state == 0) {
            int channel = ksp1_channel_index_from_key(key);
            PlayerAction seek_action = seek_action_from_delta(ksp1_seek_delta_from_key(key));
            if (channel >= 0)
                return (PlayerAction)(PLAYER_ACTION_TOGGLE_CHANNEL_BASE + channel);
            if (seek_action != PLAYER_ACTION_NONE) return seek_action;
            if (key == 0x1b) terminal->escape_state = 1;
            else if (key == 'q' || key == 'Q') return PLAYER_ACTION_QUIT;
        } else if (terminal->escape_state == 1) {
            if (key == '[' || key == 'O') terminal->escape_state = 2;
            else {
                terminal->escape_state = 0;
                return PLAYER_ACTION_QUIT;
            }
        } else {
            terminal->escape_state = 0;
            if (key == 'A') return PLAYER_ACTION_SEEK_FORWARD;
            if (key == 'B') return PLAYER_ACTION_SEEK_BACKWARD;
            if (key == 'C') return PLAYER_ACTION_NEXT;
            if (key == 'D') return PLAYER_ACTION_PREVIOUS;
        }
    }
    return PLAYER_ACTION_NONE;
#endif
}

static int is_scc_write_address(uint32_t address) {
    return address == 0x9000u || address == 0xb000u || address == 0xbffeu ||
           (address >= 0x9800u && address <= 0x98ffu) ||
           (address >= 0xb800u && address <= 0xb8ffu);
}

static void write_secondary_scc(DynamicRuntime *dynamic, uint32_t address, uint32_t data) {
    if (!dynamic->secondary_scc || !is_scc_write_address(address)) return;
    if (address == 0x9000u && data != 0u)
        SCC_write(dynamic->secondary_scc, address, 0x3fu);
    else
        SCC_write(dynamic->secondary_scc, address, data);
    LPDETECT_write(dynamic->player->vm->lpde, address, data);
}

static void set_selected_scc(DynamicRuntime *dynamic, uint32_t selector) {
    if (selector == 0u) dynamic->selected_scc = 0;
    else if (selector == 1u) dynamic->selected_scc = 1;
    else dynamic->selected_scc = -1;

    /* The primary SCC remains libkss's normal SCC. Suppress writes only while
     * SCC B (or no cartridge RAM window) is selected. Both oscillators keep
     * running, exactly as two physical SCC cartridges would. */
    dynamic->player->vm->scc_disable = dynamic->selected_scc == 0 ? 0u : 1u;
}

static void apply_scc_channel_masks(DynamicRuntime *dynamic) {
    if (!dynamic || !dynamic->player) return;
    dynamic->primary_scc_mask &= KSP1_SCC_ALL_CHANNELS_MASK;
    dynamic->secondary_scc_mask &= KSP1_SCC_ALL_CHANNELS_MASK;
    KSSPLAY_set_channel_mask(dynamic->player, KSS_DEVICE_SCC,
                             dynamic->primary_scc_mask);
    if (dynamic->secondary_scc)
        SCC_setMask(dynamic->secondary_scc, dynamic->secondary_scc_mask);
}

static int toggle_scc_channel(DynamicRuntime *dynamic, unsigned channel) {
    if (!dynamic || channel >= KSP1_DUAL_SCC_CHANNEL_COUNT) return 0;
    if (channel < KSP1_SCC_CHANNEL_COUNT) {
        dynamic->primary_scc_mask =
            ksp1_toggle_scc_channel_mask(dynamic->primary_scc_mask, channel);
    } else {
        if (!dynamic->secondary_scc) return 0;
        dynamic->secondary_scc_mask = ksp1_toggle_scc_channel_mask(
            dynamic->secondary_scc_mask, channel - KSP1_SCC_CHANNEL_COUNT);
    }
    apply_scc_channel_masks(dynamic);
    return 1;
}

static void materialize_requested_page(DynamicRuntime *dynamic, uint16_t local_page) {
    uint16_t global_page;
    uint8_t *page = NULL;
    uint32_t begin, end, target;

    if (!dynamic->page_switch_enabled) return;
    if (local_page >= dynamic->engine->page_count) {
        snprintf(dynamic->error, sizeof(dynamic->error),
                 "invalid internal KSP page request %u", (unsigned)local_page);
        SDL_AtomicSet(&dynamic->failed, 1);
        return;
    }
    global_page = (uint16_t)(dynamic->engine->first_page + local_page);
    page = (uint8_t *)malloc(dynamic->engine->page_size);
    if (!page) {
        snprintf(dynamic->error, sizeof(dynamic->error), "out of memory materializing page");
        SDL_AtomicSet(&dynamic->failed, 1);
        return;
    }
    if (!ksp1_materialize_page(dynamic->runtime, global_page, page,
                               dynamic->engine->page_size,
                               dynamic->error, sizeof(dynamic->error))) {
        free(page);
        SDL_AtomicSet(&dynamic->failed, 1);
        return;
    }

    begin = dynamic->engine->replace_start;
    end = (uint32_t)dynamic->engine->load_address + dynamic->engine->page_size;
    if (begin < dynamic->engine->load_address || begin >= end) {
        free(page);
        snprintf(dynamic->error, sizeof(dynamic->error), "invalid dynamic replacement range");
        SDL_AtomicSet(&dynamic->failed, 1);
        return;
    }
    dynamic->applying = 1;
    for (target = begin; target < end; ++target)
        KSSPLAY_write_memory(dynamic->player, target,
                             page[target - dynamic->engine->load_address]);
    dynamic->applying = 0;
    free(page);
}

static void dynamic_memwrite(void *context, uint32_t address, uint32_t data) {
    DynamicRuntime *dynamic = (DynamicRuntime *)context;
    uint16_t local_page;

    if (!dynamic || !dynamic->engine || !dynamic->player || dynamic->applying) return;

    if (dynamic->dual_abi != KSP1_DUAL_SCC_ABI_NONE) {
        if (address == KSP1_SCC_SELECTOR_MAILBOX) {
            set_selected_scc(dynamic, data & 0xffu);
            return;
        }
        if (dynamic->selected_scc == 1 && is_scc_write_address(address)) {
            write_secondary_scc(dynamic, address, data & 0xffu);
            return;
        }
    }

    if (address == KSP1_GATEWAY_MAILBOX_LOW) {
        dynamic->mailbox_low = (uint16_t)(data & 0xffu);
        dynamic->mailbox_low_valid = 1;
        return;
    }
    if (address != KSP1_GATEWAY_MAILBOX_HIGH || !dynamic->mailbox_low_valid) return;

    dynamic->mailbox_low_valid = 0;
    local_page = (uint16_t)(dynamic->mailbox_low | ((data & 0xffu) << 8));
    materialize_requested_page(dynamic, local_page);
}

static void reset_runtime_bridge_state(DynamicRuntime *dynamic) {
    if (!dynamic) return;
    dynamic->mailbox_low = 0u;
    dynamic->mailbox_low_valid = 0;
    dynamic->selected_scc = -1;
    dynamic->applying = 0;
    dynamic->error[0] = '\0';
    SDL_AtomicSet(&dynamic->failed, 0);

    if (dynamic->secondary_scc) {
        SCC_reset(dynamic->secondary_scc);
        SCC_set_quality(dynamic->secondary_scc, 0);
        SCC_set_type(dynamic->secondary_scc, SCC_STANDARD);
        SCC_write(dynamic->secondary_scc, 0x9000u, 0x3fu);
        SCC_setMask(dynamic->secondary_scc, dynamic->secondary_scc_mask);
        if (dynamic->player) dynamic->player->vm->scc_disable = 1u;
    }
}

static int setup_runtime_bridge(DynamicRuntime *dynamic, KSP1Runtime *runtime,
                                KSSPLAY *player, uint16_t engine_index,
                                KSP1DualSccAbi dual_abi, uint32_t rate,
                                char *error, size_t error_size) {
    const KSP1Engine *engine = ksp1_engine(runtime, engine_index);
    memset(dynamic, 0, sizeof(*dynamic));
    if (!engine) {
        snprintf(error, error_size, "invalid engine index");
        return 0;
    }
    dynamic->runtime = runtime;
    dynamic->player = player;
    dynamic->engine = engine;
    dynamic->engine_index = engine_index;
    dynamic->dual_abi = dual_abi;
    dynamic->selected_scc = -1;
    dynamic->primary_scc_mask = 0u;
    dynamic->secondary_scc_mask = 0u;
    dynamic->page_switch_enabled =
        (engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) != 0 ||
        dual_abi == KSP1_DUAL_SCC_ABI_LEGACY_D900_D903;
    SDL_AtomicSet(&dynamic->failed, 0);

    if (dual_abi != KSP1_DUAL_SCC_ABI_NONE) {
        dynamic->secondary_scc = SCC_new(MSX_CLK, rate);
        if (!dynamic->secondary_scc) {
            snprintf(error, error_size, "cannot create secondary SCC emulator");
            return 0;
        }
        KSSPLAY_set_device_type(player, KSS_DEVICE_SCC, VM_SCC_STANDARD);
        KSSPLAY_set_silent_limit(player, 0);
        reset_runtime_bridge_state(dynamic);
    }

    if (dynamic->page_switch_enabled || dual_abi != KSP1_DUAL_SCC_ABI_NONE)
        KSSPLAY_set_memwrite_handler(player, dynamic, dynamic_memwrite);
    return 1;
}

static void destroy_runtime_bridge(DynamicRuntime *dynamic) {
    if (!dynamic) return;
    if (dynamic->player) KSSPLAY_set_memwrite_handler(dynamic->player, NULL, NULL);
    if (dynamic->secondary_scc) SCC_delete(dynamic->secondary_scc);
    dynamic->secondary_scc = NULL;
}

static int16_t soft_compress(int32_t sample) {
    const int32_t threshold = 32768 * 8 / 10;
    if (sample < -threshold) sample = ((sample + threshold) >> 2) - threshold;
    else if (sample > threshold) sample = ((sample - threshold) >> 2) + threshold;
    if (sample < -32767) sample = -32767;
    else if (sample > 32767) sample = 32767;
    return (int16_t)sample;
}

static int32_t apply_secondary_fade(const KSSPLAY *player, int32_t sample) {
    if (player->fade_flag == KSSPLAY_FADE_END) return 0;
    if (player->fade_flag == KSSPLAY_FADE_OUT)
        return (sample * (int32_t)(player->fade >> 23)) >> 8;
    return sample;
}

static void calculate_dual_scc(KSSPLAY *player, DynamicRuntime *dynamic,
                               int16_t *output, uint32_t frames, uint8_t channels) {
    uint32_t frame;
    for (frame = 0; frame < frames; ++frame) {
        int16_t *sample = output + (size_t)frame * channels;
        int32_t secondary;
        KSSPLAY_calc(player, sample, 1);
        secondary = player->device_mute[KSS_DEVICE_SCC] ? 0 : SCC_calc(dynamic->secondary_scc);
        secondary = apply_secondary_fade(player, secondary);
        sample[0] = soft_compress((int32_t)sample[0] + secondary);
        if (channels == 2u)
            sample[1] = soft_compress((int32_t)sample[1] + secondary);
    }
}

static void render_audio_frames(AudioState *state, int16_t *output, uint32_t frames) {
    if (state->dynamic && state->dynamic->secondary_scc)
        calculate_dual_scc(state->player, state->dynamic, output, frames, state->channels);
    else
        KSSPLAY_calc(state->player, output, frames);
}

static int seek_track_state(AudioState *state, uint64_t target_frame,
                            char *error, size_t error_size) {
    int16_t *scratch;
    uint64_t remaining = target_frame;

    if (!state || !state->player || !state->dynamic) {
        snprintf(error, error_size, "invalid playback state for seek");
        return 0;
    }
    if (target_frame == state->rendered_frames) return 1;
    scratch = (int16_t *)malloc((size_t)SEEK_RENDER_CHUNK_FRAMES *
                                state->channels * sizeof(*scratch));
    if (!scratch) {
        snprintf(error, error_size, "out of memory while seeking");
        return 0;
    }

    reset_runtime_bridge_state(state->dynamic);
    KSSPLAY_reset(state->player, state->song_id, 0);
    apply_scc_channel_masks(state->dynamic);
    if (SDL_AtomicGet(&state->dynamic->failed)) {
        snprintf(error, error_size, "%s", state->dynamic->error[0]
                 ? state->dynamic->error : "dynamic page switch failed during seek reset");
        free(scratch);
        return 0;
    }

    while (remaining != 0u) {
        uint32_t chunk = remaining > SEEK_RENDER_CHUNK_FRAMES
            ? SEEK_RENDER_CHUNK_FRAMES : (uint32_t)remaining;
        render_audio_frames(state, scratch, chunk);
        if (SDL_AtomicGet(&state->dynamic->failed)) {
            snprintf(error, error_size, "%s", state->dynamic->error[0]
                     ? state->dynamic->error : "dynamic page switch failed while seeking");
            free(scratch);
            return 0;
        }
        remaining -= chunk;
    }
    free(scratch);

    state->rendered_frames = target_frame;
    state->fade_started = 0;
    state->loop_count_base = (uint32_t)KSSPLAY_get_loop_count(state->player);
    SDL_AtomicSet(&state->done, 0);
    return 1;
}

static void SDLCALL audio_callback(void *userdata, Uint8 *stream, int byte_count) {
    AudioState *state = (AudioState *)userdata;
    int frame_bytes = (int)(sizeof(int16_t) * state->channels);
    uint32_t frames;
    memset(stream, 0, (size_t)byte_count);
    if (!state->player || SDL_AtomicGet(&state->done) || frame_bytes <= 0) return;
    frames = (uint32_t)(byte_count / frame_bytes);
    if (!frames) return;

    render_audio_frames(state, (int16_t *)stream, frames);
    state->rendered_frames += frames;

    if (!state->fade_started) {
        if ((state->loops > 0 &&
             (uint32_t)((uint32_t)KSSPLAY_get_loop_count(state->player) -
                        state->loop_count_base) >= (uint32_t)state->loops) ||
            (state->fade_start_frame && state->rendered_frames >= state->fade_start_frame)) {
            KSSPLAY_fade_start(state->player, (uint32_t)(state->fade_seconds * 1000));
            state->fade_started = 1;
        }
    }
    if ((state->rendered_frames >= (uint64_t)state->rate * 5u &&
         KSSPLAY_get_stop_flag(state->player)) ||
        (state->end_frame && state->rendered_frames >= state->end_frame)) {
        SDL_AtomicSet(&state->done, 1);
    }
}

static unsigned track_duration_seconds(const Options *options, const KSP1Track *track) {
    uint64_t milliseconds;
    if (options->seconds_set && options->seconds > 0)
        return (unsigned)options->seconds;
    if (track && track->duration_ms != 0xffffffffu && track->duration_ms != 0)
        milliseconds = track->duration_ms;
    else
        milliseconds = (uint64_t)DEFAULT_FALLBACK_SECONDS * 1000u;
    return (unsigned)((milliseconds + 999u) / 1000u);
}

static uint64_t rendered_frames_snapshot(SDL_AudioDeviceID device,
                                         const AudioState *state) {
    uint64_t frames;
    SDL_LockAudioDevice(device);
    frames = state->rendered_frames;
    SDL_UnlockAudioDevice(device);
    return frames;
}

static void print_playback_status(SDL_AudioDeviceID device,
                                  const AudioState *state,
                                  const DynamicRuntime *dynamic,
                                  unsigned total_seconds,
                                  unsigned *last_second,
                                  int force) {
    char channels[128];
    uint64_t frames = rendered_frames_snapshot(device, state);
    unsigned elapsed = state->rate ? (unsigned)(frames / state->rate) : 0u;
    unsigned elapsed_minutes;
    unsigned elapsed_remainder;
    unsigned total_minutes;
    unsigned total_remainder;

    if (!force && *last_second == elapsed) return;
    *last_second = elapsed;
    elapsed_minutes = elapsed / 60u;
    elapsed_remainder = elapsed % 60u;
    total_minutes = total_seconds / 60u;
    total_remainder = total_seconds % 60u;
    ksp1_format_scc_channel_status(channels, sizeof(channels),
                                   dynamic->primary_scc_mask,
                                   dynamic->secondary_scc_mask,
                                   dynamic->secondary_scc != NULL);
    printf("\r\033[2K%02u:%02u / %02u:%02u  %s",
           elapsed_minutes, elapsed_remainder,
           total_minutes, total_remainder, channels);
    fflush(stdout);
}

static void print_info(KSP1Runtime *runtime, const char *path) {
    const KSP1Header *header = ksp1_header(runtime);
    uint16_t i;
    printf("KSP 1.%02u: %s\n", header->minor_version, path);
    printf("engines=%u pages=%u tracks=%u resources=%u default=%u\n",
           header->engine_count, header->page_count, header->track_count,
           header->resource_count, header->default_track);
    for (i = 0; i < header->engine_count; ++i) {
        const KSP1Engine *engine = ksp1_engine(runtime, i);
        const char *name = ksp1_string(runtime, engine->name_offset);
        printf("engine %u: %s load=$%04X size=%u init=$%04X play=$%04X "
               "stop=$%04X tick=%u hw=$%08X pages=%u\n",
               i, name ? name : "(unnamed)", engine->load_address,
               engine->page_size, engine->init_address, engine->play_address,
               engine->stop_address, engine->tick_hz, engine->hardware_flags,
               engine->page_count);
    }
    for (i = 0; i < header->track_count; ++i) {
        const KSP1Track *track = ksp1_track(runtime, i);
        const KSP1Page *page = ksp1_page(runtime, track->page_index);
        const char *title = ksp1_string(runtime, track->title_offset);
        printf("%5u page=%u enc=%u song=%u duration=",
               i, track->page_index, page ? page->encoding : 255u, track->song_id);
        if (track->duration_ms == 0xffffffffu) printf("unknown");
        else printf("%.3fs", track->duration_ms / 1000.0);
        printf("%s%s\n", (track->flags & KSP1_TRACK_HIDDEN) ? " hidden " : " ",
               title ? title : "");
    }
}

static uint16_t owning_engine(KSP1Runtime *runtime, const KSP1Track *track) {
    const KSP1Page *page = ksp1_page(runtime, track->page_index);
    return page ? page->engine_index : KSP1_NO_INDEX;
}

static PlayerAction play_track(KSP1Runtime *runtime, const Options *options,
                               uint16_t public_track, TerminalState *terminal,
                               char *error, size_t error_size) {
    const KSP1Track *track = ksp1_track(runtime, public_track);
    const KSP1Engine *engine;
    const char *title;
    uint8_t *image = NULL;
    uint32_t image_size = 0;
    KSS *kss = NULL;
    KSSPLAY *player = NULL;
    SDL_AudioDeviceID device = 0;
    SDL_AudioSpec desired;
    SDL_AudioSpec obtained;
    AudioState state;
    DynamicRuntime dynamic;
    unsigned seconds;
    unsigned last_status_second = UINT_MAX;
    PlayerAction action = PLAYER_ACTION_NONE;
    KSP1DualSccAbi dual_abi = KSP1_DUAL_SCC_ABI_NONE;
    uint16_t engine_index;

    if (!track) {
        snprintf(error, error_size, "track %u is unavailable", public_track);
        return PLAYER_ACTION_QUIT;
    }
    engine_index = owning_engine(runtime, track);
    engine = ksp1_engine(runtime, engine_index);
    if (!engine) {
        snprintf(error, error_size, "track %u has an invalid engine", public_track);
        return PLAYER_ACTION_QUIT;
    }
    if (!ksp1_build_kscc_image(runtime, public_track, &image, &image_size,
                               error, error_size))
        return PLAYER_ACTION_QUIT;
    dual_abi = ksp1_detect_dual_scc_abi(engine, image + 16u, image_size - 16u);
    if (!ksp1_prepare_kscc_bridge_image(&image, &image_size, engine, dual_abi,
                                   error, error_size)) {
        free(image);
        return PLAYER_ACTION_QUIT;
    }

    kss = KSS_bin2kss(image, image_size, (char *)options->input);
    free(image);
    image = NULL;
    if (!kss) {
        snprintf(error, error_size, "libkss rejected the reconstructed KSCC image");
        return PLAYER_ACTION_QUIT;
    }

    player = KSSPLAY_new((uint32_t)options->rate, (uint32_t)options->channels, 16);
    if (!player) {
        snprintf(error, error_size, "cannot create libkss player");
        KSS_delete(kss);
        return PLAYER_ACTION_QUIT;
    }
    if (KSSPLAY_set_data(player, kss) != 0) {
        snprintf(error, error_size, "cannot attach reconstructed KSS data");
        KSSPLAY_delete(player);
        KSS_delete(kss);
        return PLAYER_ACTION_QUIT;
    }
    if (!setup_runtime_bridge(&dynamic, runtime, player, engine_index, dual_abi,
                              (uint32_t)options->rate, error, error_size)) {
        destroy_runtime_bridge(&dynamic);
        KSSPLAY_delete(player);
        KSS_delete(kss);
        return PLAYER_ACTION_QUIT;
    }
    KSSPLAY_reset(player, track->song_id, 0);
    apply_scc_channel_masks(&dynamic);

    memset(&state, 0, sizeof(state));
    state.player = player;
    state.dynamic = &dynamic;
    state.rate = (uint32_t)options->rate;
    state.channels = (uint8_t)options->channels;
    state.fade_seconds = options->fade_seconds;
    state.loops = options->loops;
    state.song_id = track->song_id;
    state.loop_count_base = (uint32_t)KSSPLAY_get_loop_count(player);
    seconds = track_duration_seconds(options, track);
    state.end_frame = (uint64_t)seconds * state.rate;
    if (seconds > (unsigned)options->fade_seconds)
        state.fade_start_frame = (uint64_t)(seconds - (unsigned)options->fade_seconds) * state.rate;
    SDL_AtomicSet(&state.done, 0);

    memset(&desired, 0, sizeof(desired));
    desired.freq = options->rate;
    desired.format = AUDIO_S16SYS;
    desired.channels = (Uint8)options->channels;
    desired.samples = 1024;
    desired.callback = audio_callback;
    desired.userdata = &state;
    device = SDL_OpenAudioDevice(NULL, 0, &desired, &obtained, 0);
    if (!device) {
        snprintf(error, error_size, "cannot open SDL audio device: %s", SDL_GetError());
        destroy_runtime_bridge(&dynamic);
        KSSPLAY_delete(player);
        KSS_delete(kss);
        return PLAYER_ACTION_QUIT;
    }

    title = ksp1_string(runtime, track->title_offset);
    printf("Playing %u/%u: %s  [%u Hz, %u channel%s, %us%s]\n",
           public_track, ksp1_header(runtime)->track_count - 1u,
           title ? title : "(untitled)", state.rate, state.channels,
           state.channels == 1 ? "" : "s", seconds,
           dual_abi == KSP1_DUAL_SCC_ABI_NONE ? "" :
           (dual_abi == KSP1_DUAL_SCC_ABI_KSP1 ? ", dual SCC" : ", legacy dual SCC"));
    if (terminal->active) {
        printf("Controls: Left/Right track, Up/Down or [/] seek 10s, "
               "{/} seek 60s, 1-5 SCC A, 6-0 SCC B, Esc/q quit\n");
        fflush(stdout);
    }
    SDL_PauseAudioDevice(device, 0);
    if (terminal->active)
        print_playback_status(device, &state, &dynamic, seconds,
                              &last_status_second, 1);

    while (!g_stop_requested && !SDL_AtomicGet(&state.done)) {
        PlayerAction polled = terminal_poll(terminal);
        if (polled >= PLAYER_ACTION_TOGGLE_CHANNEL_BASE &&
            polled < PLAYER_ACTION_TOGGLE_CHANNEL_BASE +
                     (int)KSP1_DUAL_SCC_CHANNEL_COUNT) {
            unsigned channel = (unsigned)(polled - PLAYER_ACTION_TOGGLE_CHANNEL_BASE);
            SDL_LockAudioDevice(device);
            (void)toggle_scc_channel(&dynamic, channel);
            SDL_UnlockAudioDevice(device);
            if (terminal->active)
                print_playback_status(device, &state, &dynamic, seconds,
                                      &last_status_second, 1);
        } else if (polled == PLAYER_ACTION_SEEK_BACKWARD ||
                   polled == PLAYER_ACTION_SEEK_FORWARD ||
                   polled == PLAYER_ACTION_SEEK_BACKWARD_LARGE ||
                   polled == PLAYER_ACTION_SEEK_FORWARD_LARGE) {
            int delta_seconds;
            uint64_t target_frame;
            unsigned target_seconds;
            int seek_ok;

            if (polled == PLAYER_ACTION_SEEK_BACKWARD)
                delta_seconds = -KSP1_SEEK_SMALL_SECONDS;
            else if (polled == PLAYER_ACTION_SEEK_FORWARD)
                delta_seconds = KSP1_SEEK_SMALL_SECONDS;
            else if (polled == PLAYER_ACTION_SEEK_BACKWARD_LARGE)
                delta_seconds = -KSP1_SEEK_LARGE_SECONDS;
            else
                delta_seconds = KSP1_SEEK_LARGE_SECONDS;

            SDL_LockAudioDevice(device);
            target_frame = ksp1_seek_target_frame(state.rendered_frames,
                                                  delta_seconds, state.rate,
                                                  state.end_frame);
            target_seconds = state.rate
                ? (unsigned)(target_frame / state.rate) : 0u;
            if (terminal->active) {
                printf("\r\033[2KSeeking to %02u:%02u...",
                       target_seconds / 60u, target_seconds % 60u);
                fflush(stdout);
            }
            seek_ok = seek_track_state(&state, target_frame, error, error_size);
            SDL_UnlockAudioDevice(device);
            if (!seek_ok) {
                action = PLAYER_ACTION_QUIT;
                break;
            }
            if (terminal->active)
                print_playback_status(device, &state, &dynamic, seconds,
                                      &last_status_second, 1);
        } else if (polled != PLAYER_ACTION_NONE) {
            action = polled;
            break;
        }
        if (SDL_AtomicGet(&dynamic.failed)) {
            snprintf(error, error_size, "%s", dynamic.error[0] ? dynamic.error : "dynamic page switch failed");
            action = PLAYER_ACTION_QUIT;
            break;
        }
        if (terminal->active)
            print_playback_status(device, &state, &dynamic, seconds,
                                  &last_status_second, 0);
        SDL_Delay(20);
    }
    if (g_stop_requested) action = PLAYER_ACTION_QUIT;
    if (terminal->active) {
        print_playback_status(device, &state, &dynamic, seconds,
                              &last_status_second, 1);
        putchar('\n');
        fflush(stdout);
    }

    SDL_PauseAudioDevice(device, 1);
    SDL_CloseAudioDevice(device);
    destroy_runtime_bridge(&dynamic);
    KSSPLAY_delete(player);
    KSS_delete(kss);
    return action;
}

static int find_visible_track(KSP1Runtime *runtime, uint16_t current, int direction,
                              uint16_t *result) {
    const KSP1Header *header = ksp1_header(runtime);
    uint32_t attempts;
    uint32_t index = current;
    if (!header->track_count) return 0;
    for (attempts = 0; attempts < header->track_count; ++attempts) {
        if (direction > 0) index = (index + 1u) % header->track_count;
        else index = index ? index - 1u : header->track_count - 1u;
        if (!(ksp1_track(runtime, (uint16_t)index)->flags & KSP1_TRACK_HIDDEN)) {
            *result = (uint16_t)index;
            return 1;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    Options options;
    KSP1Runtime *runtime = NULL;
    const KSP1Header *header;
    TerminalState terminal;
    uint16_t track;
    char error[512] = {0};
    int exit_code = 1;
    void (*previous_interrupt_handler)(int);

    if (!parse_options(argc, argv, &options)) {
        usage(stderr, argv[0]);
        return 2;
    }
    runtime = ksp1_open(options.input, error, sizeof(error));
    if (!runtime) {
        fprintf(stderr, "error: %s\n", error);
        return 1;
    }
    header = ksp1_header(runtime);
    if (!header->track_count) {
        fprintf(stderr, "error: package has no tracks\n");
        goto cleanup;
    }
    if (options.info_only) {
        print_info(runtime, options.input);
        exit_code = 0;
        goto cleanup;
    }
    if (options.validate_only) {
        if (!ksp1_validate_all_pages(runtime, error, sizeof(error))) {
            fprintf(stderr, "error: %s\n", error);
            goto cleanup;
        }
        printf("validated %u pages and %u tracks\n", header->page_count, header->track_count);
        exit_code = 0;
        goto cleanup;
    }

    track = options.song_set ? (uint16_t)options.song : header->default_track;
    if (track == KSP1_NO_INDEX || track >= header->track_count) track = 0;
    if (!terminal_prepare(&terminal))
        fprintf(stderr, "warning: interactive key handling is unavailable\n");

    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "error: cannot initialize SDL audio: %s\n", SDL_GetError());
        terminal_restore(&terminal);
        goto cleanup;
    }
    g_stop_requested = 0;
    previous_interrupt_handler = signal(SIGINT, interrupt_handler);
    for (;;) {
        PlayerAction action;
        error[0] = '\0';
        action = play_track(runtime, &options, track, &terminal, error, sizeof(error));
        if (error[0]) {
            fprintf(stderr, "error: %s\n", error);
            exit_code = 1;
            break;
        }
        if (action == PLAYER_ACTION_NEXT) {
            if (!find_visible_track(runtime, track, 1, &track)) break;
            continue;
        }
        if (action == PLAYER_ACTION_PREVIOUS) {
            if (!find_visible_track(runtime, track, -1, &track)) break;
            continue;
        }
        exit_code = 0;
        break;
    }
    if (previous_interrupt_handler != SIG_ERR)
        signal(SIGINT, previous_interrupt_handler);
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
    terminal_restore(&terminal);

cleanup:
    ksp1_close(runtime);
    return exit_code;
}
