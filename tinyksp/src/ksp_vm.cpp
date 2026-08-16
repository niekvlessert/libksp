#include "ksp_vm.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace tinyksp {
namespace {
constexpr uint16_t DUAL_SELECT_A = 0xd900;
constexpr uint16_t DUAL_SELECT_B = 0xd904;
constexpr uint16_t DUAL_RESTORE_RAM = 0xd908;
constexpr uint16_t LEGACY_SELECT = 0xd903;
constexpr uint16_t DEFAULT_GATEWAY = 0xd8a0;

bool containsZ80Call(const std::vector<uint8_t>& page, uint16_t address) {
    for (size_t i = 0; i + 2 < page.size(); ++i) {
        if (page[i] == 0xcd && page[i + 1] == static_cast<uint8_t>(address) &&
            page[i + 2] == static_cast<uint8_t>(address >> 8))
            return true;
    }
    return false;
}

int16_t softCompress(int32_t sample) {
    constexpr int32_t threshold = 32768 * 8 / 10;
    if (sample < -threshold) sample = ((sample + threshold) >> 2) - threshold;
    else if (sample > threshold) sample = ((sample - threshold) >> 2) + threshold;
    if (sample < -32767) sample = -32767;
    else if (sample > 32767) sample = 32767;
    return static_cast<int16_t>(sample);
}
}

KspVm::KspVm(uint32_t sample_rate)
    : cpu_(*this), sample_rate_(sample_rate ? sample_rate : 44100) {
    initializeMachine();
}

KspVm::~KspVm() {
    std::string ignored;
    stop(ignored);
}

void KspVm::initializeMachine() {
    memory_.fill(0);
    // Minimal MSX BIOS-facing stubs used by self-contained music drivers.
    memory_[0x0000] = 0xc9; // RESET/CHKRAM fallback
    memory_[0x0005] = 0xc9; // DOS BDOS fallback
    memory_[0x000c] = 0xaf; memory_[0x000d] = 0xc9; // RDSLT -> 0
    memory_[0x0014] = 0xc9; // WRSLT
    memory_[0x001c] = 0xc9; // CALSLT
    memory_[0x0024] = 0xc9; // ENASLT
    memory_[0x0030] = 0xc9; // CALLF
    memory_[0x0138] = 0xaf; memory_[0x0139] = 0xc9; // RSLREG -> 0
    memory_[0x013b] = 0xc9; // WSLREG
    memory_[0x013e] = 0xaf; memory_[0x013f] = 0xc9; // RDVDP -> 0
    memory_[0x0141] = 0xff; memory_[0x0142] = 0xc9; // SNSMAT -> no keys
    // KSP PAGE3_WORKRAM profile: private page 3 is initialized to FFh
    // immediately before INIT. Engines may use FFh-terminated state tables.
    if (engine_.flags & ENGINE_PAGE3_WORKRAM) {
        std::fill(memory_.begin() + 0xc000, memory_.end(), 0xff);
    }

    cpu_.reset();
    cpu_.setSP(0xf380);
    psg_.reset(sample_rate_);
    scc_a_.reset(sample_rate_, false);
    scc_b_.reset(sample_rate_, false);
    y8950_.reset(sample_rate_);
    fmpac_.reset(sample_rate_);
    opl4_.reset(sample_rate_);
    selected_scc_ = 0;
    scc_normal_enabled_ = false;
    scc_plus_enabled_ = false;
    legacy_dual_scc_ = false;
    gateway_failed_ = false;
    gateway_error_.clear();
    trace_psg_reg_ = trace_fmpac_reg_ = trace_y8950_reg_ = 0;
    trace_opl4_fm_low_reg_ = trace_opl4_fm_high_reg_ = trace_opl4_pcm_reg_ = 0;
}

bool KspVm::open(const std::string& path, std::string& error) {
    close();
    return package_.load(path, error);
}

void KspVm::close() {
    std::string ignored;
    stop(ignored);
    package_.clear();
    implementation_track_ = logical_track_ = 0xffff;
}

uint32_t KspVm::suggestedSeconds(int visible_index) const {
    return suggestedSeconds(visible_index, 0);
}

