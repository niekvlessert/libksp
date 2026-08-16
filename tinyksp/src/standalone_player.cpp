#include "ksp_vm.h"
#include "kss_vm.h"
#include "playback_trace.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#if defined(_WIN32) || defined(TINYKSP_TEST_WINDOWS)
#define TINYKSP_WINDOWS 1
#endif

#if defined(__APPLE__) && !defined(TINYKSP_TEST_WINDOWS)
#define TINYKSP_MACOS 1
#include "native_audio_macos.h"
#endif

#ifdef TINYKSP_WINDOWS
#include <conio.h>
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#else
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;
#ifndef TINYKSP_VERSION
#define TINYKSP_VERSION "1.9.9"
#endif
namespace {
constexpr const char* PROGRAM_VERSION = TINYKSP_VERSION;
constexpr uint32_t SAMPLE_RATE = 44100;
constexpr uint32_t CHANNELS_PER_PAGE = 10;
constexpr uint32_t SEEK_SECONDS = 10;
constexpr int KEY_LEFT = 0x100;
constexpr int KEY_RIGHT = 0x101;
std::atomic<bool> interrupted{false};

void signalHandler(int) { interrupted.store(true); }

void enableAnsiTerminal() {
#ifdef TINYKSP_WINDOWS
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    if (output == INVALID_HANDLE_VALUE) return;
    DWORD mode = 0;
    if (!GetConsoleMode(output, &mode)) return;
    SetConsoleMode(output, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
#endif
}

#ifndef TINYKSP_MACOS
bool commandExists(const char* name) {
#ifdef TINYKSP_WINDOWS
    std::string command = "where ";
    command += name;
    command += " >NUL 2>&1";
#else
    std::string command = "command -v ";
    command += name;
    command += " >/dev/null 2>&1";
#endif
    return std::system(command.c_str()) == 0;
}
#endif

std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

bool isKsp(const fs::path& path) {
    std::error_code ec;
    return fs::is_regular_file(path, ec) && !ec && lower(path.extension().string()) == ".ksp";
}

bool isKssPath(const fs::path& path) {
    const std::string ext = lower(path.extension().string());
    return ext == ".kss" || ext == ".kssx";
}

bool containsWildcard(const std::string& value) {
    return value.find('*') != std::string::npos || value.find('?') != std::string::npos;
}

bool wildcardMatch(const std::string& pattern_value, const std::string& name_value) {
    const std::string pattern = lower(pattern_value);
    const std::string name = lower(name_value);
    size_t pattern_pos = 0;
    size_t name_pos = 0;
    size_t star_pos = std::string::npos;
    size_t star_match = 0;

    while (name_pos < name.size()) {
        if (pattern_pos < pattern.size() &&
            (pattern[pattern_pos] == '?' || pattern[pattern_pos] == name[name_pos])) {
            ++pattern_pos;
            ++name_pos;
            continue;
        }
        if (pattern_pos < pattern.size() && pattern[pattern_pos] == '*') {
            star_pos = pattern_pos++;
            star_match = name_pos;
            continue;
        }
        if (star_pos != std::string::npos) {
            pattern_pos = star_pos + 1;
            name_pos = ++star_match;
            continue;
        }
        return false;
    }
    while (pattern_pos < pattern.size() && pattern[pattern_pos] == '*') ++pattern_pos;
    return pattern_pos == pattern.size();
}

std::vector<fs::path> expandKspArguments(const std::vector<std::string>& arguments,
                                         bool& used_wildcard, std::string& error) {
    std::vector<fs::path> files;
    std::vector<std::string> seen;
    used_wildcard = false;

    auto appendUnique = [&](const fs::path& path) {
        std::error_code ec;
        fs::path normalized = fs::absolute(path, ec);
        if (ec) normalized = path;
        normalized = normalized.lexically_normal();
        std::string key = normalized.generic_string();
#ifdef TINYKSP_WINDOWS
        key = lower(key);
#endif
        if (std::find(seen.begin(), seen.end(), key) != seen.end()) return;
        seen.push_back(std::move(key));
        files.push_back(path);
    };

    for (const std::string& argument : arguments) {
        if (!containsWildcard(argument)) {
            appendUnique(fs::path(argument));
            continue;
        }
        used_wildcard = true;
        const fs::path pattern_path(argument);
        const fs::path parent = pattern_path.has_parent_path()
            ? pattern_path.parent_path() : fs::current_path();
        if (containsWildcard(parent.string())) {
            error = "wildcards in directory names are not supported: " + argument;
            return {};
        }

        std::error_code ec;
        if (!fs::is_directory(parent, ec) || ec) {
            error = "wildcard directory does not exist: " + parent.string();
            return {};
        }
        std::vector<fs::path> matches;
        const std::string filename_pattern = pattern_path.filename().string();
        for (fs::directory_iterator it(parent, fs::directory_options::skip_permission_denied, ec), end;
             it != end; it.increment(ec)) {
            if (ec) {
                ec.clear();
                continue;
            }
            const fs::path candidate = it->path();
            if (!isKsp(candidate)) continue;
            if (wildcardMatch(filename_pattern, candidate.filename().string()))
                matches.push_back(candidate);
        }
        std::sort(matches.begin(), matches.end(), [](const fs::path& a, const fs::path& b) {
            return lower(a.filename().string()) < lower(b.filename().string());
        });
        if (matches.empty()) {
            error = "wildcard matched no KSP files: " + argument;
            return {};
        }
        for (const fs::path& match : matches) appendUnique(match);
    }
    return files;
}

std::vector<fs::path> findKspFiles() {
    std::vector<fs::path> files;
    std::vector<fs::path> roots;
    const char* home = std::getenv("HOME");
#ifdef TINYKSP_WINDOWS
    if (!home) home = std::getenv("USERPROFILE");
#endif
    if (home) {
        roots.emplace_back(fs::path(home) / "storage" / "downloads"); // Termux
        roots.emplace_back(fs::path(home) / "Downloads");              // macOS/Windows/Linux
        roots.emplace_back(fs::path(home) / "downloads");              // Linux variants
    }
#ifndef TINYKSP_WINDOWS
    roots.emplace_back("/sdcard/Download");
#endif
    roots.emplace_back(fs::current_path());

    for (const auto& root : roots) {
        std::error_code ec;
        if (!fs::is_directory(root, ec)) continue;
        fs::recursive_directory_iterator it(
            root, fs::directory_options::skip_permission_denied, ec), end;
        while (it != end) {
            if (ec) {
                ec.clear();
                it.increment(ec);
                continue;
            }
            if (it.depth() > 3) it.disable_recursion_pending();
            if (isKsp(it->path())) files.push_back(it->path());
            it.increment(ec);
        }
    }
    std::sort(files.begin(), files.end(), [](const auto& a, const auto& b) {
        return lower(a.filename().string()) < lower(b.filename().string());
    });
    files.erase(std::unique(files.begin(), files.end()), files.end());
    return files;
}

fs::path findYrw801Rom(const fs::path& ksp, const fs::path& explicit_path) {
    std::vector<fs::path> candidates;
    if (!explicit_path.empty()) candidates.push_back(explicit_path);
    if (const char* env = std::getenv("TINYKSP_YRW801_ROM")) candidates.emplace_back(env);
    candidates.push_back(ksp.parent_path() / "yrw801.rom");
    candidates.push_back(fs::current_path() / "yrw801.rom");
    if (const char* home = std::getenv("HOME")) {
        candidates.emplace_back(fs::path(home) / "storage" / "downloads" / "yrw801.rom");
        candidates.emplace_back(fs::path(home) / "Downloads" / "yrw801.rom");
    }
    for (const auto& candidate : candidates) {
        std::error_code ec;
        if (!candidate.empty() && fs::is_regular_file(candidate, ec) && !ec) return candidate;
    }
    return {};
}

int chooseIndex(const std::string& prompt, int count) {
    while (true) {
        std::cout << prompt << " [1-" << count << ", 0=quit]: " << std::flush;
        std::string line;
        if (!std::getline(std::cin, line)) return -1;
        try {
            size_t used = 0;
            const int value = std::stoi(line, &used);
            if (used == line.size() && value == 0) return -1;
            if (used == line.size() && value >= 1 && value <= count) return value - 1;
        } catch (...) {
        }
        std::cout << "Invalid selection.\n";
    }
}

std::string formatSeconds(uint64_t seconds) {
    std::ostringstream out;
    const uint64_t hours = seconds / 3600;
    const uint64_t minutes = (seconds / 60) % 60;
    const uint64_t secs = seconds % 60;
    if (hours) out << hours << ':' << std::setfill('0') << std::setw(2) << minutes << ':';
    else out << std::setfill('0') << std::setw(2) << minutes << ':';
    out << std::setfill('0') << std::setw(2) << secs;
    return out.str();
}

std::string humanSize(uint64_t bytes) {
    std::ostringstream out;
    if (bytes < 1024) return std::to_string(bytes) + " bytes";
    const double kib = static_cast<double>(bytes) / 1024.0;
    if (kib < 1024.0) {
        out << std::fixed << std::setprecision(kib < 10.0 ? 1 : 0) << kib << " KiB";
    } else {
        const double mib = kib / 1024.0;
        out << std::fixed << std::setprecision(mib < 10.0 ? 2 : 1) << mib << " MiB";
    }
    return out.str();
}

void clearStatusLine() {
    std::cout << "\r\033[2K" << std::flush;
}

void printPackageInfo(const tinyksp::KspVm& vm, const fs::path& file) {
    std::cout << "\nPackage information\n"
              << "-------------------\n"
              << "File: " << file.filename().string() << '\n'
              << "KSP version: 1." << std::setfill('0') << std::setw(2) << vm.minorVersion()
              << std::setfill(' ') << '\n'
              << "File size: " << humanSize(vm.fileSize()) << '\n'
              << "Tracks: " << vm.visibleTrackCount() << " visible / " << vm.trackCount() << " total\n"
              << "Engines: " << vm.engineCount() << " | Pages: " << vm.pageCount()
              << " | Resources: " << vm.resourceCount() << '\n'
              << "Default public track: " << static_cast<unsigned>(vm.defaultTrack()) + 1 << '\n'
              << "Cover image: " << (vm.coverResource() == 0xffff ? "none" : "present") << '\n';

    const auto metadata = vm.generalMetadata();
    std::cout << "Hardware variants: "
              << (vm.hasHardwareVariants() ? "HVAR/HVR1 present" : "none") << '\n';
    std::cout << "\nGeneral META fields:\n";
    if (metadata.empty()) {
        std::cout << "  (none)\n";
    } else {
        for (const auto& entry : metadata)
            std::cout << "  " << entry.key << ": " << entry.value << '\n';
    }
    if (!vm.metadataWarnings().empty()) {
        std::cout << "\nMetadata warnings:\n";
        for (const auto& warning : vm.metadataWarnings())
            std::cout << "  " << warning << '\n';
    }

    std::cout << "\nEngine profiles:\n";
    const auto engines = vm.engineSummaries();
    for (size_t i = 0; i < engines.size(); ++i)
        std::cout << "  " << i + 1 << ". " << engines[i] << '\n';
    std::cout << '\n';
}

void writeLe16(std::ofstream& out, uint16_t value) {
    const char b[2] = {static_cast<char>(value), static_cast<char>(value >> 8)};
    out.write(b, 2);
}

void writeLe32(std::ofstream& out, uint32_t value) {
    const char b[4] = {static_cast<char>(value), static_cast<char>(value >> 8),
                       static_cast<char>(value >> 16), static_cast<char>(value >> 24)};
    out.write(b, 4);
}

class TerminalInput {
public:
    TerminalInput() {
#ifdef TINYKSP_WINDOWS
        active_ = _isatty(_fileno(stdin)) != 0;
#else
        if (!isatty(STDIN_FILENO)) return;
        if (tcgetattr(STDIN_FILENO, &original_term_) != 0) return;
        original_flags_ = fcntl(STDIN_FILENO, F_GETFL, 0);
        if (original_flags_ < 0) return;
        termios current = original_term_;
        current.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO));
        current.c_cc[VMIN] = 0;
        current.c_cc[VTIME] = 0;
        if (tcsetattr(STDIN_FILENO, TCSANOW, &current) != 0) return;
        if (fcntl(STDIN_FILENO, F_SETFL, original_flags_ | O_NONBLOCK) != 0) {
            tcsetattr(STDIN_FILENO, TCSANOW, &original_term_);
            return;
        }
        active_ = true;
#endif
    }

