#pragma once

#include "chips.h"
#include "playback_trace.h"
#include "yamaha_chips.h"
#include "z80.h"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace tinyksp {

class KssVm final : private Z80Bus {
public:
    explicit KssVm(uint32_t sample_rate = 44100);

    bool open(const std::string& path, std::string& error);
    void close();
    bool start(uint16_t song, std::string& error);
    bool render(int16_t* interleaved_stereo, uint32_t frames, std::string& error);
    bool stop(std::string& error);

    bool hasDeclaredSongRange() const { return has_song_range_; }
    uint16_t firstSong() const { return first_song_; }
    uint16_t lastSong() const { return last_song_; }
    uint16_t initAddress() const { return init_address_; }
    uint16_t playAddress() const { return play_address_; }
    uint16_t loadAddress() const { return load_address_; }
    uint16_t loadLength() const { return load_length_; }
    bool palMode() const { return pal_mode_; }
    bool ramMode() const { return ram_mode_; }
    bool bank8k() const { return bank_8k_; }
    uint8_t bankCount() const { return bank_count_; }
    uint8_t bankOffset() const { return bank_offset_; }
    uint8_t soundFlags() const { return sound_flags_; }
    std::string hardwareDescription() const;
    uint64_t fileSize() const { return file_size_; }

    uint64_t playCalls() const { return play_calls_; }
    uint64_t psgWrites() const { return psg_.writeCount(); }
    uint64_t sccWrites() const { return scc_.writeCount(); }
    uint64_t fmpacWrites() const { return fmpac_.writeCount(); }
    uint64_t y8950Writes() const { return y8950_.writeCount(); }
    uint64_t bankSwitches() const { return bank_switches_; }
    uint64_t dacWrites() const { return dac_writes_; }

    int channelCount() const;
    std::string channelName(int channel) const;
    bool channelMuted(int channel) const;
    bool toggleChannelMute(int channel, bool& now_muted);
    void unmuteAllChannels();

    void enableTrace(bool enabled) { trace_enabled_ = enabled; trace_.clear(); trace_order_ = 0; }
    const std::vector<TraceEvent>& trace() const { return trace_; }

private:
    uint8_t memRead(uint16_t address) override;
    uint8_t opcodeRead(uint16_t address) override { return memRead(address); }
    void memWrite(uint16_t address, uint8_t value) override;
    uint8_t ioRead(uint16_t port) override;
    void ioWrite(uint16_t port, uint8_t value) override;

    void initializeMachine();
    bool callRoutine(uint16_t address, uint64_t cycles, std::string& error);
    bool runPlayTick(std::string& error);
    void record(TraceDevice device, uint16_t address, uint8_t value);
    bool pageUsesBank(uint16_t address) const;
    uint8_t bankRead(uint16_t address) const;
    bool mainWritable(uint16_t address) const;

    std::array<uint8_t, 65536> memory_{};
    std::vector<uint8_t> initial_data_;
    std::vector<uint8_t> bank_data_;
    Z80 cpu_;
    PsgDevice psg_;
    SccDevice scc_;
    Y8950Device y8950_;
    Ym2413Device fmpac_;

    uint32_t sample_rate_ = 44100;
    uint64_t file_size_ = 0;
    uint16_t load_address_ = 0;
    uint16_t load_length_ = 0;
    uint16_t init_address_ = 0;
    uint16_t play_address_ = 0;
    uint8_t bank_offset_ = 0;
    uint8_t bank_count_ = 0;
    bool bank_8k_ = false;
    bool ram_mode_ = false;
    bool pal_mode_ = false;
    bool fmpac_enabled_ = false;
    bool y8950_enabled_ = false;
    bool dac8_enabled_ = false;
    uint8_t sound_flags_ = 0;
    bool has_song_range_ = false;
    uint16_t first_song_ = 0;
    uint16_t last_song_ = 0xffff;

    // -1 means the main KSS image is mapped. 8K mode independently maps
    // pages 4 ($8000-$9FFF) and 5 ($A000-$BFFF). 16K mode maps both together.
    int bank_page4_ = -1;
    int bank_page5_ = -1;
    bool invalid_bank_page4_ = false;
    bool invalid_bank_page5_ = false;

    uint8_t psg_register_ = 0;
    uint8_t fmpac_register_ = 0;
    uint8_t y8950_register_ = 0;
    int32_t dac1_ = 0;
    int32_t dac8_ = 0;
    uint64_t dac_writes_ = 0;

    double samples_until_tick_ = 0.0;
    double samples_per_tick_ = 735.0;
    double dc_filter_weight_ = 0.0;
    double dc_filter_in_[2] = {0.0, 0.0};
    double dc_filter_out_[2] = {0.0, 0.0};
    bool started_ = false;
    uint64_t play_calls_ = 0;
    uint64_t bank_switches_ = 0;

    bool trace_enabled_ = false;
    TracePhase trace_phase_ = TracePhase::Init;
    uint64_t trace_tick_ = 0;
    uint32_t trace_order_ = 0;
    std::vector<TraceEvent> trace_;
};

} // namespace tinyksp