uint32_t KspVm::suggestedSeconds(int visible_index, int variant_index) const {
    const uint16_t logical = package_.logicalTrackAt(visible_index);
    uint16_t implementation = 0xffff;
    std::string ignored;
    Track effective{};
    if (logical != 0xffff && package_.resolveTrackVariant(visible_index, variant_index,
            supportedHardwareMask(), implementation, ignored)) {
        effective = package_.effectiveTrack(logical, implementation);
    } else if (const Track* track = package_.track(logical)) {
        effective = *track;
    }
    if (effective.duration_ms == 0xffffffffu || effective.duration_ms == 0)
        return 180;
    const uint64_t rounded = (static_cast<uint64_t>(effective.duration_ms) + 999u) / 1000u;
    return static_cast<uint32_t>(std::clamp<uint64_t>(rounded, 1, 3600));
}

int KspVm::playbackVariantCount(int visible_index) const {
    return static_cast<int>(package_.playbackVariants(visible_index, supportedHardwareMask()).size());
}

std::string KspVm::playbackVariantName(int visible_index, int variant_index) const {
    const auto variants = package_.playbackVariants(visible_index, supportedHardwareMask());
    if (variant_index < 0 || static_cast<size_t>(variant_index) >= variants.size())
        return "Invalid playback type";
    const PlaybackVariant& variant = variants[static_cast<size_t>(variant_index)];
    std::string result = variant.label;
    if (package_.hasHardwareVariants()) result += " (rank " + std::to_string(variant.quality_rank) + ")";
    if (variant.visible_fallback) result += " (fallback)";
    return result;
}

uint32_t KspVm::playbackVariantHardware(int visible_index, int variant_index) const {
    const auto variants = package_.playbackVariants(visible_index, supportedHardwareMask());
    if (variant_index < 0 || static_cast<size_t>(variant_index) >= variants.size()) return 0;
    return variants[static_cast<size_t>(variant_index)].hardware;
}

bool KspVm::installPage(const std::vector<uint8_t>& page, bool replacement, std::string& error) {
    if (engine_.page_size == 0 || page.size() != engine_.page_size) {
        error = "materialized page size does not match engine descriptor";
        return false;
    }
    const uint32_t start = engine_.load_address;
    const uint32_t end = start + engine_.page_size;
    if (end > memory_.size()) {
        error = "engine page lies outside the Z80 address space";
        return false;
    }
    uint32_t copy_start = start;
    if (replacement) {
        copy_start = engine_.replace_start ? engine_.replace_start : start;
        if (copy_start < start || copy_start > end) {
            error = "invalid dynamic replacement boundary";
            return false;
        }
    }
    const size_t source_offset = static_cast<size_t>(copy_start - start);
    std::copy(page.begin() + static_cast<ptrdiff_t>(source_offset), page.end(),
              memory_.begin() + static_cast<ptrdiff_t>(copy_start));

    if ((engine_.flags & ENGINE_PAGE2_RUNTIME) && !replacement) {
        if (0x8000u + page.size() > memory_.size()) {
            error = "page-2 runtime copy lies outside Z80 memory";
            return false;
        }
        std::copy(page.begin(), page.end(), memory_.begin() + 0x8000);
    }
    return true;
}

bool KspVm::callRoutine(uint16_t address, uint64_t cycles, std::string& error) {
    if (address == 0) return true;
    gateway_failed_ = false;
    gateway_error_.clear();
    if (!cpu_.call(address, cycles, error)) return false;
    if (gateway_failed_) {
        error = gateway_error_;
        return false;
    }
    return true;
}

bool KspVm::start(int visible_index, std::string& error) {
    return start(visible_index, 0, error);
}

bool KspVm::start(int visible_index, int variant_index, std::string& error) {
    if (visible_index < 0 || visible_index >= package_.visibleTrackCount()) {
        error = "track selection outside visible track list";
        return false;
    }
    const uint16_t logical = package_.logicalTrackAt(visible_index);
    uint16_t implementation = 0xffff;
    if (!package_.resolveTrackVariant(visible_index, variant_index,
                                      supportedHardwareMask(), implementation, error))
        return false;
    return startResolved(logical, implementation, error);
}

bool KspVm::startPhysical(uint16_t physical_track, std::string& error) {
    uint16_t implementation = 0xffff;
    if (!package_.resolvePhysicalTrack(physical_track, supportedHardwareMask(),
                                       implementation, error))
        return false;
    return startResolved(physical_track, implementation, error);
}