    ~TerminalInput() {
#ifndef TINYKSP_WINDOWS
        if (!active_) return;
        fcntl(STDIN_FILENO, F_SETFL, original_flags_);
        tcsetattr(STDIN_FILENO, TCSANOW, &original_term_);
#endif
    }

    int readKey() {
        if (!active_) return -1;
#ifdef TINYKSP_WINDOWS
        if (!_kbhit()) return -1;
        const int value = _getch();
        if (value == 0 || value == 224) {
            const int extended = _getch();
            if (extended == 75) return KEY_LEFT;
            if (extended == 77) return KEY_RIGHT;
            return -1;
        }
        return value;
#else
        unsigned char bytes[64];
        for (;;) {
            const ssize_t count = ::read(STDIN_FILENO, bytes, sizeof(bytes));
            if (count <= 0) break;
            const auto now = std::chrono::steady_clock::now();
            for (ssize_t i = 0; i < count; ++i) feedByte(bytes[i], now);
        }

        const auto now = std::chrono::steady_clock::now();
        if (escape_state_ != 0 &&
            now - escape_started_ >= std::chrono::milliseconds(180)) {
            if (escape_state_ == 1) decoded_.push_back(27);
            escape_state_ = 0;
            escape_sequence_.clear();
        }
        if (decoded_.empty()) return -1;
        const int value = decoded_.front();
        decoded_.pop_front();
        return value;
#endif
    }

    bool active() const { return active_; }

private:
#ifndef TINYKSP_WINDOWS
    void feedByte(unsigned char value, std::chrono::steady_clock::time_point now) {
        if (escape_state_ == 0) {
            if (value == 27) {
                escape_state_ = 1;
                escape_started_ = now;
            } else {
                decoded_.push_back(value);
            }
            return;
        }

        if (escape_state_ == 1) {
            if (value == '[' || value == 'O') {
                escape_state_ = 2;
                escape_sequence_.clear();
                return;
            }
            decoded_.push_back(27);
            escape_state_ = 0;
            escape_sequence_.clear();
            feedByte(value, now);
            return;
        }

        // CSI/SS3 sequences can contain parameters, for example ESC [ 1 ; 2 C.
        // Consume the complete sequence and classify only its final byte.
        escape_sequence_.push_back(static_cast<char>(value));
        const bool final_byte = value >= 0x40 && value <= 0x7e;
        if (!final_byte && escape_sequence_.size() <= 32) return;
        if (final_byte) {
            if (value == 'D') decoded_.push_back(KEY_LEFT);
            else if (value == 'C') decoded_.push_back(KEY_RIGHT);
        }
        escape_state_ = 0;
        escape_sequence_.clear();
    }

    termios original_term_{};
    int original_flags_ = 0;
    int escape_state_ = 0;
    std::chrono::steady_clock::time_point escape_started_{};
    std::string escape_sequence_;
    std::deque<int> decoded_;
#endif
    bool active_ = false;
};

