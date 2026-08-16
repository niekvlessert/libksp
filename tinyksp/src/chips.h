#pragma once

#include <array>
#include <cstdint>

#include "libvgm_psg.h"

struct __SCC;

namespace tinyksp {

class PsgDevice {
public:
    void reset(uint32_t sample_rate);
    void select(uint8_t reg) { selected_ = reg & 0x0f; }
    void write(uint8_t value);
    uint8_t read() const { return registers_[selected_]; }
    float sample();
    void setMuted(int channel, bool muted);
    bool muted(int channel) const;
    void unmuteAll();
    uint64_t writeCount() const { return write_count_; }

private:
    void restartEnvelope();
    float envelopeVolume();

    static constexpr double CLOCK = 3579545.0;
    uint32_t sample_rate_ = 44100;
    std::array<uint8_t, 16> registers_{};
    uint8_t selected_ = 0;
    std::array<double, 3> tone_phase_{};
    std::array<bool, 3> muted_{};
    double noise_phase_ = 0.0;
    uint32_t noise_lfsr_ = 0x1ffff;
    double envelope_phase_ = 0.0;
    int envelope_step_ = 0;
    int envelope_direction_ = -1;
    bool envelope_hold_ = false;
    bool envelope_alternate_ = false;
    bool envelope_continue_ = false;
    bool envelope_holding_ = false;
    uint64_t write_count_ = 0;
    LibVgmPsg libvgm_;
};

class SccDevice {
public:
    SccDevice() = default;
    ~SccDevice();
    SccDevice(const SccDevice&) = delete;
    SccDevice& operator=(const SccDevice&) = delete;

    void reset(uint32_t sample_rate, bool enhanced);
    void setEnhanced(bool enhanced);
    void write(uint8_t offset, uint8_t value);
    void writeAddress(uint16_t address, uint8_t value);
    uint8_t read(uint8_t offset) const;
    float sample();
    void setMuted(int channel, bool muted);
    bool muted(int channel) const;
    void unmuteAll();
    uint64_t writeCount() const { return write_count_; }

private:
    static constexpr double CLOCK = 3579545.0;
    uint32_t sample_rate_ = 44100;
    bool enhanced_ = false;
    std::array<bool, 5> muted_{};
    uint64_t write_count_ = 0;
    __SCC* chip_ = nullptr;
};

class Y8950Device {
public:
    void reset(uint32_t sample_rate);
    void select(uint8_t reg) { selected_ = reg; }
    void write(uint8_t value);
    uint8_t readStatus() const { return status_; }
    uint8_t readData() const { return registers_[selected_]; }
    float sample();
    void setMuted(int channel, bool muted);
    bool muted(int channel) const;
    void unmuteAll() { muted_.fill(false); }
    uint64_t writeCount() const { return write_count_; }

private:
    enum class EnvelopeStage : uint8_t { Off, Attack, Decay, Sustain, Release };
    struct Operator {
        double phase = 0.0;
        double envelope = 0.0;
        double previous = 0.0;
        double last = 0.0;
        bool key = false;
        EnvelopeStage stage = EnvelopeStage::Off;
    };

    static int slotForOffset(uint8_t offset);
    static uint8_t offsetForSlot(int slot);
    void setKey(int channel, bool on);
    void setOperatorKey(int slot, bool on);
    void updateRhythmKeys();
    double operatorSample(int slot, int channel, double phase_modulation, double feedback);
    double envelopeStep(Operator& op, int slot, int channel);
    double waveform(double phase, uint8_t waveform_id) const;

    static constexpr double CLOCK = 3579545.0;
    uint32_t sample_rate_ = 44100;
    std::array<uint8_t, 256> registers_{};
    std::array<Operator, 18> operators_{};
    std::array<bool, 9> muted_{};
    uint8_t selected_ = 0;
    uint8_t status_ = 0;
    double lfo_phase_ = 0.0;
    uint32_t noise_lfsr_ = 0x1ffff;
    uint64_t write_count_ = 0;
};

} // namespace tinyksp