bool KspVm::startResolved(uint16_t logical, uint16_t implementation,
                          std::string& error) {
    std::string ignored;
    stop(ignored);
    logical_track_ = logical;
    const Track* implementation_record = package_.track(implementation);
    const Engine* engine = package_.engineForTrack(implementation);
    if (!implementation_record || !engine) {
        error = "resolved track has no valid engine";
        return false;
    }
    if (engine->tick_hz == 0 || engine->tick_hz > 1000) {
        error = "invalid engine tick frequency";
        return false;
    }
    if ((engine->hardware & HW_DUAL_SCC) && (engine->hardware & HW_SCC_PLUS)) {
        error = "KSP ABI 1 does not define dual SCC+";
        return false;
    }

    engine_ = *engine;
    active_track_ = package_.effectiveTrack(logical_track_, implementation);
    implementation_track_ = implementation;
    initializeMachine();
    // libkss's VM_SCC_AUTO uses emu2212's enhanced type for ordinary SCC
    // engines too; it still starts in standard 9000h mode until BFFE selects
    // the SCC+ window. Native dual-SCC keeps cartridge A explicitly standard.
    scc_a_.setEnhanced((engine_.hardware & HW_SCC_PLUS) != 0 ||
                       ((engine_.hardware & HW_SCC) != 0));
    scc_b_.setEnhanced(false);
    scc_normal_enabled_ = (engine_.hardware & (HW_SCC | HW_DUAL_SCC)) != 0;
    scc_plus_enabled_ = (engine_.hardware & HW_SCC_PLUS) != 0;
    selected_scc_ = 0;
    play_calls_ = 0;
    dynamic_switches_ = 0;
    trace_phase_ = TracePhase::Init;
    trace_tick_ = 0;
    trace_order_ = 0;
    if (trace_enabled_) trace_.clear();

    std::vector<uint8_t> page;
    if (!package_.materializeTrackPage(implementation, page, error)) return false;
    // Early dual-SCC converters used D900 as an 8-bit page gateway and D903
    // as the SCC selector, without setting the later HW_DUAL_SCC flag.  The
    // desktop reference player detects this ABI from the page itself.
    legacy_dual_scc_ = engine_.page_count > 1 &&
        !(engine_.flags & ENGINE_DYNAMIC_PAGES) && engine_.replace_start != 0 &&
        containsZ80Call(page, DUAL_SELECT_A) && containsZ80Call(page, LEGACY_SELECT);
    if (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC))
        scc_a_.writeAddress(0x9000, 0x3f);
    if ((engine_.hardware & HW_DUAL_SCC) || legacy_dual_scc_)
        scc_b_.writeAddress(0x9000, 0x3f);
    if (!installPage(page, false, error)) return false;

    if (engine_.hardware & HW_OPL4) {
        const uint16_t mwk = implementation_record->mwk != 0xffff
            ? implementation_record->mwk : engine_.default_mwk;
        if ((engine_.flags & ENGINE_MWK_REQUIRED) && mwk == 0xffff) {
            error = "MoonSound engine requires an MWK resource";
            return false;
        }
        if (mwk != 0xffff) {
            if (package_.resourceKind(mwk) != "MWK ") {
                error = "selected MoonSound MWK reference is not an MWK resource";
                return false;
            }
            std::vector<uint8_t> mwk_data;
            if (!package_.materializeResource(mwk, mwk_data, error)) return false;
            if (!opl4_.loadMwk(mwk_data, error)) return false;
        }
    }

    // KSP PAGE3_WORKRAM profile: private page 3 is initialized to FFh
    // immediately before INIT. Engines may use FFh-terminated state tables.
    if (engine_.flags & ENGINE_PAGE3_WORKRAM) {
        std::fill(memory_.begin() + 0xc000, memory_.end(), 0xff);
    }

    cpu_.reset();
    cpu_.setSP(0xf380);
    cpu_.setA(static_cast<uint8_t>(active_track_.song & 0xff));
    cpu_.setHL(active_track_.song);
    trace_phase_ = TracePhase::Init;
    trace_tick_ = 0;
    if (!callRoutine(engine_.init_address, 30'000'000, error)) return false;

    samples_per_tick_ = static_cast<double>(sample_rate_) / engine_.tick_hz;
    // libkss schedules the first VSYNC PLAY event one tick after INIT; do not
    // run PLAY on the first PCM sample.
    samples_until_tick_ = samples_per_tick_;
    // Match libkss's default 47 kOhm / 1 uF output DC blocker.
    dc_filter_weight_ = 1.0 / ((1.0 / sample_rate_) /
                               (1.0e-6 * 47000.0) + 1.0);
    dc_filter_in_[0] = dc_filter_in_[1] = 0.0;
    dc_filter_out_[0] = dc_filter_out_[1] = 0.0;
    started_ = true;
    return true;
}

