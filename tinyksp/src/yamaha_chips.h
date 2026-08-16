#pragma once

#include "chips.h"
#include "libvgm_ym2413.h"
#include <memory>

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace tinyksp {

// Standalone YM2413/OPLL core used by MSX-MUSIC and FM-PAC engines.
// It implements the native register layout, preset/user instruments,
// 9 melodic channels, rhythm keying, envelopes, feedback and channel muting.
class Ym2413Device {
public:
    Ym2413Device() = default;
    ~Ym2413Device() = default;
    Ym2413Device(const Ym2413Device&) = delete;
    Ym2413Device& operator=(const Ym2413Device&) = delete;

    void reset(uint32_t sample_rate);
    void select(uint8_t reg) { selected_ = reg & 0x3f; }
    void write(uint8_t value);
    uint8_t readStatus() const { return 0; }
    uint8_t readData() const { return registers_[selected_]; }
    float sample();
    void setMuted(int channel, bool muted);
    bool muted(int channel) const;
    void unmuteAll();
    uint64_t writeCount() const { return write_count_; }
    bool rhythmMode() const { return (registers_[0x0e] & 0x20) != 0; }

    struct Patch {
        uint8_t mod_flags = 0, car_flags = 0;
        uint8_t mod_level = 0, feedback = 0;
        uint8_t mod_ad = 0, car_ad = 0;
        uint8_t mod_sr = 0, car_sr = 0;
    };

private:
    enum class Stage : uint8_t { Off, Attack, Decay, Sustain, Release };
    struct Operator {
        double phase = 0.0;
        double envelope = 0.0;
        double last = 0.0;
        double previous = 0.0;
        bool key = false;
        Stage stage = Stage::Off;
    };
    struct RhythmVoice {
        double age = 0.0;
        double phase = 0.0;
        double phase2 = 0.0;
        bool active = false;
    };
    Patch patchForChannel(int channel) const;
    void setKey(int channel, bool on);
    void triggerRhythmVoice(int voice);
    double rhythmSample();
    double rhythmLevel(uint8_t attenuation) const;
    double envelope(Operator& op, uint8_t ad, uint8_t sr, bool sustain_hold, int block);
    double opSample(Operator& op, double frequency, uint8_t flags, uint8_t level,
                    uint8_t ad, uint8_t sr, bool sustain_hold,
                    double modulation, double feedback, int block);

    static constexpr double CLOCK = 3579545.0;
    uint32_t sample_rate_ = 44100;
    std::array<uint8_t, 64> registers_{};
    std::array<Operator, 18> operators_{};
    std::array<RhythmVoice, 5> rhythm_{}; // BD, SD, TOM, CYM, HH
    std::array<bool, 9> muted_{};
    uint8_t selected_ = 0;
    uint8_t rhythm_keys_ = 0;
    double lfo_phase_ = 0.0;
    uint32_t noise_lfsr_ = 0x1ffff;
    uint64_t write_count_ = 0;
    LibVgmYm2413 libvgm_;
};

// OPL3-compatible FM portion of YMF278B. The two banks are represented by
// independent 9-channel OPL engines; this preserves the OPL3 register/port
// contract and gives deterministic 18-channel muting without libkss.
class Opl3Device {
public:
    void reset(uint32_t sample_rate);
    void selectLow(uint8_t reg) { low_.select(reg); }
    void selectHigh(uint8_t reg) { high_.select(reg); }
    void writeLow(uint8_t value) { low_.write(value); ++write_count_; }
    void writeHigh(uint8_t value) { high_.write(value); ++write_count_; }
    uint8_t readStatusLow() const { return low_.readStatus(); }
    uint8_t readStatusHigh() const { return high_.readStatus(); }
    uint8_t readDataLow() const { return low_.readData(); }
    uint8_t readDataHigh() const { return high_.readData(); }
    float sample() { return (low_.sample() + high_.sample()) * 0.78f; }
    void setMuted(int channel, bool muted);
    bool muted(int channel) const;
    void unmuteAll();
    uint64_t writeCount() const { return write_count_; }

private:
    Y8950Device low_;
    Y8950Device high_;
    uint64_t write_count_ = 0;
};

class LibVgmYmf278b;

// Native MoonSound/OPL4 host device. FM uses the OPL3-compatible core above;
// wave-table playback implements the 24-slot YMF278B register map and custom
// MoonBlaster MWK 0Ch/0Dh sample kits. Standard YRW801 ROM data is optional.
class Opl4Device {
public:
    Opl4Device();
    ~Opl4Device();
    Opl4Device(const Opl4Device&) = delete;
    Opl4Device& operator=(const Opl4Device&) = delete;
    void reset(uint32_t sample_rate);
    bool loadMwk(const std::vector<uint8_t>& data, std::string& error);
    bool loadYrw801Rom(const std::string& path, std::string& error);
    bool hasRom() const { return rom_loaded_; }
    bool hasCustomSamples() const { return custom_sample_count_ != 0; }

    void selectFmLow(uint8_t reg);
    void selectFmHigh(uint8_t reg);
    void writeFmLow(uint8_t value);
    void writeFmHigh(uint8_t value);
    uint8_t readFmStatusLow() const { return fm_.readStatusLow(); }
    uint8_t readFmStatusHigh() const { return fm_.readStatusHigh(); }
    uint8_t readFmDataLow() const { return fm_.readDataLow(); }
    uint8_t readFmDataHigh() const { return fm_.readDataHigh(); }

    void selectWave(uint8_t reg);
    void writeWave(uint8_t value);
    uint8_t readWaveStatus() const;
    uint8_t readWaveData();

    float sample();
    void sampleStereo(float& left, float& right);
    void setFmMuted(int channel, bool muted) { fm_.setMuted(channel, muted); }
    bool fmMuted(int channel) const { return fm_.muted(channel); }
    void setPcmMuted(int channel, bool muted);
    bool pcmMuted(int channel) const;
    void unmuteAll();
    uint64_t fmWriteCount() const { return fm_.writeCount(); }
    uint64_t pcmWriteCount() const { return pcm_write_count_; }
    uint16_t pcmWaveNumber(int channel) const {
        return channel >= 0 && channel < 24 ? voices_[static_cast<size_t>(channel)].wave : 0;
    }
    uint16_t pcmFnum(int channel) const {
        return channel >= 0 && channel < 24 ? voices_[static_cast<size_t>(channel)].fnum : 0;
    }
    uint32_t customSampleCount() const { return custom_sample_count_; }

    struct Patch {
        uint8_t mod_flags = 0, car_flags = 0;
        uint8_t mod_level = 0, feedback = 0;
        uint8_t mod_ad = 0, car_ad = 0;
        uint8_t mod_sr = 0, car_sr = 0;
    };

private:
    std::unique_ptr<LibVgmYmf278b> libvgm_;

    enum class Stage : uint8_t { Off, Attack, Decay1, Decay2, Release };
    struct Voice {
        uint16_t wave = 0;
        uint16_t fnum = 0;
        int8_t octave = 0;
        uint8_t level = 127;
        uint8_t pan = 8;
        bool key = false;
        bool damp = false;
        double position = 0.0;
        double envelope = 0.0;
        Stage stage = Stage::Off;
        uint32_t start = 0;
        uint32_t loop = 0;
        uint32_t length = 0;
        uint8_t format = 0;
        uint8_t ar = 15, d1r = 0, dl = 0, d2r = 0, rc = 0, rr = 7, am = 0;
    };

    void updateVoiceRegister(uint8_t reg, uint8_t value);
    void reloadWave(int slot);
    void setKey(int slot, bool on, bool damp);
    double envelopeStep(Voice& voice);
    float pcmSample(int slot);
    uint8_t memoryRead(uint32_t address) const;
    void memoryWrite(uint32_t address, uint8_t value);
    bool decodeMwk(const std::vector<uint8_t>& data, std::string& error);

    static constexpr uint32_t MEMORY_SIZE = 4u * 1024u * 1024u;
    uint32_t sample_rate_ = 44100;
    Opl3Device fm_;
    std::array<uint8_t, 256> wave_registers_{};
    std::array<Voice, 24> voices_{};
    std::array<bool, 24> pcm_muted_{};
    std::array<std::array<uint8_t, 12>, 512> headers_{};
    std::array<uint32_t, 512> custom_lengths_{};
    std::vector<uint8_t> memory_;
    uint8_t selected_wave_ = 0;
    uint32_t memory_address_ = 0;
    bool memory_write_enabled_ = false;
    bool rom_loaded_ = false;
    uint32_t custom_sample_count_ = 0;
    uint64_t pcm_write_count_ = 0;
};

} // namespace tinyksp