void printChannelPage(const tinyksp::KspVm& vm, int page) {
    const int count = vm.channelCount();
    if (count <= 0) return;
    const int pages = std::max(1, (count + static_cast<int>(CHANNELS_PER_PAGE) - 1) /
                                  static_cast<int>(CHANNELS_PER_PAGE));
    page = std::clamp(page, 0, pages - 1);
    clearStatusLine();
    std::cout << "Channels " << page + 1 << '/' << pages << ": ";
    const int start = page * static_cast<int>(CHANNELS_PER_PAGE);
    const int end = std::min(count, start + static_cast<int>(CHANNELS_PER_PAGE));
    for (int index = start; index < end; ++index) {
        const int slot = index - start;
        const char key = slot == 9 ? '0' : static_cast<char>('1' + slot);
        if (index != start) std::cout << " | ";
        std::cout << key << '=' << vm.channelName(index)
                  << (vm.channelMuted(index) ? " [MUTED]" : " [on]");
    }
    std::cout << "\n";
}

void printProgress(const tinyksp::KspVm& vm, uint64_t elapsed_frames,
                   uint64_t total_frames, int page, bool interactive,
                   int track = -1, int track_count = 0) {
    const uint64_t elapsed = elapsed_frames / SAMPLE_RATE;
    const uint64_t total = total_frames / SAMPLE_RATE;
    const int channels = vm.channelCount();
    const int pages = std::max(1, (channels + static_cast<int>(CHANNELS_PER_PAGE) - 1) /
                                  static_cast<int>(CHANNELS_PER_PAGE));
    int muted = 0;
    for (int i = 0; i < channels; ++i) if (vm.channelMuted(i)) ++muted;
    clearStatusLine();
    // Keep the live status within a normal terminal width. The full title is
    // printed when a track starts; repeating it here makes wrapped terminal
    // lines accumulate because clearing one physical line cannot erase all
    // rows occupied by a long status message.
    if (track >= 0 && track_count > 0) {
        if (interactive)
            std::cout << "Track " << track + 1 << '/' << track_count << " | ";
        else
            std::cout << "Track " << track + 1 << '/' << track_count << ": "
                      << vm.visibleTrackTitle(track) << " | ";
    }
    std::cout << formatSeconds(elapsed) << " / " << formatSeconds(total)
              << " | " << vm.activeHardwareName();
    if (channels) std::cout << " | page " << page + 1 << '/' << pages
                            << " | muted " << muted;
    std::cout << std::flush;
}

bool renderWav(tinyksp::KspVm& vm, const fs::path& output, uint32_t seconds,
               std::string& error) {
    const uint64_t frames_total = static_cast<uint64_t>(seconds) * SAMPLE_RATE;
    const uint64_t data_size64 = frames_total * 4;
    if (data_size64 > std::numeric_limits<uint32_t>::max()) {
        error = "WAV output exceeds RIFF size limit";
        return false;
    }
    const uint32_t data_size = static_cast<uint32_t>(data_size64);
    std::ofstream out(output, std::ios::binary);
    if (!out) {
        error = "cannot create WAV output";
        return false;
    }
    out.write("RIFF", 4);
    writeLe32(out, 36 + data_size);
    out.write("WAVE", 4);
    out.write("fmt ", 4);
    writeLe32(out, 16);
    writeLe16(out, 1);
    writeLe16(out, 2);
    writeLe32(out, SAMPLE_RATE);
    writeLe32(out, SAMPLE_RATE * 4);
    writeLe16(out, 4);
    writeLe16(out, 16);
    out.write("data", 4);
    writeLe32(out, data_size);

    std::vector<int16_t> buffer(2048 * 2);
    uint64_t rendered = 0;
    uint64_t last_second = std::numeric_limits<uint64_t>::max();
    while (rendered < frames_total && !interrupted.load()) {
        const uint32_t frames = static_cast<uint32_t>(
            std::min<uint64_t>(frames_total - rendered, 2048));
        if (!vm.render(buffer.data(), frames, error)) return false;
        out.write(reinterpret_cast<const char*>(buffer.data()),
                  static_cast<std::streamsize>(frames * 4));
        if (!out) {
            error = "WAV write failed";
            return false;
        }
        rendered += frames;
        const uint64_t current_second = rendered / SAMPLE_RATE;
        if (current_second != last_second) {
            printProgress(vm, rendered, frames_total, 0, false);
            last_second = current_second;
        }
    }
    clearStatusLine();
    std::cout << formatSeconds(rendered / SAMPLE_RATE) << " rendered.\n";
    return true;
}

#ifndef TINYKSP_MACOS
FILE* openMpvPipe() {
    const char* command =
        "mpv --no-config --terminal=no --input-terminal=no --no-video --really-quiet "
        "--cache=no --demuxer-readahead-secs=0 --audio-buffer=0.05 "
        "--demuxer=rawaudio --demuxer-rawaudio-rate=44100 "
        "--demuxer-rawaudio-channels=stereo --demuxer-rawaudio-format=s16le -";
#ifdef TINYKSP_WINDOWS
    FILE* pipe = _popen(command, "wb");
    if (pipe) _setmode(_fileno(pipe), _O_BINARY);
    return pipe;
#else
    return popen(command, "w");
#endif
}

int closeMpvPipe(FILE* pipe) {
#ifdef TINYKSP_WINDOWS
    return _pclose(pipe);
#else
    return pclose(pipe);
#endif
}
#endif

int findVariantForHardware(const tinyksp::KspVm& vm, int track, uint32_t hardware) {
    const int count = vm.playbackVariantCount(track);
    for (int index = 0; index < count; ++index) {
        if (vm.playbackVariantHardware(track, index) == hardware) return index;
    }
    return count > 0 ? 0 : -1;
}

int findPreviousPlayableTrack(const tinyksp::KspVm& vm, int current) {
    for (int candidate = current - 1; candidate >= 0; --candidate) {
        if (vm.playbackVariantCount(candidate) > 0) return candidate;
    }
    return -1;
}

int findFirstPlayableTrack(const tinyksp::KspVm& vm, int start = 0) {
    const int count = vm.visibleTrackCount();
    for (int candidate = std::max(0, start); candidate < count; ++candidate) {
        if (vm.playbackVariantCount(candidate) > 0) return candidate;
    }
    return -1;
}

int findNextPlayableTrack(const tinyksp::KspVm& vm, int current) {
    return findFirstPlayableTrack(vm, current + 1);
}

bool packageUsesHardware(const tinyksp::KspVm& vm, uint32_t hardware) {
    for (int track = 0; track < vm.visibleTrackCount(); ++track) {
        for (int variant = 0; variant < vm.playbackVariantCount(track); ++variant) {
            if (vm.playbackVariantHardware(track, variant) & hardware) return true;
        }
    }
    return false;
}

std::vector<bool> captureMuteState(const tinyksp::KspVm& vm) {
    std::vector<bool> result(static_cast<size_t>(std::max(0, vm.channelCount())), false);
    for (int channel = 0; channel < vm.channelCount(); ++channel)
        result[static_cast<size_t>(channel)] = vm.channelMuted(channel);
    return result;
}

void restoreMuteState(tinyksp::KspVm& vm, const std::vector<bool>& muted) {
    const int count = std::min(vm.channelCount(), static_cast<int>(muted.size()));
    for (int channel = 0; channel < count; ++channel) {
        if (!muted[static_cast<size_t>(channel)]) continue;
        bool now_muted = false;
        vm.toggleChannelMute(channel, now_muted);
    }
}