bool KspVm::stop(std::string& error) {
    if (started_ && engine_.stop_address) {
        if (!callRoutine(engine_.stop_address, 5'000'000, error)) {
            started_ = false;
            return false;
        }
    }
    started_ = false;
    psg_.reset(sample_rate_);
    scc_a_.reset(sample_rate_, false);
    scc_b_.reset(sample_rate_, false);
    y8950_.reset(sample_rate_);
    fmpac_.reset(sample_rate_);
    opl4_.reset(sample_rate_);
    return true;
}

bool KspVm::runPlayTick(std::string& error) {
    trace_phase_ = TracePhase::Play;
    trace_tick_ = play_calls_ + 1;
    if (!callRoutine(engine_.play_address, 5'000'000, error)) return false;
    ++play_calls_;
    return true;
}

void KspVm::recordTrace(TraceDevice device, uint16_t address, uint8_t value) {
    if (!trace_enabled_) return;
    trace_.push_back({trace_phase_, trace_tick_, trace_order_++, device, address, value});
}

std::vector<KspVm::ChannelRef> KspVm::activeChannels() const {
    std::vector<ChannelRef> channels;
    const bool has_scc = (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC)) != 0;
    if (has_scc) {
        for (int i = 0; i < 5; ++i)
            channels.push_back({ChannelDevice::SccA, i,
                                std::string((engine_.hardware & HW_SCC_PLUS) ? "SCC+ " : "SCC-A ") +
                                std::to_string(i + 1)});
        if ((engine_.hardware & HW_DUAL_SCC) || legacy_dual_scc_) {
            for (int i = 0; i < 5; ++i)
                channels.push_back({ChannelDevice::SccB, i, "SCC-B " + std::to_string(i + 1)});
        }
    }
    if (!has_scc && (engine_.hardware & HW_Y8950)) {
        for (int i = 0; i < 9; ++i)
            channels.push_back({ChannelDevice::Y8950, i, "Y8950 FM " + std::to_string(i + 1)});
    }
    if (engine_.hardware & HW_FMPAC) {
        for (int i = 0; i < 9; ++i)
            channels.push_back({ChannelDevice::FmPac, i, "FM-PAC " + std::to_string(i + 1)});
    }
    if (engine_.hardware & HW_OPL4) {
        for (int i = 0; i < 18; ++i)
            channels.push_back({ChannelDevice::Opl4Fm, i, "OPL4 FM " + std::to_string(i + 1)});
        for (int i = 0; i < 24; ++i)
            channels.push_back({ChannelDevice::Opl4Pcm, i, "OPL4 PCM " + std::to_string(i + 1)});
    }
    if (engine_.hardware & HW_PSG) {
        static constexpr const char* names[3] = {"PSG A", "PSG B", "PSG C"};
        for (int i = 0; i < 3; ++i) channels.push_back({ChannelDevice::Psg, i, names[i]});
    }
    if (has_scc && (engine_.hardware & HW_Y8950)) {
        for (int i = 0; i < 9; ++i)
            channels.push_back({ChannelDevice::Y8950, i, "Y8950 FM " + std::to_string(i + 1)});
    }
    return channels;
}

int KspVm::channelCount() const {
    return static_cast<int>(activeChannels().size());
}

std::string KspVm::channelName(int channel_index) const {
    const auto channels = activeChannels();
    if (channel_index < 0 || static_cast<size_t>(channel_index) >= channels.size())
        return "Invalid channel";
    return channels[static_cast<size_t>(channel_index)].name;
}

