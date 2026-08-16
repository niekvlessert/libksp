#pragma once

#include "chips.h"
#include "ksp_runtime.h"
#include "playback_trace.h"
#include "yamaha_chips.h"
#include "z80.h"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace tinyksp {

class KspVm final : private Z80Bus {
public:
    explicit KspVm(uint32_t sample_rate = 44100);
    ~KspVm();

    bool open(const std::string& path, std::string& error);
    void close();
    int visibleTrackCount() const { return package_.visibleTrackCount(); }
    std::string visibleTrackTitle(int index) const { return package_.visibleTrackTitle(index); }
    uint32_t suggestedSeconds(int visible_index) const;
    uint32_t suggestedSeconds(int visible_index, int variant_index) const;
    int playbackVariantCount(int visible_index) const;
    std::string playbackVariantName(int visible_index, int variant_index) const;
    uint32_t playbackVariantHardware(int visible_index, int variant_index) const;
    std::string playbackUnsupportedReason(int visible_index) const {
        return package_.playbackUnsupportedReason(visible_index, supportedHardwareMask());
    }
    uint16_t minorVersion() const { return package_.minorVersion(); }
    uint64_t fileSize() const { return package_.fileSize(); }
    size_t engineCount() const { return package_.engineCount(); }
    size_t pageCount() const { return package_.pageCount(); }
    size_t trackCount() const { return package_.trackCount(); }
    size_t resourceCount() const { return package_.resourceCount(); }
    uint16_t defaultTrack() const { return package_.defaultTrack(); }
    uint16_t coverResource() const { return package_.coverResource(); }
    std::vector<MetadataEntry> generalMetadata() const { return package_.generalMetadata(); }
    const std::vector<std::string>& metadataWarnings() const { return package_.metadataWarnings(); }
    bool hasHardwareVariants() const { return package_.hasHardwareVariants(); }
    std::vector<std::string> engineSummaries() const { return package_.engineSummaries(); }

    bool start(int visible_index, std::string& error);
    bool start(int visible_index, int variant_index, std::string& error);
    bool startPhysical(uint16_t physical_track, std::string& error);
    bool render(int16_t* interleaved_stereo, uint32_t frames, std::string& error);
    bool stop(std::string& error);

    uint32_t activeHardware() const { return engine_.hardware; }
    std::string activeHardwareName() const { return hardwareDescription(engine_.hardware); }
    int channelCount() const;
    std::string channelName(int channel_index) const;
    bool channelMuted(int channel_index) const;
    bool toggleChannelMute(int channel_index, bool& now_muted);
    void unmuteAllChannels();
    uint64_t playCalls() const { return play_calls_; }
    uint64_t dynamicSwitches() const { return dynamic_switches_; }
    uint64_t psgWrites() const { return psg_.writeCount(); }
    uint64_t sccAWrites() const { return scc_a_.writeCount(); }
    uint64_t sccBWrites() const { return scc_b_.writeCount(); }
    uint64_t y8950Writes() const { return y8950_.writeCount(); }
    uint64_t fmpacWrites() const { return fmpac_.writeCount(); }
    uint64_t opl4FmWrites() const { return opl4_.fmWriteCount(); }
    uint64_t opl4PcmWrites() const { return opl4_.pcmWriteCount(); }
    uint32_t opl4CustomSamples() const { return opl4_.customSampleCount(); }
    bool loadYrw801Rom(const std::string& path, std::string& error) {
        return opl4_.loadYrw801Rom(path, error);
    }
    bool hasYrw801Rom() const { return opl4_.hasRom(); }
    void enableTrace(bool enabled) { trace_enabled_ = enabled; trace_.clear(); trace_order_ = 0; }
    const std::vector<TraceEvent>& trace() const { return trace_; }

private:
    static constexpr uint32_t HW_PSG = 1u << 0;
    static constexpr uint32_t HW_SCC = 1u << 1;
    static constexpr uint32_t HW_SCC_PLUS = 1u << 2;
    static constexpr uint32_t HW_DUAL_SCC = 1u << 3;
    static constexpr uint32_t HW_FMPAC = 1u << 4;
    static constexpr uint32_t HW_Y8950 = 1u << 5;
    static constexpr uint32_t HW_OPL4 = 1u << 6;
    static constexpr uint32_t ENGINE_DYNAMIC_PAGES = 1u << 0;
    static constexpr uint32_t ENGINE_MWK_REQUIRED = 1u << 2;
    static constexpr uint32_t ENGINE_PAGE2_RUNTIME = 1u << 3;
    static constexpr uint32_t ENGINE_PAGE3_WORKRAM = 1u << 4;

    uint8_t memRead(uint16_t address) override;
    uint8_t opcodeRead(uint16_t address) override;
    void memWrite(uint16_t address, uint8_t value) override;
    uint8_t ioRead(uint16_t port) override;
    void ioWrite(uint16_t port, uint8_t value) override;

    void initializeMachine();
    bool installPage(const std::vector<uint8_t>& page, bool replacement, std::string& error);
    bool startResolved(uint16_t logical_track, uint16_t implementation_track,
                       std::string& error);
    bool handleDynamicGateway(std::string& error);
    bool handleLegacyPageGateway(std::string& error);
    bool callRoutine(uint16_t address, uint64_t cycles, std::string& error);
    bool runPlayTick(std::string& error);
    float mixedSample();
    void recordTrace(TraceDevice device, uint16_t address, uint8_t value);

    enum class ChannelDevice : uint8_t { SccA, SccB, Psg, Y8950, FmPac, Opl4Fm, Opl4Pcm };
    struct ChannelRef {
        ChannelDevice device = ChannelDevice::Psg;
        int channel = 0;
        std::string name;
    };
    std::vector<ChannelRef> activeChannels() const;

    KspPackage package_;
    std::array<uint8_t, 65536> memory_{};
    Z80 cpu_;
    PsgDevice psg_;
    SccDevice scc_a_;
    SccDevice scc_b_;
    Y8950Device y8950_;
    Ym2413Device fmpac_;
    Opl4Device opl4_;
    Engine engine_{};
    Track active_track_{};
    uint16_t implementation_track_ = 0xffff;
    uint16_t logical_track_ = 0xffff;
    uint32_t sample_rate_ = 44100;
    double samples_until_tick_ = 0.0;
    double samples_per_tick_ = 735.0;
    double dc_filter_weight_ = 0.0;
    double dc_filter_in_[2] = {0.0, 0.0};
    double dc_filter_out_[2] = {0.0, 0.0};
    int selected_scc_ = 0;
    bool scc_normal_enabled_ = false;
    bool scc_plus_enabled_ = false;
    bool legacy_dual_scc_ = false;
    bool started_ = false;
    bool gateway_failed_ = false;
    std::string gateway_error_;
    uint64_t play_calls_ = 0;
    uint64_t dynamic_switches_ = 0;
    bool trace_enabled_ = false;
    TracePhase trace_phase_ = TracePhase::Init;
    uint64_t trace_tick_ = 0;
    uint32_t trace_order_ = 0;
    uint8_t trace_psg_reg_ = 0;
    uint8_t trace_fmpac_reg_ = 0;
    uint8_t trace_y8950_reg_ = 0;
    uint8_t trace_opl4_fm_low_reg_ = 0;
    uint8_t trace_opl4_fm_high_reg_ = 0;
    uint8_t trace_opl4_pcm_reg_ = 0;
    std::vector<TraceEvent> trace_;
};

} // namespace tinyksp