bool seekVm(tinyksp::KspVm& vm, int track, int variant, uint64_t target_frames,
            const std::vector<bool>& muted, std::string& error) {
    if (!vm.start(track, variant, error)) return false;

    std::vector<int16_t> discard(4096 * 2);
    uint64_t advanced = 0;
    while (advanced < target_frames) {
        const uint32_t frames = static_cast<uint32_t>(
            std::min<uint64_t>(target_frames - advanced, discard.size() / 2));
        if (!vm.render(discard.data(), frames, error)) return false;
        advanced += frames;
    }
    restoreMuteState(vm, muted);
    return true;
}

#ifndef TINYKSP_MACOS
bool reopenMpvPipe(FILE*& pipe, std::string& error) {
    if (pipe) {
        closeMpvPipe(pipe);
        pipe = nullptr;
    }
    pipe = openMpvPipe();
    if (!pipe) {
        error = "cannot relaunch mpv after seek or track switch";
        return false;
    }
    return true;
}
#endif

enum class PlaybackResult {
    Finished,
    NextFile,
    Stopped,
    Failed,
};

PlaybackResult playLive(tinyksp::KspVm& vm, int& track, int& variant,
                        uint32_t seconds_override, bool has_next_file,
                        std::string& error) {
#ifdef TINYKSP_MACOS
    tinyksp::MacAudioOutput audio;
    if (!audio.start(error)) return PlaybackResult::Failed;
    auto close_output = [&]() { audio.stop(); };
    auto reopen_output = [&](std::string& output_error) {
        return audio.restart(output_error);
    };
    auto write_output = [&](const int16_t* data, uint32_t frames,
                            std::string& output_error) {
        return audio.write(data, frames, output_error);
    };
    auto drain_output = [&](std::string& output_error) {
        return audio.drain(output_error);
    };
#else
    FILE* pipe = openMpvPipe();
    if (!pipe) {
        error = "cannot launch mpv";
        return PlaybackResult::Failed;
    }
    auto close_output = [&]() { closeMpvPipe(pipe); };
    auto reopen_output = [&](std::string& output_error) {
        return reopenMpvPipe(pipe, output_error);
    };
    auto write_output = [&](const int16_t* data, uint32_t frames,
                            std::string& output_error) {
        if (fwrite(data, sizeof(int16_t) * 2, frames, pipe) == frames) return true;
        if (!interrupted.load()) output_error = "mpv closed the audio pipe";
        return false;
    };
    auto drain_output = [&](std::string&) { return true; };
#endif

    TerminalInput terminal;
    std::vector<int16_t> buffer(512 * 2);
    uint32_t current_seconds = seconds_override
        ? seconds_override : vm.suggestedSeconds(track, variant);
    uint64_t total_frames = static_cast<uint64_t>(current_seconds) * SAMPLE_RATE;
    uint64_t rendered = 0;
    uint64_t last_display_bucket = std::numeric_limits<uint64_t>::max();
    int channel_page = 0;
    int page_count = std::max(1, (vm.channelCount() + static_cast<int>(CHANNELS_PER_PAGE) - 1) /
                                  static_cast<int>(CHANNELS_PER_PAGE));
    if (terminal.active()) printChannelPage(vm, channel_page);

    while (true) {
        bool ok = true;
        bool stop_requested = false;
        while (rendered < total_frames && !interrupted.load() && !stop_requested) {
            const uint32_t frames = static_cast<uint32_t>(
                std::min<uint64_t>(total_frames - rendered, buffer.size() / 2));
            if (!vm.render(buffer.data(), frames, error)) {
                ok = false;
                break;
            }
            if (!write_output(buffer.data(), frames, error)) {
                if (!interrupted.load()) ok = false;
                break;
            }
            rendered += frames;

            for (int key = terminal.readKey(); key >= 0; key = terminal.readKey()) {
                if (key == '<' || key == '>') {
                    const bool forward = key == '>';
                    const uint64_t step = static_cast<uint64_t>(SEEK_SECONDS) * SAMPLE_RATE;
                    const uint64_t target = forward
                        ? std::min(total_frames, rendered + step)
                        : (rendered > step ? rendered - step : 0);
                    if (target == rendered) continue;

                    const auto muted = captureMuteState(vm);
                    clearStatusLine();
                    std::cout << "Seeking to " << formatSeconds(target / SAMPLE_RATE) << "..." << std::flush;
                    if (!reopen_output(error)) {
                        ok = false;
                        stop_requested = true;
                        break;
                    }
                    if (!seekVm(vm, track, variant, target, muted, error)) {
                        error = "seek failed: " + error;
                        ok = false;
                        stop_requested = true;
                        break;
                    }
                    rendered = target;
                    last_display_bucket = std::numeric_limits<uint64_t>::max();
                    clearStatusLine();
                    std::cout << "Seek: " << formatSeconds(rendered / SAMPLE_RATE) << '\n';
                    if (terminal.active()) printChannelPage(vm, channel_page);
                    continue;
                }
                if (key == KEY_LEFT || key == KEY_RIGHT) {
                    const int target_track = key == KEY_RIGHT
                        ? findNextPlayableTrack(vm, track)
                        : findPreviousPlayableTrack(vm, track);
                    if (target_track < 0) {
                        if (key == KEY_RIGHT && has_next_file) {
                            clearStatusLine();
                            std::cout << "Skipping to next KSP file.\n";
                            close_output();
                            return PlaybackResult::NextFile;
                        }
                        continue;
                    }
                    const uint32_t preferred_hardware = vm.activeHardware();
                    const int target_variant = findVariantForHardware(
                        vm, target_track, preferred_hardware);
                    if (target_variant < 0) continue;

                    std::string switch_error;
                    if (!reopen_output(switch_error)) {
                        error = "track switch failed: " + switch_error;
                        ok = false;
                        stop_requested = true;
                        break;
                    }
                    if (!vm.start(target_track, target_variant, switch_error)) {
                        error = "track switch failed: " + switch_error;
                        ok = false;
                        stop_requested = true;
                        break;
                    }
                    track = target_track;
                    variant = target_variant;
                    current_seconds = seconds_override
                        ? seconds_override : vm.suggestedSeconds(track, variant);
                    total_frames = static_cast<uint64_t>(current_seconds) * SAMPLE_RATE;
                    rendered = 0;
                    last_display_bucket = std::numeric_limits<uint64_t>::max();
                    channel_page = 0;
                    page_count = std::max(
                        1, (vm.channelCount() + static_cast<int>(CHANNELS_PER_PAGE) - 1) /
                               static_cast<int>(CHANNELS_PER_PAGE));
                    clearStatusLine();
                    std::cout << "Now playing track " << track + 1 << '/'
                              << vm.visibleTrackCount() << ": " << vm.visibleTrackTitle(track) << '\n'
                              << "Playback type: " << vm.playbackVariantName(track, variant) << '\n';
                    if (terminal.active()) printChannelPage(vm, channel_page);
                    continue;
                }
                if (key == 'q' || key == 'Q' || key == 27) {
                    stop_requested = true;
                    break;
                }
                if (key == '\t' || key == 'n' || key == 'N' || key == ']') {
                    channel_page = (channel_page + 1) % page_count;
                    printChannelPage(vm, channel_page);
                    continue;
                }
                if (key == 'p' || key == 'P' || key == '[') {
                    channel_page = (channel_page + page_count - 1) % page_count;
                    printChannelPage(vm, channel_page);
                    continue;
                }
                if (key == 'u' || key == 'U') {
                    vm.unmuteAllChannels();
                    printChannelPage(vm, channel_page);
                    continue;
                }
                int slot = -1;
                if (key >= '1' && key <= '9') slot = key - '1';
                else if (key == '0') slot = 9;
                if (slot >= 0) {
                    const int channel = channel_page * static_cast<int>(CHANNELS_PER_PAGE) + slot;
                    bool now_muted = false;
                    if (vm.toggleChannelMute(channel, now_muted)) printChannelPage(vm, channel_page);
                }
            }

            const uint64_t display_bucket = rendered / (SAMPLE_RATE / 5);
            if (display_bucket != last_display_bucket) {
                printProgress(vm, rendered, total_frames, channel_page, terminal.active(),
                              track, vm.visibleTrackCount());
                last_display_bucket = display_bucket;
            }
        }

        clearStatusLine();
        if (!ok) {
            close_output();
            return PlaybackResult::Failed;
        }
        if (stop_requested || interrupted.load()) {
            std::cout << "Track " << track + 1 << ": " << formatSeconds(rendered / SAMPLE_RATE)
                      << " stopped.\n";
            close_output();
            return PlaybackResult::Stopped;
        }

        std::cout << "Track " << track + 1 << ": " << formatSeconds(rendered / SAMPLE_RATE)
                  << " finished.\n";
        const int next_track = findNextPlayableTrack(vm, track);
        if (next_track < 0) {
            if (!drain_output(error)) {
                close_output();
                return PlaybackResult::Failed;
            }
            close_output();
            return PlaybackResult::Finished;
        }

        const uint32_t preferred_hardware = vm.activeHardware();
        const int next_variant = findVariantForHardware(vm, next_track, preferred_hardware);
        if (next_variant < 0 || !vm.start(next_track, next_variant, error)) {
            if (error.empty()) error = "next track has no supported playback type";
            else error = "next track start failed: " + error;
            close_output();
            return PlaybackResult::Failed;
        }
        track = next_track;
        variant = next_variant;
        current_seconds = seconds_override
            ? seconds_override : vm.suggestedSeconds(track, variant);
        total_frames = static_cast<uint64_t>(current_seconds) * SAMPLE_RATE;
        rendered = 0;
        last_display_bucket = std::numeric_limits<uint64_t>::max();
        channel_page = 0;
        page_count = std::max(
            1, (vm.channelCount() + static_cast<int>(CHANNELS_PER_PAGE) - 1) /
                   static_cast<int>(CHANNELS_PER_PAGE));
        std::cout << "Now playing track " << track + 1 << '/'
                  << vm.visibleTrackCount() << ": " << vm.visibleTrackTitle(track) << '\n'
                  << "Playback type: " << vm.playbackVariantName(track, variant) << '\n';
        if (terminal.active()) printChannelPage(vm, channel_page);
    }
}