bool KspVm::channelMuted(int channel_index) const {
    const auto channels = activeChannels();
    if (channel_index < 0 || static_cast<size_t>(channel_index) >= channels.size()) return false;
    const ChannelRef& ref = channels[static_cast<size_t>(channel_index)];
    switch (ref.device) {
    case ChannelDevice::SccA: return scc_a_.muted(ref.channel);
    case ChannelDevice::SccB: return scc_b_.muted(ref.channel);
    case ChannelDevice::Psg: return psg_.muted(ref.channel);
    case ChannelDevice::Y8950: return y8950_.muted(ref.channel);
    case ChannelDevice::FmPac: return fmpac_.muted(ref.channel);
    case ChannelDevice::Opl4Fm: return opl4_.fmMuted(ref.channel);
    case ChannelDevice::Opl4Pcm: return opl4_.pcmMuted(ref.channel);
    }
    return false;
}

bool KspVm::toggleChannelMute(int channel_index, bool& now_muted) {
    const auto channels = activeChannels();
    if (channel_index < 0 || static_cast<size_t>(channel_index) >= channels.size()) return false;
    const ChannelRef& ref = channels[static_cast<size_t>(channel_index)];
    now_muted = !channelMuted(channel_index);
    switch (ref.device) {
    case ChannelDevice::SccA: scc_a_.setMuted(ref.channel, now_muted); break;
    case ChannelDevice::SccB: scc_b_.setMuted(ref.channel, now_muted); break;
    case ChannelDevice::Psg: psg_.setMuted(ref.channel, now_muted); break;
    case ChannelDevice::Y8950: y8950_.setMuted(ref.channel, now_muted); break;
    case ChannelDevice::FmPac: fmpac_.setMuted(ref.channel, now_muted); break;
    case ChannelDevice::Opl4Fm: opl4_.setFmMuted(ref.channel, now_muted); break;
    case ChannelDevice::Opl4Pcm: opl4_.setPcmMuted(ref.channel, now_muted); break;
    }
    return true;
}

void KspVm::unmuteAllChannels() {
    scc_a_.unmuteAll();
    scc_b_.unmuteAll();
    psg_.unmuteAll();
    y8950_.unmuteAll();
    fmpac_.unmuteAll();
    opl4_.unmuteAll();
}

float KspVm::mixedSample() {
    float value = 0.0f;
    if (engine_.hardware & HW_PSG) value += psg_.sample();
    if (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC)) value += scc_a_.sample();
    if ((engine_.hardware & HW_DUAL_SCC) || legacy_dual_scc_) value += scc_b_.sample();
    if (engine_.hardware & HW_Y8950) value += y8950_.sample();
    if (engine_.hardware & HW_FMPAC) value += fmpac_.sample();
    if (engine_.hardware & HW_OPL4) value += opl4_.sample();
    return value;
}

bool KspVm::render(int16_t* output, uint32_t frames, std::string& error) {
    if (!started_) {
        error = "no track is running";
        return false;
    }
    if (!output && frames) {
        error = "null audio output buffer";
        return false;
    }
    for (uint32_t frame = 0; frame < frames; ++frame) {
        while (samples_until_tick_ <= 0.0) {
            if (!runPlayTick(error)) return false;
            samples_until_tick_ += samples_per_tick_;
        }
        float left = 0.0f, right = 0.0f;
        // Legacy chips are mono/centered; preserve the YMF278B's native stereo.
        if (engine_.hardware & HW_PSG) {
            const float sample = psg_.sample();
            left += sample;
            right += sample;
        }
        if (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC)) {
            const float sample = scc_a_.sample();
            left += sample;
            right += sample;
        }
        if (engine_.hardware & HW_Y8950) {
            const float sample = y8950_.sample();
            left += sample;
            right += sample;
        }
        if (engine_.hardware & HW_FMPAC) {
            const float sample = fmpac_.sample();
            left += sample;
            right += sample;
        }
        if (engine_.hardware & HW_OPL4) {
            float opl4_left = 0.0f, opl4_right = 0.0f;
            opl4_.sampleStereo(opl4_left, opl4_right);
            left += opl4_left;
            right += opl4_right;
        }
        // libkss applies its output DC blocker while calculating the primary
        // device mix. The legacy desktop bridge then adds SCC-B's raw
        // emu2212 sample and runs the combined value through soft clipping.
        // Keep that ordering for dual-SCC engines; a single-SCC engine still
        // follows the ordinary whole-mix path above.
        const bool has_secondary_scc =
            (engine_.hardware & HW_DUAL_SCC) || legacy_dual_scc_;
        const float secondary = has_secondary_scc ? scc_b_.sample() : 0.0f;
        const float mixed[2] = {left, right};
        for (int channel = 0; channel < 2; ++channel) {
            const int32_t input = static_cast<int32_t>(mixed[channel] * 32767.0f);
            dc_filter_out_[channel] = dc_filter_weight_ *
                (dc_filter_out_[channel] + input - dc_filter_in_[channel]);
            dc_filter_in_[channel] = input;
            output[frame * 2 + channel] = softCompress(
                static_cast<int32_t>(dc_filter_out_[channel]) +
                static_cast<int32_t>(secondary * 32767.0f));
        }
        samples_until_tick_ -= 1.0;
    }
    return true;
}