bool renderKssWav(tinyksp::KssVm& vm, const fs::path& output, uint32_t seconds,
                  std::string& error) {
    const uint64_t frames_total = static_cast<uint64_t>(seconds) * SAMPLE_RATE;
    const uint64_t data_size64 = frames_total * 4;
    if (data_size64 > std::numeric_limits<uint32_t>::max()) {
        error = "WAV output exceeds RIFF size limit";
        return false;
    }
    std::ofstream out(output, std::ios::binary);
    if (!out) { error = "cannot create WAV output"; return false; }
    const uint32_t data_size = static_cast<uint32_t>(data_size64);
    out.write("RIFF", 4); writeLe32(out, 36 + data_size); out.write("WAVE", 4);
    out.write("fmt ", 4); writeLe32(out, 16); writeLe16(out, 1); writeLe16(out, 2);
    writeLe32(out, SAMPLE_RATE); writeLe32(out, SAMPLE_RATE * 4); writeLe16(out, 4); writeLe16(out, 16);
    out.write("data", 4); writeLe32(out, data_size);
    std::vector<int16_t> buffer(2048 * 2);
    uint64_t rendered = 0;
    while (rendered < frames_total && !interrupted.load()) {
        const uint32_t frames = static_cast<uint32_t>(std::min<uint64_t>(2048, frames_total - rendered));
        if (!vm.render(buffer.data(), frames, error)) return false;
        out.write(reinterpret_cast<const char*>(buffer.data()), static_cast<std::streamsize>(frames * 4));
        if (!out) { error = "WAV write failed"; return false; }
        rendered += frames;
    }
    return true;
}

bool playKssLive(tinyksp::KssVm& vm, uint32_t seconds, std::string& error) {
#ifdef TINYKSP_MACOS
    tinyksp::MacAudioOutput audio;
    if (!audio.start(error)) return false;
    auto close_output = [&]() { audio.stop(); };
    auto write_output = [&](const int16_t* data, uint32_t frames) { return audio.write(data, frames, error); };
#else
    FILE* pipe = openMpvPipe();
    if (!pipe) { error = "cannot launch mpv"; return false; }
    auto close_output = [&]() { closeMpvPipe(pipe); };
    auto write_output = [&](const int16_t* data, uint32_t frames) {
        if (fwrite(data, sizeof(int16_t) * 2, frames, pipe) == frames) return true;
        if (!interrupted.load()) error = "mpv closed the audio pipe";
        return false;
    };
#endif
    TerminalInput terminal;
    std::vector<int16_t> buffer(512 * 2);
    const uint64_t total = static_cast<uint64_t>(seconds) * SAMPLE_RATE;
    uint64_t rendered = 0;
    while (rendered < total && !interrupted.load()) {
        const uint32_t frames = static_cast<uint32_t>(std::min<uint64_t>(buffer.size() / 2, total - rendered));
        if (!vm.render(buffer.data(), frames, error) || !write_output(buffer.data(), frames)) {
            close_output();
            return false;
        }
        rendered += frames;
        for (int key = terminal.readKey(); key >= 0; key = terminal.readKey()) {
            if (key == 'q' || key == 'Q' || key == 27) { close_output(); return true; }
            if (key == 'u' || key == 'U') vm.unmuteAllChannels();
            int slot = -1;
            if (key >= '1' && key <= '9') slot = key - '1'; else if (key == '0') slot = 9;
            if (slot >= 0) { bool muted = false; vm.toggleChannelMute(slot, muted); }
        }
        if ((rendered % (SAMPLE_RATE / 5)) < frames) {
            clearStatusLine();
            std::cout << formatSeconds(rendered / SAMPLE_RATE) << " / " << formatSeconds(seconds)
                      << " | " << vm.hardwareDescription() << std::flush;
        }
    }
    clearStatusLine();
    close_output();
    return true;
}

void printTraceEvent(const char* side, const tinyksp::TraceEvent* e) {
    std::cout << "  " << side << ": ";
    if (!e) { std::cout << "<no event>\n"; return; }
    std::cout << tinyksp::tracePhaseName(e->phase);
    if (e->phase == tinyksp::TracePhase::Play) std::cout << " tick " << e->tick;
    std::cout << " | " << tinyksp::traceDeviceName(e->device)
              << " $" << std::hex << std::setw(4) << std::setfill('0') << e->address
              << " = $" << std::setw(2) << static_cast<unsigned>(e->value)
              << std::dec << std::setfill(' ') << "\n";
}