bool KspVm::handleDynamicGateway(std::string& error) {
    if (!(engine_.flags & ENGINE_DYNAMIC_PAGES)) return true;
    const uint16_t local_page = cpu_.hl();
    std::vector<uint8_t> page;
    if (!package_.materializeDynamicPage(implementation_track_, local_page, page, error))
        return false;
    if (!installPage(page, true, error)) return false;
    ++dynamic_switches_;
    return true;
}

bool KspVm::handleLegacyPageGateway(std::string& error) {
    const uint16_t local_page = static_cast<uint16_t>(cpu_.af() >> 8);
    std::vector<uint8_t> page;
    if (!package_.materializeDynamicPage(implementation_track_, local_page, page, error))
        return false;
    if (!installPage(page, true, error)) return false;
    ++dynamic_switches_;
    return true;
}

uint8_t KspVm::opcodeRead(uint16_t address) {
    if ((engine_.flags & ENGINE_DYNAMIC_PAGES) &&
        address == (engine_.gateway ? engine_.gateway : DEFAULT_GATEWAY)) {
        std::string error;
        if (!handleDynamicGateway(error)) {
            gateway_failed_ = true;
            gateway_error_ = error;
        }
        return 0xc9; // host-handled gateway returns to its CALL site
    }
    // KSP SCC conversion engines use these host callbacks as cartridge-slot
    // wrappers even in their single-SCC fallback implementation.  They are an
    // engine ABI convention, not proof that HW_DUAL_SCC was selected.  Always
    // service SELECT_A/RESTORE; SELECT_B remains harmless and allows shared
    // single/dual engine templates.
    if (address == DUAL_SELECT_A) {
        if (legacy_dual_scc_) {
            std::string error;
            if (!handleLegacyPageGateway(error)) {
                gateway_failed_ = true;
                gateway_error_ = error;
            }
            return 0xc9;
        }
        selected_scc_ = 0;
        scc_normal_enabled_ = true;
        return 0xc9;
    }
    if (address == DUAL_SELECT_B) {
        selected_scc_ = 1;
        scc_normal_enabled_ = true;
        return 0xc9;
    }
    if (address == LEGACY_SELECT) {
        const uint8_t selector = static_cast<uint8_t>(cpu_.af() >> 8);
        selected_scc_ = selector == 0 ? 0 : selector == 1 ? 1 : -1;
        scc_normal_enabled_ = true;
        return 0xc9;
    }
    if (address == DUAL_RESTORE_RAM) {
        selected_scc_ = -1;
        return 0xc9;
    }
    return memRead(address);
}

uint8_t KspVm::memRead(uint16_t address) {
    // Engine data reads in the SCC window remain RAM reads. Several converted
    // Konami drivers intentionally keep selected stream bytes in this range.
    return memory_[address];
}