int runCompare(const fs::path& ksp_path, const fs::path& kss_path, int track,
               int variant, bool variant_explicit, uint32_t seconds) {
    std::string error;
    tinyksp::KspVm ksp(SAMPLE_RATE);
    tinyksp::KssVm kss(SAMPLE_RATE);
    if (!ksp.open(ksp_path.string(), error)) { std::cerr << "KSP open failed: " << error << "\n"; return 1; }
    if (!kss.open(kss_path.string(), error)) { std::cerr << "KSS open failed: " << error << "\n"; return 1; }
    if (track < 0 || track >= ksp.visibleTrackCount()) {
        std::cerr << "Track outside KSP visible range 1.." << ksp.visibleTrackCount() << ".\n"; return 2;
    }
    const int variant_count = ksp.playbackVariantCount(track);
    if (variant_count <= 0) { std::cerr << "KSP track has no supported playback variant.\n"; return 1; }
    if (!variant_explicit) variant = 0;
    if (variant < 0 || variant >= variant_count) { std::cerr << "Playback variant outside range.\n"; return 2; }

    const uint32_t kss_song32 = kss.hasDeclaredSongRange()
        ? static_cast<uint32_t>(kss.firstSong()) + static_cast<uint32_t>(track)
        : static_cast<uint32_t>(track);
    if (kss_song32 > 0xffffu || (kss.hasDeclaredSongRange() && kss_song32 > kss.lastSong())) {
        std::cerr << "Track outside declared KSS track range.\n";
        return 2;
    }
    const uint16_t kss_song = static_cast<uint16_t>(kss_song32);

    ksp.enableTrace(true);
    kss.enableTrace(true);
    if (!ksp.start(track, variant, error)) { std::cerr << "KSP start failed: " << error << "\n"; return 1; }
    if (!kss.start(kss_song, error)) { std::cerr << "KSS start failed: " << error << "\n"; return 1; }

    const uint32_t compare_seconds = seconds ? seconds : 10;
    const uint64_t total_frames = static_cast<uint64_t>(compare_seconds) * SAMPLE_RATE;
    std::vector<int16_t> ksp_pcm, kss_pcm;
    ksp_pcm.reserve(static_cast<size_t>(total_frames * 2));
    kss_pcm.reserve(static_cast<size_t>(total_frames * 2));
    std::vector<int16_t> a(2048 * 2), b(2048 * 2);
    uint64_t done = 0;
    while (done < total_frames) {
        const uint32_t frames = static_cast<uint32_t>(std::min<uint64_t>(2048, total_frames - done));
        if (!ksp.render(a.data(), frames, error)) { std::cerr << "KSP compare render failed: " << error << "\n"; return 1; }
        if (!kss.render(b.data(), frames, error)) { std::cerr << "KSS compare render failed: " << error << "\n"; return 1; }
        ksp_pcm.insert(ksp_pcm.end(), a.begin(), a.begin() + static_cast<ptrdiff_t>(frames * 2));
        kss_pcm.insert(kss_pcm.end(), b.begin(), b.begin() + static_cast<ptrdiff_t>(frames * 2));
        done += frames;
    }

    const auto& kt = ksp.trace();
    const auto& st = kss.trace();
    const size_t common_events = std::min(kt.size(), st.size());
    size_t first_event_diff = common_events;
    for (size_t i = 0; i < common_events; ++i) if (!(kt[i] == st[i])) { first_event_diff = i; break; }
    const bool trace_identical = first_event_diff == common_events && kt.size() == st.size();

    size_t first_pcm_diff = ksp_pcm.size();
    uint32_t max_delta = 0;
    uint64_t pcm_diff_count = 0;
    for (size_t i = 0; i < ksp_pcm.size(); ++i) {
        const uint32_t delta = static_cast<uint32_t>(std::abs(static_cast<int>(ksp_pcm[i]) - static_cast<int>(kss_pcm[i])));
        if (delta) { if (first_pcm_diff == ksp_pcm.size()) first_pcm_diff = i; ++pcm_diff_count; max_delta = std::max(max_delta, delta); }
    }
    const bool pcm_identical = pcm_diff_count == 0;
    const bool identical = trace_identical && pcm_identical;

    std::cout << "\nKSP/KSS comparison\n------------------\n"
              << "Track: " << track + 1 << " (KSS song " << kss_song << ")\n"
              << "Duration: " << compare_seconds << " s\n"
              << "KSP: " << ksp_path.filename().string() << "\n"
              << "KSS: " << kss_path.filename().string() << "\n"
              << "KSP hardware: " << ksp.activeHardwareName() << "\n"
              << "KSS hardware: " << kss.hardwareDescription() << "\n"
              << "PLAY calls: KSP=" << ksp.playCalls() << ", KSS=" << kss.playCalls() << "\n"
              << "Canonical chip writes: KSP=" << kt.size() << ", KSS=" << st.size() << "\n"
              << "KSS mapper switches: " << kss.bankSwitches() << "\n"
              << "Result: " << (identical ? "IDENTICAL" : "DIFFERENT") << "\n";

    if (!trace_identical) {
        std::cout << "\nIssue: canonical chip-write trace differs.\n";
        const tinyksp::TraceEvent* ke = first_event_diff < kt.size() ? &kt[first_event_diff] : nullptr;
        const tinyksp::TraceEvent* se = first_event_diff < st.size() ? &st[first_event_diff] : nullptr;
        std::cout << "First trace divergence at event " << first_event_diff + 1 << ":\n";
        printTraceEvent("KSP", ke); printTraceEvent("KSS", se);
        std::cout << "Trace lengths: KSP=" << kt.size() << ", KSS=" << st.size() << ".\n";
    } else {
        std::cout << "Chip-write trace: identical.\n";
    }

    if (!pcm_identical) {
        const uint64_t frame = first_pcm_diff / 2;
        const char channel = (first_pcm_diff & 1) ? 'R' : 'L';
        std::cout << "Issue: PCM differs from frame " << frame << " ("
                  << std::fixed << std::setprecision(6) << static_cast<double>(frame) / SAMPLE_RATE
                  << " s, channel " << channel << ").\n"
                  << "PCM differing samples: " << pcm_diff_count << '/' << ksp_pcm.size()
                  << ", max absolute delta=" << max_delta << ".\n";
        if (trace_identical)
            std::cout << "The register stream is identical, so this points to mixer/device-state or hardware-profile differences rather than conversion sequencing.\n";
    } else {
        std::cout << "PCM: bit-identical.\n";
    }
    if (kss.dacWrites())
        std::cout << "Note: KSS executed " << kss.dacWrites() << " DAC writes; these are included in trace diagnostics.\n";
    return identical ? 0 : 3;
}

int runKss(const fs::path& path, int track, bool track_explicit, uint32_t seconds,
           const fs::path& wav, bool dry_run, bool list) {
    tinyksp::KssVm vm(SAMPLE_RATE);
    std::string error;
    if (!vm.open(path.string(), error)) { std::cerr << "KSS open failed: " << error << "\n"; return 1; }
    std::cout << "\nKSS information\n---------------\n"
              << "File: " << path.filename().string() << "\n"
              << "File size: " << humanSize(vm.fileSize()) << "\n"
              << "Load: $" << std::hex << std::setw(4) << std::setfill('0') << vm.loadAddress()
              << " length=$" << std::setw(4) << vm.loadLength()
              << " init=$" << std::setw(4) << vm.initAddress()
              << " play=$" << std::setw(4) << vm.playAddress() << std::dec << std::setfill(' ') << "\n"
              << "Timing: " << (vm.palMode() ? "PAL 50 Hz" : "NTSC 60 Hz") << "\n"
              << "Mapper: " << (vm.bank8k() ? "8 KiB" : "16 KiB") << ", banks="
              << static_cast<unsigned>(vm.bankCount()) << ", offset=" << static_cast<unsigned>(vm.bankOffset()) << "\n"
              << "Hardware: " << vm.hardwareDescription() << "\n";
    if (vm.hasDeclaredSongRange())
        std::cout << "Declared KSS songs: " << vm.firstSong() << ".." << vm.lastSong() << "\n";
    else
        std::cout << "Declared KSS songs: not specified by header\n";
    if (list) return 0;
    const uint32_t song32 = track_explicit
        ? (vm.hasDeclaredSongRange() ? static_cast<uint32_t>(vm.firstSong()) + static_cast<uint32_t>(track)
                                     : static_cast<uint32_t>(track))
        : (vm.hasDeclaredSongRange() ? vm.firstSong() : 0u);
    if (track < -1 || song32 > 0xffffu || (vm.hasDeclaredSongRange() && song32 > vm.lastSong())) {
        std::cerr << "Track outside declared KSS track range.\n"; return 2;
    }
    const uint16_t song = static_cast<uint16_t>(song32);
    if (!vm.start(song, error)) { std::cerr << "KSS start failed: " << error << "\n"; return 1; }
    const uint32_t duration = seconds ? seconds : 180;
    if (dry_run) {
        std::vector<int16_t> buffer(SAMPLE_RATE / 10 * 2);
        if (!vm.render(buffer.data(), SAMPLE_RATE / 10, error)) { std::cerr << "KSS dry run failed: " << error << "\n"; return 1; }
        std::cout << "Dry run passed: PLAY calls=" << vm.playCalls() << ", PSG writes=" << vm.psgWrites()
                  << ", SCC writes=" << vm.sccWrites() << ", FM-PAC writes=" << vm.fmpacWrites()
                  << ", Y8950 writes=" << vm.y8950Writes() << ", bank switches=" << vm.bankSwitches() << "\n";
        return 0;
    }
    if (!wav.empty()) {
        if (!renderKssWav(vm, wav, duration, error)) { std::cerr << "KSS render failed: " << error << "\n"; return 1; }
        std::cout << "Done. PLAY calls=" << vm.playCalls() << ", PSG writes=" << vm.psgWrites()
                  << ", SCC writes=" << vm.sccWrites() << ", FM-PAC writes=" << vm.fmpacWrites()
                  << ", Y8950 writes=" << vm.y8950Writes() << ", bank switches=" << vm.bankSwitches() << "\n";
        return 0;
    }
#ifndef TINYKSP_MACOS
    if (!commandExists("mpv")) { std::cerr << "mpv is missing from PATH. Install mpv or use --wav.\n"; return 1; }
#endif
    std::cout << "Playing KSS song " << song << " for " << formatSeconds(duration) << ". q/Esc stops.\n";
    if (!playKssLive(vm, duration, error)) { std::cerr << "KSS playback failed: " << error << "\n"; return 1; }
    return 0;
}