void KspVm::memWrite(uint16_t address, uint8_t value) {
    // $D84F is a legacy selector used by some SCC engines. It is ordinary
    // work RAM for non-SCC drivers, so only intercept it when SCC is declared.
    if (address == 0xd84f &&
        (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC))) {
        selected_scc_ = value == 0 ? 0 : value == 1 ? 1 : -1;
        scc_normal_enabled_ = true;
        if (selected_scc_ == 1) legacy_dual_scc_ = true;
        return;
    }
    if (address == 0x9000 && (engine_.hardware & (HW_SCC | HW_DUAL_SCC))) {
        if ((value & 0x3f) == 0x3f) scc_normal_enabled_ = true;
        if (selected_scc_ >= 0) {
            auto& scc = selected_scc_ == 0 ? scc_a_ : scc_b_;
            scc.writeAddress(address, value == 0 ? 0 : 0x3f);
        }
        memory_[address] = value;
        return;
    }
    if (address == 0xb000 &&
        (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC)) &&
        selected_scc_ >= 0) {
        (selected_scc_ == 0 ? scc_a_ : scc_b_).writeAddress(address, value);
        memory_[address] = value;
        return;
    }
    if (address == 0xbffe &&
        (engine_.hardware & (HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC)) &&
        selected_scc_ >= 0) {
        scc_plus_enabled_ = (value & 0x20) != 0 || value == 0;
        (selected_scc_ == 0 ? scc_a_ : scc_b_).writeAddress(address, value);
        memory_[address] = value;
        return;
    }
    if (address >= 0x9800 && address <= 0x98ff && scc_normal_enabled_ && selected_scc_ >= 0) {
        (selected_scc_ == 0 ? scc_a_ : scc_b_).writeAddress(address, value);
        recordTrace(TraceDevice::Scc, address, value);
        return;
    }
    if (address >= 0xb800 && address <= 0xb8ff && scc_plus_enabled_ &&
        selected_scc_ >= 0) {
        (selected_scc_ == 0 ? scc_a_ : scc_b_).writeAddress(address, value);
        recordTrace(TraceDevice::Scc, address, value);
        return;
    }
    memory_[address] = value;
}

uint8_t KspVm::ioRead(uint16_t port) {
    switch (port & 0xff) {
    case 0xa2: return psg_.read();
    case 0x7c: return fmpac_.readStatus();
    case 0x7d: return fmpac_.readData();
    case 0xc0: return y8950_.readStatus();
    case 0xc1: return y8950_.readData();
    case 0xc4: return opl4_.readFmStatusLow();
    case 0xc5: return opl4_.readFmDataLow();
    case 0xc6: return opl4_.readFmStatusHigh();
    case 0xc7: return opl4_.readFmDataHigh();
    case 0x7e: return opl4_.readWaveStatus();
    case 0x7f: return opl4_.readWaveData();
    case 0xa8: return 0;
    case 0x98: return 0;
    case 0x99: return 0;
    default: return 0xff;
    }
}

void KspVm::ioWrite(uint16_t port, uint8_t value) {
    switch (port & 0xff) {
    case 0xa0: trace_psg_reg_ = value & 0x0f; psg_.select(value); break;
    case 0xa1: psg_.write(value); recordTrace(TraceDevice::Psg, trace_psg_reg_, value); break;
    case 0x7c: trace_fmpac_reg_ = value & 0x3f; fmpac_.select(value); break;
    case 0x7d: fmpac_.write(value); recordTrace(TraceDevice::FmPac, trace_fmpac_reg_, value); break;
    case 0xc0: trace_y8950_reg_ = value; y8950_.select(value); break;
    case 0xc1: y8950_.write(value); recordTrace(TraceDevice::Y8950, trace_y8950_reg_, value); break;
    case 0xc4: trace_opl4_fm_low_reg_ = value; opl4_.selectFmLow(value); break;
    case 0xc5: opl4_.writeFmLow(value); recordTrace(TraceDevice::Opl4FmLow, trace_opl4_fm_low_reg_, value); break;
    case 0xc6: trace_opl4_fm_high_reg_ = value; opl4_.selectFmHigh(value); break;
    case 0xc7: opl4_.writeFmHigh(value); recordTrace(TraceDevice::Opl4FmHigh, trace_opl4_fm_high_reg_, value); break;
    case 0x7e: trace_opl4_pcm_reg_ = value; opl4_.selectWave(value); break;
    case 0x7f: opl4_.writeWave(value); recordTrace(TraceDevice::Opl4Pcm, trace_opl4_pcm_reg_, value); break;
    case 0xa8: break; // slot register: flat host memory has no slot mapping
    case 0x98: case 0x99: break; // VDP writes are irrelevant to audio replay
    default: break;
    }
}

} // namespace tinyksp