void usage() {
    std::cout
        << "TinyKSP standalone VM " << PROGRAM_VERSION << "\n\n"
        << "Usage:\n"
        << "  tinyksp                         scan Downloads recursively\n"
        << "  tinyksp FILE.ksp --list\n"
        << "  tinyksp '*.ksp' [--seconds N] [--yrw801 FILE]\n"
        << "  tinyksp FILE1.ksp FILE2.ksp ... [--seconds N]\n"
        << "  tinyksp FILE.ksp --track N [--variant N] [--seconds N] [--yrw801 FILE]\n"
        << "  tinyksp FILE.ksp --track N [--variant N] --wav output.wav\n"
        << "  tinyksp FILE.ksp --track N [--variant N] --dry-run\n"
        << "  tinyksp FILE.kss --track N [--seconds N] [--wav output.wav]\n"
        << "  tinyksp --compare FILE.ksp FILE.kss --track N [--variant N] [--seconds N]\n\n"
        << "Playback advances through the remaining playable tracks, then through the\n"
        << "next matched KSP file. Wildcards support * and ? in the filename. Quote the\n"
        << "pattern when the shell should pass it to TinyKSP unchanged.\n\n"
        << "Package META fields and technical package information are shown immediately\n"
        << "after a KSP file is opened.\n\n"
        << "Live keys: Left/Right selects the previous/next playable track; Shift+, (<) and Shift+. (>) seek\n"
        << "back/forward 10 seconds; 1-0 mutes channels on the current page; Tab\n"
        << "selects the next channel page; u unmutes all channels; q or Esc stops.\n\n"
        << "Playback core: direct Z80 + PSG + SCC/SCC+/dual-SCC + FM-PAC/YM2413 +\n"
        << "Y8950 + MoonSound/OPL4 FM/PCM. KSS/KSSX uses the same direct VM.\n"
        << "KSP 1.03/1.04/1.05 META and strict HVAR/HVR1 selection are supported.\n"
        << "Manual playback types are eligible HVR1 candidates in rank order.\n";
}
} // namespace

int main(int argc, char** argv) {
    enableAnsiTerminal();
    std::signal(SIGINT, signalHandler);
    std::signal(SIGTERM, signalHandler);
#ifdef SIGPIPE
    std::signal(SIGPIPE, SIG_IGN);
#endif

    std::vector<std::string> file_arguments;
    fs::path wav, yrw801;
    int requested_track = -1;
    int requested_variant = -1;
    uint32_t seconds = 0;
    bool list = false;
    bool dry_run = false;
    bool compare = false;
    bool track_explicit = false;
    bool variant_explicit = false;
    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") {
                usage();
                return 0;
            }
            if (arg == "--version" || arg == "-v") {
                std::cout << "TinyKSP standalone VM " << PROGRAM_VERSION << "\n";
                return 0;
            }
            if (arg == "--list") {
                list = true;
                continue;
            }
            if (arg == "--dry-run") {
                dry_run = true;
                continue;
            }
            if (arg == "--compare") {
                compare = true;
                continue;
            }
            if (arg == "--track" && i + 1 < argc) {
                requested_track = std::stoi(argv[++i]) - 1;
                track_explicit = true;
                continue;
            }
            if (arg == "--variant" && i + 1 < argc) {
                requested_variant = std::stoi(argv[++i]) - 1;
                variant_explicit = true;
                continue;
            }
            if (arg == "--seconds" && i + 1 < argc) {
                seconds = static_cast<uint32_t>(std::stoul(argv[++i]));
                continue;
            }
            if (arg == "--wav" && i + 1 < argc) {
                wav = argv[++i];
                continue;
            }
            if (arg == "--yrw801" && i + 1 < argc) {
                yrw801 = argv[++i];
                continue;
            }
            if (!arg.empty() && arg[0] == '-') {
                std::cerr << "Unknown option: " << arg << "\n";
                return 2;
            }
            file_arguments.push_back(std::move(arg));
        }
    } catch (const std::exception& ex) {
        std::cerr << "Invalid command-line value: " << ex.what() << "\n";
        return 2;
    }


    if (seconds > 3600) {
        std::cerr << "Maximum duration is 3600 seconds per track.\n";
        return 2;
    }

    if (compare) {
        if (!track_explicit || file_arguments.size() != 2 || !wav.empty() || dry_run || list) {
            std::cerr << "--compare requires exactly one KSP, one KSS and --track N; do not combine it with --wav, --dry-run or --list.\n";
            return 2;
        }
        fs::path ksp_path, kss_path;
        for (const auto& arg : file_arguments) {
            fs::path p(arg);
            if (lower(p.extension().string()) == ".ksp") ksp_path = p;
            else if (isKssPath(p)) kss_path = p;
        }
        if (ksp_path.empty() || kss_path.empty()) {
            std::cerr << "--compare needs one .ksp and one .kss/.kssx file.\n";
            return 2;
        }
        return runCompare(ksp_path, kss_path, requested_track, requested_variant,
                          variant_explicit, seconds);
    }

    if (file_arguments.size() == 1 && isKssPath(fs::path(file_arguments[0]))) {
        return runKss(fs::path(file_arguments[0]), requested_track, track_explicit, seconds,
                      wav, dry_run, list);
    }
    std::vector<fs::path> files;
    bool used_wildcard = false;
    std::string error;
    if (file_arguments.empty()) {
        const auto found = findKspFiles();
        if (found.empty()) {
            std::cerr << "No KSP files found in Downloads or the current directory.\n";
            return 1;
        }
        std::cout << "KSP files:\n";
        for (size_t i = 0; i < found.size(); ++i)
            std::cout << "  " << i + 1 << ". " << found[i].string() << "\n";
        const int selected = chooseIndex("Select file", static_cast<int>(found.size()));
        if (selected < 0) return 0;
        files.push_back(found[static_cast<size_t>(selected)]);
    } else {
        files = expandKspArguments(file_arguments, used_wildcard, error);
        if (files.empty()) {
            std::cerr << "File selection failed: " << error << "\n";
            return 1;
        }
    }

    const bool playlist_mode = used_wildcard || files.size() > 1;
    if ((!wav.empty() || dry_run) && files.size() != 1) {
        std::cerr << "--wav and --dry-run require exactly one KSP file.\n";
        return 2;
    }
#ifndef TINYKSP_MACOS
    if (!list && wav.empty() && !dry_run && !commandExists("mpv")) {
#ifdef TINYKSP_WINDOWS
        std::cerr << "mpv.exe is missing from PATH. Install mpv or use --wav.\n";
#else
        std::cerr << "mpv is missing from PATH. Install mpv or use --wav.\n";
#endif
        return 1;
    }
#endif

    tinyksp::KspVm vm(SAMPLE_RATE);
    uint32_t preferred_hardware = 0;
    bool handled_any = false;
    bool played_any = false;
    interrupted.store(false);
    constexpr uint32_t HW_OPL4 = 1u << 6;

    for (size_t file_index = 0; file_index < files.size(); ++file_index) {
        const fs::path& file = files[file_index];
        error.clear();
        if (!vm.open(file.string(), error)) {
            if (!playlist_mode) {
                std::cerr << "Open failed: " << error << "\n";
                return 1;
            }
            std::cerr << "Skipping " << file.string() << ": open failed: " << error << "\n";
            continue;
        }
        const int count = vm.visibleTrackCount();
        if (count <= 0) {
            if (!playlist_mode) {
                std::cerr << "No visible tracks.\n";
                return 1;
            }
            std::cerr << "Skipping " << file.string() << ": no visible tracks.\n";
            continue;
        }

        if (playlist_mode)
            std::cout << "\nFile " << file_index + 1 << '/' << files.size()
                      << ": " << file.string() << "\n";
        printPackageInfo(vm, file);
        std::cout << "Tracks\n------\n";
        for (int i = 0; i < count; ++i) {
            std::cout << "  " << i + 1 << ". " << vm.visibleTrackTitle(i) << "\n";
            if (list) {
                const int variants = vm.playbackVariantCount(i);
                for (int v = 0; v < variants; ++v)
                    std::cout << "       type " << v + 1 << ": "
                              << vm.playbackVariantName(i, v) << "\n";
            }
        }
        handled_any = true;
        if (list) continue;

        int track = -1;
        if (file_index == 0 && track_explicit) {
            track = requested_track;
        } else if (!playlist_mode && file_index == 0 && count > 1) {
            track = chooseIndex("Select track", count);
            if (track < 0) return 0;
        } else {
            track = findFirstPlayableTrack(vm);
        }
        if (track < 0 || track >= count) {
            if (!playlist_mode || (file_index == 0 && track_explicit)) {
                std::cerr << "Track outside available range.\n";
                return 2;
            }
            std::cerr << "Skipping " << file.string() << ": no playable track.\n";
            continue;
        }

        const int variant_count = vm.playbackVariantCount(track);
        if (variant_count <= 0) {
            std::cerr << "This track has no playback type supported by TinyKSP";
            const std::string reason = vm.playbackUnsupportedReason(track);
            if (!reason.empty()) std::cerr << ": " << reason;
            std::cerr << ".\n";
            if (!playlist_mode || (file_index == 0 && track_explicit)) return 1;
            continue;
        }

        int variant = -1;
        if (file_index == 0 && variant_explicit) {
            variant = requested_variant;
        } else if (preferred_hardware != 0) {
            variant = findVariantForHardware(vm, track, preferred_hardware);
        } else if (!playlist_mode && file_index == 0 && variant_count > 1) {
            std::cout << "Playback types:\n";
            for (int i = 0; i < variant_count; ++i)
                std::cout << "  " << i + 1 << ". " << vm.playbackVariantName(track, i) << "\n";
            variant = chooseIndex("Select playback type", variant_count);
            if (variant < 0) return 0;
        } else {
            variant = 0;
        }
        if (variant < 0 || variant >= variant_count) {
            std::cerr << "Playback type outside available range.\n";
            return 2;
        }

        if (packageUsesHardware(vm, HW_OPL4)) {
            const fs::path rom = findYrw801Rom(file, yrw801);
            if (!rom.empty()) {
                if (!vm.loadYrw801Rom(rom.string(), error)) {
                    std::cerr << "MoonSound ROM load failed: " << error << "\n";
                    return 1;
                }
                std::cout << "MoonSound ROM: " << rom.string() << "\n";
            } else {
                std::cout << "MoonSound ROM: not found; embedded MWK/custom RAM samples remain available.\n";
            }
        }
        if (!vm.start(track, variant, error)) {
            std::cerr << "Start failed: " << error << "\n";
            return 1;
        }
        std::cout << "Playback type: " << vm.playbackVariantName(track, variant) << "\n";

        const uint32_t initial_seconds = seconds != 0
            ? seconds : vm.suggestedSeconds(track, variant);
        if (dry_run) {
            std::vector<int16_t> buffer(SAMPLE_RATE / 10 * 2);
            if (!vm.render(buffer.data(), SAMPLE_RATE / 10, error)) {
                std::cerr << "Dry run failed: " << error << "\n";
                return 1;
            }
            std::cout << "Dry run passed: play calls=" << vm.playCalls()
                      << ", dynamic switches=" << vm.dynamicSwitches()
                      << ", PSG writes=" << vm.psgWrites()
                      << ", SCC-A writes=" << vm.sccAWrites()
                      << ", SCC-B writes=" << vm.sccBWrites()
                      << ", Y8950 writes=" << vm.y8950Writes()
                      << ", FM-PAC writes=" << vm.fmpacWrites()
                      << ", OPL4-FM writes=" << vm.opl4FmWrites()
                      << ", OPL4-PCM writes=" << vm.opl4PcmWrites()
                      << ", MWK samples=" << vm.opl4CustomSamples()
                      << ", channels=" << vm.channelCount() << "\n";
            return 0;
        }
        if (!wav.empty()) {
            std::cout << "Rendering " << initial_seconds << " seconds to " << wav << "...\n";
            if (!renderWav(vm, wav, initial_seconds, error)) {
                std::cerr << "Render failed: " << error << "\n";
                return 1;
            }
            std::cout << "Done. PLAY calls=" << vm.playCalls()
                      << ", page switches=" << vm.dynamicSwitches()
                      << ", PSG writes=" << vm.psgWrites()
                      << ", SCC-A writes=" << vm.sccAWrites()
                      << ", SCC-B writes=" << vm.sccBWrites()
                      << ", Y8950 writes=" << vm.y8950Writes()
                      << ", FM-PAC writes=" << vm.fmpacWrites()
                      << ", OPL4-FM writes=" << vm.opl4FmWrites()
                      << ", OPL4-PCM writes=" << vm.opl4PcmWrites()
                      << ", MWK samples=" << vm.opl4CustomSamples() << "\n";
            return 0;
        }

        std::cout << "Playing track " << track + 1 << " for "
                  << formatSeconds(initial_seconds)
                  << "; following tracks continue automatically.\n";
        played_any = true;
        const PlaybackResult result = playLive(
            vm, track, variant, seconds, file_index + 1 < files.size(), error);
        preferred_hardware = vm.activeHardware();
        if (result == PlaybackResult::Failed) {
            std::cerr << "Playback failed: " << error << "\n";
            return 1;
        }
        if (result == PlaybackResult::Stopped) return 0;
        if (file_index + 1 < files.size())
            std::cout << "Advancing to next KSP file.\n";
    }

    if ((list && !handled_any) || (!list && !played_any)) {
        std::cerr << "No usable KSP files were found.\n";
        return 1;
    }
    if (!list && playlist_mode) std::cout << "Playlist finished.\n";
    return 0;
}
