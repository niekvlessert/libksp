#include "yamaha_chips.h"
#include "libvgm_ymf278b.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iterator>

namespace tinyksp {
namespace {
constexpr double PI2 = 6.283185307179586476925286766559;
constexpr std::array<double, 16> MULT = {
    0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0,
    8.0, 9.0, 10.0, 10.0, 12.0, 12.0, 15.0, 15.0
};
constexpr std::array<Ym2413Device::Patch, 16> PRESETS = {{
    {0x21,0x01,0x1e,0x07,0xf0,0xf0,0x77,0x17},
    {0x13,0x41,0x16,0x05,0xd2,0xf2,0x13,0x13},
    {0x13,0x01,0x1a,0x07,0xf0,0xd4,0x00,0x23},
    {0x11,0x01,0x0e,0x04,0xf2,0xf4,0x00,0x13},
    {0x21,0x01,0x16,0x06,0xf0,0xf0,0x00,0x17},
    {0x22,0x21,0x1e,0x05,0xf0,0x72,0x00,0x16},
    {0x31,0x22,0x16,0x06,0x91,0x61,0x00,0x17},
    {0x21,0x61,0x1d,0x07,0x82,0xf1,0x00,0x17},
    {0x23,0x21,0x2d,0x07,0xc1,0xf1,0x00,0x17},
    {0x61,0x61,0x1b,0x03,0xa1,0xf2,0x00,0x17},
    {0x61,0x61,0x0b,0x04,0xb0,0xf0,0x00,0x16},
    {0x21,0x61,0x0d,0x05,0x71,0xf1,0x00,0x17},
    {0x21,0x21,0x1d,0x07,0x82,0x82,0x00,0x17},
    {0x21,0x21,0x2d,0x06,0xf0,0xf0,0x00,0x17},
    {0x21,0x21,0x1d,0x05,0xf0,0xf0,0x00,0x17},
    {0x21,0x21,0x0d,0x07,0xf0,0xf0,0x00,0x17}
}};

double rateCoeff(int rate, uint32_t sample_rate, bool attack) {
    if (rate <= 0) return 0.0;
    const double seconds = (attack ? 3.5 : 9.0) * std::pow(0.5, rate * 0.58);
    return 1.0 - std::exp(-1.0 / (std::max(0.00025, seconds) * sample_rate));
}

uint32_t read24be(const uint8_t* p) {
    return (uint32_t(p[0]) << 16) | (uint32_t(p[1]) << 8) | p[2];
}

template<typename Emit>
bool decodeNitroImaAdpcmCore(const uint8_t* src, size_t source_bytes,
                             size_t decoded_samples, Emit emit) {
    static constexpr int STEP[89] = {
        7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,
        60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,
        337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,
        1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,
        4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,
        15289,16818,18500,20350,22385,24623,27086,29794,32767
    };
    static constexpr int INDEX[8] = {-1,-1,-1,-1,2,4,6,8};
    if (!src || source_bytes < 4 || decoded_samples == 0) return false;
    int predictor = int(int16_t(uint16_t(src[0]) | (uint16_t(src[1]) << 8)));
    int step_index = src[2];
    if (step_index > 88) return false;
    size_t out_index = 0;
    emit(out_index++, int16_t(predictor));
    for (size_t i = 4; i < source_bytes && out_index < decoded_samples; ++i) {
        for (int half = 0; half < 2 && out_index < decoded_samples; ++half) {
            const int nibble = half ? (src[i] >> 4) : (src[i] & 0x0f);
            const int step = STEP[step_index];
            int delta = step >> 3;
            if (nibble & 1) delta += step >> 2;
            if (nibble & 2) delta += step >> 1;
            if (nibble & 4) delta += step;
            predictor += (nibble & 8) ? -delta : delta;
            predictor = std::max(-32768, std::min(32767, predictor));
            step_index += INDEX[nibble & 7];
            step_index = std::max(0, std::min(88, step_index));
            emit(out_index++, int16_t(predictor));
        }
    }
    return out_index == decoded_samples;
}

bool decodeNitroImaAdpcm16(const uint8_t* src, size_t source_bytes,
                           uint8_t* dst, size_t decoded_samples) {
    if (!dst) return false;
    return decodeNitroImaAdpcmCore(src, source_bytes, decoded_samples,
        [&](size_t sample_index, int16_t sample) {
            const uint16_t value = uint16_t(sample);
            dst[sample_index * 2] = uint8_t(value >> 8);
            dst[sample_index * 2 + 1] = uint8_t(value);
        });
}

int16_t quantize12(int16_t sample) {
    const int value = int(sample);
    int quantized = value >= 0 ? ((value + 8) / 16) * 16
                               : -(((-value + 8) / 16) * 16);
    quantized = std::max(-32768, std::min(32752, quantized));
    return int16_t(quantized);
}

bool decodeNitroImaAdpcm12(const uint8_t* src, size_t source_bytes,
                           uint8_t* dst, size_t decoded_samples) {
    if (!dst) return false;
    int16_t first = 0;
    bool have_first = false;
    size_t packed_pos = 0;
    const bool ok = decodeNitroImaAdpcmCore(src, source_bytes, decoded_samples,
        [&](size_t, int16_t sample) {
            const int16_t q = quantize12(sample);
            if (!have_first) {
                first = q;
                have_first = true;
                return;
            }
            const uint16_t a = uint16_t(first);
            const uint16_t b = uint16_t(q);
            dst[packed_pos++] = uint8_t(a >> 8);
            dst[packed_pos++] = uint8_t(((b >> 4) & 0xf0) | ((a >> 4) & 0x0f));
            dst[packed_pos++] = uint8_t(b >> 8);
            have_first = false;
        });
    if (!ok) return false;
    if (have_first) {
        const uint16_t a = uint16_t(first);
        dst[packed_pos++] = uint8_t(a >> 8);
        dst[packed_pos++] = uint8_t((a >> 4) & 0x0f);
        dst[packed_pos++] = 0;
    }
    return packed_pos == ((decoded_samples + 1u) / 2u) * 3u;
}
}

void Ym2413Device::reset(uint32_t sample_rate) {
    sample_rate_ = sample_rate ? sample_rate : 44100;
    registers_.fill(0);
    operators_.fill({});
    rhythm_.fill({});
    muted_.fill(false);
    selected_ = 0;
    rhythm_keys_ = 0;
    lfo_phase_ = 0.0;
    noise_lfsr_ = 0x1ffff;
    write_count_ = 0;
    std::string ignored;
    (void)libvgm_.reset(sample_rate_, &ignored);
}

Ym2413Device::Patch Ym2413Device::patchForChannel(int channel) const {
    const uint8_t instrument = (registers_[0x30 + channel] >> 4) & 15;
    if (instrument != 0) return PRESETS[instrument];
    Patch p;
    p.mod_flags = registers_[0]; p.car_flags = registers_[1];
    p.mod_level = registers_[2] & 0x3f; p.feedback = registers_[3] & 7;
    p.mod_ad = registers_[4]; p.car_ad = registers_[5];
    p.mod_sr = registers_[6]; p.car_sr = registers_[7];
    return p;
}

void Ym2413Device::setKey(int channel, bool on) {
    for (int op_index = 0; op_index < 2; ++op_index) {
        Operator& op = operators_[static_cast<size_t>(channel * 2 + op_index)];
        if (on && !op.key) {
            op.key = true; op.stage = Stage::Attack; op.envelope = 0.0;
        } else if (!on && op.key) {
            op.key = false; if (op.stage != Stage::Off) op.stage = Stage::Release;
        }
    }
}

void Ym2413Device::write(uint8_t value) {
    const uint8_t reg = selected_ & 0x3f;
    const uint8_t old = registers_[reg];
    registers_[reg] = value;
    ++write_count_;
    libvgm_.write(reg, value);
    if (reg >= 0x20 && reg <= 0x28 && ((old ^ value) & 0x10))
        setKey(reg - 0x20, (value & 0x10) != 0);
    if (reg == 0x0e) {
        const bool old_rhythm = (old & 0x20) != 0;
        const bool new_rhythm = (value & 0x20) != 0;
        if (!new_rhythm) {
            rhythm_keys_ = 0;
        } else {
            const uint8_t new_keys = value & 0x1f;
            const uint8_t rising = new_keys & uint8_t(~rhythm_keys_);
            if (rising & 0x10) triggerRhythmVoice(0); // bass drum
            if (rising & 0x08) triggerRhythmVoice(1); // snare
            if (rising & 0x04) triggerRhythmVoice(2); // tom
            if (rising & 0x02) triggerRhythmVoice(3); // cymbal
            if (rising & 0x01) triggerRhythmVoice(4); // hi-hat
            rhythm_keys_ = new_keys;
            if (!old_rhythm) {
                // Channels 6-8 stop being melodic operators in rhythm mode.
                setKey(6, false);
                setKey(7, false);
                setKey(8, false);
            }
        }
    }
}

void Ym2413Device::triggerRhythmVoice(int voice) {
    if (voice < 0 || voice >= static_cast<int>(rhythm_.size())) return;
    RhythmVoice& v = rhythm_[static_cast<size_t>(voice)];
    v.age = 0.0;
    v.phase = 0.0;
    v.phase2 = 0.0;
    v.active = true;
}

double Ym2413Device::rhythmLevel(uint8_t attenuation) const {
    // OPLL rhythm volume nibbles are logarithmic attenuation controls.  A
    // 1.5 dB approximation keeps the five voices useful in a mixed KSP while
    // retaining the expected 0=loud, 15=quiet ordering.
    return std::pow(10.0, -(double(attenuation & 15) * 1.5) / 20.0);
}

double Ym2413Device::rhythmSample() {
    const double dt = 1.0 / sample_rate_;
    const double noise = (noise_lfsr_ & 1u) ? 1.0 : -1.0;
    double out = 0.0;

    auto channelFrequency = [&](int ch) {
        const uint16_t fnum = uint16_t(registers_[0x10 + ch] |
                                       ((registers_[0x20 + ch] & 1) << 8));
        const int block = (registers_[0x20 + ch] >> 1) & 7;
        return (CLOCK / 72.0) * fnum * std::pow(2.0, block - 1) / 262144.0;
    };

    // Bass drum: pitched sine with a short downward sweep and click.  The
    // base pitch comes from melodic channel 6, as on the YM2413.
    {
        RhythmVoice& v = rhythm_[0];
        if (v.active) {
            const double env = std::exp(-v.age / 0.115);
            if (env < 0.0005) v.active = false;
            else {
                const double base = std::max(45.0, channelFrequency(6));
                const double freq = base * (0.72 + 1.55 * std::exp(-v.age / 0.025));
                v.phase += freq * dt;
                v.phase -= std::floor(v.phase);
                const double click = v.age < 0.006 ? noise * (1.0 - v.age / 0.006) * 0.18 : 0.0;
                if (!muted_[6]) out += (std::sin(PI2 * v.phase) * 0.92 + click) * env *
                                       rhythmLevel(registers_[0x36] & 15) * 1.45;
                v.age += dt;
            }
        }
    }

    // Snare: broad noise with a low resonant component.  FM-PAC channel 8
    // controls both snare and hi-hat muting.
    {
        RhythmVoice& v = rhythm_[1];
        if (v.active) {
            const double env = std::exp(-v.age / 0.082);
            if (env < 0.0005) v.active = false;
            else {
                const double base = std::max(150.0, channelFrequency(7) * 0.72);
                v.phase += base * dt;
                v.phase -= std::floor(v.phase);
                const double body = std::sin(PI2 * v.phase) * 0.27;
                const double shaped_noise = noise * (0.80 + 0.20 * std::sin(PI2 * v.phase * 3.0));
                if (!muted_[7]) out += (shaped_noise * 0.88 + body) * env *
                                       rhythmLevel(registers_[0x37] & 15) * 1.10;
                v.age += dt;
            }
        }
    }

    // Tom: resonant sine with a gentler pitch sweep, using channel 8 pitch.
    {
        RhythmVoice& v = rhythm_[2];
        if (v.active) {
            const double env = std::exp(-v.age / 0.155);
            if (env < 0.0005) v.active = false;
            else {
                const double base = std::max(90.0, channelFrequency(8) * 0.60);
                const double freq = base * (0.86 + 0.58 * std::exp(-v.age / 0.045));
                v.phase += freq * dt;
                v.phase -= std::floor(v.phase);
                if (!muted_[8]) out += std::sin(PI2 * v.phase) * env *
                                       rhythmLevel(registers_[0x38] >> 4) * 1.18;
                v.age += dt;
            }
        }
    }

    // Cymbal: inharmonic metallic partials plus a modest noise component.
    {
        RhythmVoice& v = rhythm_[3];
        if (v.active) {
            const double env = std::exp(-v.age / 0.34);
            if (env < 0.0005) v.active = false;
            else {
                const double base = std::max(170.0, channelFrequency(8));
                v.phase += base * 2.37 * dt;
                v.phase2 += base * 3.91 * dt;
                v.phase -= std::floor(v.phase);
                v.phase2 -= std::floor(v.phase2);
                const double metal = (std::sin(PI2 * v.phase) +
                                      std::sin(PI2 * v.phase2) * 0.72 +
                                      std::sin(PI2 * (v.phase * 1.618 + v.phase2 * 0.37)) * 0.46) / 2.18;
                if (!muted_[8]) out += (metal * 0.82 + noise * 0.20) * env *
                                       rhythmLevel(registers_[0x38] & 15) * 0.88;
                v.age += dt;
            }
        }
    }

    // Hi-hat: very short high-frequency metallic/noise burst.
    {
        RhythmVoice& v = rhythm_[4];
        if (v.active) {
            const double env = std::exp(-v.age / 0.038);
            if (env < 0.0005) v.active = false;
            else {
                const double base = std::max(230.0, channelFrequency(7));
                v.phase += base * 7.1 * dt;
                v.phase2 += base * 10.7 * dt;
                v.phase -= std::floor(v.phase);
                v.phase2 -= std::floor(v.phase2);
                const double metal = ((v.phase < 0.5 ? 1.0 : -1.0) * 0.45 +
                                      (v.phase2 < 0.5 ? 1.0 : -1.0) * 0.35 + noise * 0.55) / 1.35;
                if (!muted_[7]) out += metal * env * rhythmLevel(registers_[0x37] >> 4) * 0.72;
                v.age += dt;
            }
        }
    }
    return out;
}

double Ym2413Device::envelope(Operator& op, uint8_t ad, uint8_t sr,
                              bool sustain_hold, int block) {
    const int boost = block >> 1;
    const int attack = std::min(15, int(ad >> 4) + boost);
    const int decay = std::min(15, int(ad & 15) + boost);
    const int sustain_level = (sr >> 4) & 15;
    const int release = std::min(15, int(sr & 15) + boost);
    const double sustain = sustain_level == 15 ? 0.0 : std::pow(10.0, -(sustain_level * 3.0) / 20.0);
    switch (op.stage) {
    case Stage::Attack:
        op.envelope += (1.0 - op.envelope) * rateCoeff(attack, sample_rate_, true) * 3.5;
        if (op.envelope >= 0.999) { op.envelope = 1.0; op.stage = Stage::Decay; }
        break;
    case Stage::Decay:
        op.envelope += (sustain - op.envelope) * rateCoeff(decay, sample_rate_, false);
        if (op.envelope <= sustain + 0.001) { op.envelope = sustain; op.stage = Stage::Sustain; }
        break;
    case Stage::Sustain:
        if (!sustain_hold) {
            op.envelope += (0.0 - op.envelope) * rateCoeff(release ? release : decay, sample_rate_, false) * 0.3;
            if (op.envelope < 1e-5) { op.envelope = 0.0; op.stage = Stage::Off; }
        }
        break;
    case Stage::Release:
        op.envelope += (0.0 - op.envelope) * rateCoeff(release ? release : 5, sample_rate_, false);
        if (op.envelope < 1e-5) { op.envelope = 0.0; op.stage = Stage::Off; }
        break;
    case Stage::Off: op.envelope = 0.0; break;
    }
    return op.envelope;
}

double Ym2413Device::opSample(Operator& op, double frequency, uint8_t flags,
                              uint8_t level, uint8_t ad, uint8_t sr,
                              bool sustain_hold, double modulation,
                              double feedback, int block) {
    double f = frequency * MULT[flags & 15];
    if (flags & 0x40) f *= 1.0 + 0.006 * std::sin(PI2 * lfo_phase_ * 6.1);
    op.phase += f / sample_rate_;
    op.phase -= std::floor(op.phase);
    double wave = std::sin(PI2 * (op.phase + modulation + feedback));
    const double amp = std::pow(10.0, -(level * 0.75) / 20.0);
    if (flags & 0x80) wave *= 0.88 + 0.12 * std::sin(PI2 * lfo_phase_ * 3.7);
    const double out = wave * envelope(op, ad, sr, sustain_hold, block) * amp;
    op.previous = op.last; op.last = out;
    return out;
}

float Ym2413Device::sample() {
    if (libvgm_.ready()) return libvgm_.sample();
    lfo_phase_ += 1.0 / sample_rate_;
    if (lfo_phase_ >= 1.0) lfo_phase_ -= 1.0;
    const uint32_t bit = ((noise_lfsr_ >> 0) ^ (noise_lfsr_ >> 3)) & 1u;
    noise_lfsr_ = (noise_lfsr_ >> 1) | (bit << 16);
    double mix = 0.0;
    const bool rhythm_mode = (registers_[0x0e] & 0x20) != 0;
    for (int ch = 0; ch < 9; ++ch) {
        if (rhythm_mode && ch >= 6) continue;
        const uint16_t fnum = uint16_t(registers_[0x10 + ch] | ((registers_[0x20 + ch] & 1) << 8));
        const int block = (registers_[0x20 + ch] >> 1) & 7;
        const double freq = (CLOCK / 72.0) * fnum * std::pow(2.0, block - 1) / 262144.0;
        const Patch p = patchForChannel(ch);
        Operator& mod = operators_[static_cast<size_t>(ch * 2)];
        Operator& car = operators_[static_cast<size_t>(ch * 2 + 1)];
        const double fb = p.feedback ? (mod.last + mod.previous) * std::ldexp(1.0, int(p.feedback) - 9) : 0.0;
        const bool sustain = (registers_[0x20 + ch] & 0x20) != 0;
        const double m = opSample(mod, freq, p.mod_flags, p.mod_level, p.mod_ad, p.mod_sr, sustain, 0.0, fb, block);
        const uint8_t carrier_level = uint8_t((registers_[0x30 + ch] & 15) * 4);
        double v = opSample(car, freq, p.car_flags, carrier_level, p.car_ad, p.car_sr, sustain, m * 0.7, 0.0, block);
        if (!muted_[static_cast<size_t>(ch)]) mix += v;
    }
    if (rhythm_mode) mix += rhythmSample();
    return static_cast<float>(mix * 0.23);
}

void Ym2413Device::setMuted(int channel, bool muted) {
    if (channel >= 0 && channel < 9) muted_[static_cast<size_t>(channel)] = muted;
    uint32_t mask = 0;
    for (int i = 0; i < static_cast<int>(muted_.size()); ++i)
        if (muted_[static_cast<size_t>(i)]) mask |= 1u << i;
    libvgm_.setMuteMask(mask);
}

void Ym2413Device::unmuteAll() {
    muted_.fill(false);
    libvgm_.setMuteMask(0);
}
bool Ym2413Device::muted(int channel) const {
    return channel >= 0 && channel < 9 && muted_[static_cast<size_t>(channel)];
}

void Opl3Device::reset(uint32_t sample_rate) {
    low_.reset(sample_rate); high_.reset(sample_rate); write_count_ = 0;
}
void Opl3Device::setMuted(int channel, bool muted) {
    if (channel < 0 || channel >= 18) return;
    (channel < 9 ? low_ : high_).setMuted(channel % 9, muted);
}
bool Opl3Device::muted(int channel) const {
    if (channel < 0 || channel >= 18) return false;
    return (channel < 9 ? low_ : high_).muted(channel % 9);
}
void Opl3Device::unmuteAll() { low_.unmuteAll(); high_.unmuteAll(); }


Opl4Device::Opl4Device() : libvgm_(std::make_unique<LibVgmYmf278b>()) {}
Opl4Device::~Opl4Device() = default;

void Opl4Device::selectFmLow(uint8_t reg) {
    fm_.selectLow(reg);
    if (libvgm_) libvgm_->write(0, reg);
}
void Opl4Device::selectFmHigh(uint8_t reg) {
    fm_.selectHigh(reg);
    if (libvgm_) libvgm_->write(2, reg);
}
void Opl4Device::writeFmLow(uint8_t value) {
    fm_.writeLow(value);
    if (libvgm_) libvgm_->write(1, value);
}
void Opl4Device::writeFmHigh(uint8_t value) {
    fm_.writeHigh(value);
    if (libvgm_) libvgm_->write(3, value);
}
void Opl4Device::selectWave(uint8_t reg) {
    selected_wave_ = reg;
    if (libvgm_) libvgm_->write(4, reg);
}
uint8_t Opl4Device::readWaveStatus() const {
    return libvgm_ ? libvgm_->read(0) : 0;
}

void Opl4Device::reset(uint32_t sample_rate) {
    sample_rate_ = sample_rate ? sample_rate : 44100;
    fm_.reset(sample_rate_);
    wave_registers_.fill(0);
    voices_.fill({});
    pcm_muted_.fill(false);
    headers_.fill({});
    custom_lengths_.fill(0);
    if (memory_.size() != MEMORY_SIZE) memory_.assign(MEMORY_SIZE, 0);
    else std::fill(memory_.begin() + std::min<size_t>(memory_.size(), 0x200000), memory_.end(), 0);
    selected_wave_ = 0; memory_address_ = 0; memory_write_enabled_ = false;
    custom_sample_count_ = 0; pcm_write_count_ = 0;
    if (libvgm_) {
        libvgm_->reset(sample_rate_);
        libvgm_->setDsReferenceMode(false);
        if (memory_.size() >= 0x400000u)
            libvgm_->loadRam(memory_.data() + 0x200000u, 0x200000u);
    }
}

bool Opl4Device::loadYrw801Rom(const std::string& path, std::string& error) {
    std::ifstream in(path, std::ios::binary);
    if (!in) { error = "cannot open YRW801 ROM"; return false; }
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)), {});
    if (data.size() < 2u * 1024u * 1024u) { error = "YRW801 ROM must be at least 2 MiB"; return false; }
    if (memory_.size() != MEMORY_SIZE) memory_.assign(MEMORY_SIZE, 0);
    std::copy_n(data.begin(), 2u * 1024u * 1024u, memory_.begin());
    rom_loaded_ = true;
    if (libvgm_ && !libvgm_->loadRom(data.data(), 2u * 1024u * 1024u, &error)) return false;
    return true;
}

bool Opl4Device::loadMwk(const std::vector<uint8_t>& data, std::string& error) {
    return decodeMwk(data, error);
}

bool Opl4Device::decodeMwk(const std::vector<uint8_t>& data, std::string& error) {
    size_t pos = 0;
    auto take = [&](size_t n, const uint8_t*& p) -> bool {
        if (n > data.size() - std::min(pos, data.size())) return false;
        p = data.data() + pos; pos += n; return true;
    };
    const uint8_t* p = nullptr;
    if (!take(5, p) || std::memcmp(p, "MBMS\x10", 5) != 0) { error = "invalid MWK signature"; return false; }
    if (!take(1, p)) { error = "truncated MWK"; return false; }
    const uint8_t version = p[0];
    if (version != 0x0c && version != 0x0d && version != 0x0e && version != 0x0f) { error = "unsupported MWK revision"; return false; }
    if (!take(3, p) || !take(1, p)) { error = "truncated MWK header"; return false; }
    const uint8_t wave_count = p[0];
    if (wave_count > 48) { error = "invalid MWK wave count"; return false; }
    if (!take(64, p)) { error = "truncated MWK flags"; return false; }
    std::array<uint8_t,64> flags{}; std::copy_n(p,64,flags.begin());
    if (!take(size_t(wave_count) * 25, p)) { error = "truncated MWK patch table"; return false; }
    if (version == 0x0c && !take(size_t(wave_count) * 16, p)) { error = "truncated MWK edit table"; return false; }
    if (memory_.size() != MEMORY_SIZE) memory_.assign(MEMORY_SIZE, 0);
    std::fill(memory_.begin() + 0x200000, memory_.end(), 0);
    headers_.fill({}); custom_lengths_.fill(0); custom_sample_count_ = 0;
    uint32_t sample_address = 0x200300;
    for (int tone = 0; tone < 64; ++tone) {
        const uint8_t flag = flags[static_cast<size_t>(tone)];
        if (!(flag & 1)) continue;
        if (version == 0x0c && !take(16, p)) { error = "truncated MWK tone edit data"; return false; }
        if (!take(13, p)) { error = "truncated MWK tone header"; return false; }
        std::array<uint8_t,12> out{};
        out[1] = uint8_t(sample_address >> 8); out[2] = uint8_t(sample_address);
        uint32_t payload_length = 0;
        const uint8_t source_format = uint8_t((flag >> 6) & 3);
        const bool nitro_adpcm16 = version == 0x0e && source_format == 3;
        const bool nitro_adpcm12 = version == 0x0f && source_format == 3;
        const bool nitro_adpcm = nitro_adpcm16 || nitro_adpcm12;
        const uint8_t opl4_format_bits = nitro_adpcm12 ? uint8_t(1u << 6)
            : nitro_adpcm16 ? uint8_t(2u << 6) : uint8_t(flag & 0xc0);
        if (flag & 0x20) out[0] = uint8_t(opl4_format_bits | p[12]);
        else {
            out[0] = uint8_t(opl4_format_bits | ((sample_address >> 16) & 0x3f));
            payload_length = uint32_t(p[11]) | (uint32_t(p[12]) << 8);
        }
        std::copy_n(p + 2, 9, out.begin() + 3);
        // MWK stores the sample payload size in bytes, while the YMF278B wave
        // header stores loop/end positions in decoded samples. These differ for
        // 12-bit (3 bytes per 2 samples) and 16-bit (2 bytes per sample) waves.
        const uint16_t complement = uint16_t((uint16_t(out[5]) << 8) | out[6]);
        uint32_t sample_count = uint16_t(0u - complement);
        if (!sample_count) sample_count = 65536;
        // MoonSound RAM wave headers occupy wave numbers 384..511.
        // Do not overwrite standard YRW801 ROM wave numbers 0..383.
        headers_[static_cast<size_t>(384 + tone)] = out;
        custom_lengths_[static_cast<size_t>(384 + tone)] = payload_length ? sample_count : 0;
        const uint32_t header_address = 0x200000u + uint32_t(tone) * 12u;
        if (header_address + 12 > memory_.size()) { error = "MWK header outside OPL4 RAM"; return false; }
        std::copy(out.begin(), out.end(), memory_.begin() + header_address);
        if (payload_length) {
            if (nitro_adpcm) {
                const uint32_t decoded_bytes = nitro_adpcm12
                    ? ((sample_count + 1u) / 2u) * 3u : sample_count * 2u;
                const uint32_t expected_samples = payload_length >= 4 ? 1u + (payload_length - 4u) * 2u : 0u;
                if (expected_samples != sample_count) { error = "Nitro ADPCM sample length does not match MWK end marker"; return false; }
                if (!take(payload_length, p) || sample_address + decoded_bytes > memory_.size()) { error = "truncated or oversized Nitro ADPCM sample"; return false; }
                const bool decoded = nitro_adpcm12
                    ? decodeNitroImaAdpcm12(p, payload_length, memory_.data() + sample_address, sample_count)
                    : decodeNitroImaAdpcm16(p, payload_length, memory_.data() + sample_address, sample_count);
                if (!decoded) { error = "invalid Nitro IMA ADPCM sample"; return false; }
                sample_address += decoded_bytes;
            } else {
                const uint8_t format = source_format;
                const uint32_t required = format == 0 ? sample_count
                    : format == 1 ? ((sample_count + 1) / 2) * 3
                    : format == 2 ? sample_count * 2 : 0;
                if (format == 3 || payload_length < required) { error = "invalid MWK sample format or payload size"; return false; }
                if (!take(payload_length, p) || sample_address + payload_length > memory_.size()) { error = "truncated or oversized MWK sample"; return false; }
                std::copy_n(p, payload_length, memory_.begin() + sample_address);
                sample_address += payload_length;
            }
        }
        ++custom_sample_count_;
    }
    if (libvgm_) libvgm_->setDsReferenceMode(version == 0x0e || version == 0x0f);
    if (libvgm_ && !libvgm_->loadRam(memory_.data() + 0x200000u,
                                      memory_.size() - 0x200000u, &error))
        return false;
    if (libvgm_) {
        // MWK wave numbers 384+ use the 0x200000 RAM header bank.
        libvgm_->write(4, 0x02);
        libvgm_->write(5, 0x10);
    }
    return true;
}

uint8_t Opl4Device::memoryRead(uint32_t address) const {
    return address < memory_.size() ? memory_[address] : 0;
}
void Opl4Device::memoryWrite(uint32_t address, uint8_t value) {
    if (memory_write_enabled_ && address < memory_.size()) memory_[address] = value;
}

void Opl4Device::writeWave(uint8_t value) {
    if (libvgm_) {
        libvgm_->write(4, selected_wave_);
        libvgm_->write(5, value);
    }
    const uint8_t reg = selected_wave_;
    wave_registers_[reg] = value;
    ++pcm_write_count_;
    if (reg == 0x02) memory_write_enabled_ = (value & 1) != 0;
    else if (reg == 0x03) memory_address_ = (memory_address_ & 0x00ffffu) | (uint32_t(value & 0x3f) << 16);
    else if (reg == 0x04) memory_address_ = (memory_address_ & 0x3f00ffu) | (uint32_t(value) << 8);
    else if (reg == 0x05) memory_address_ = (memory_address_ & 0x3fff00u) | value;
    else if (reg == 0x06) { memoryWrite(memory_address_, value); memory_address_ = (memory_address_ + 1) & 0x3fffff; }
    else updateVoiceRegister(reg, value);
}

uint8_t Opl4Device::readWaveData() {
    if (libvgm_ && libvgm_->ready()) return libvgm_->read(5);
    if (selected_wave_ == 0x06) {
        const uint8_t v = memoryRead(memory_address_);
        memory_address_ = (memory_address_ + 1) & 0x3fffff;
        return v;
    }
    return wave_registers_[selected_wave_];
}

void Opl4Device::updateVoiceRegister(uint8_t reg, uint8_t value) {
    int slot = -1;
    if (reg >= 0x08 && reg < 0x20) { slot = reg - 0x08; voices_[slot].wave = uint16_t((voices_[slot].wave & 0x100) | value); reloadWave(slot); }
    else if (reg >= 0x20 && reg < 0x38) {
        slot = reg - 0x20;
        // YMF278B register 20h+n: bit 0 is wave-number bit 8;
        // bits 1..7 are F-number bits 0..6.
        voices_[slot].wave = uint16_t((voices_[slot].wave & 0x0ff) | ((value & 0x01) << 8));
        voices_[slot].fnum = uint16_t((voices_[slot].fnum & 0x380) | (value >> 1));
        reloadWave(slot);
    }
    else if (reg >= 0x38 && reg < 0x50) { slot = reg - 0x38; voices_[slot].fnum = uint16_t((voices_[slot].fnum & 0x07f) | ((value & 7) << 7)); int o = (value >> 4) & 15; voices_[slot].octave = int8_t(o >= 8 ? o - 16 : o); }
    else if (reg >= 0x50 && reg < 0x68) { slot = reg - 0x50; voices_[slot].level = value >> 1; }
    else if (reg >= 0x68 && reg < 0x80) { slot = reg - 0x68; voices_[slot].pan = value & 15; setKey(slot, (value & 0x80) != 0, (value & 0x40) != 0); }
    else if (reg >= 0x98 && reg < 0xb0) { slot = reg - 0x98; voices_[slot].ar = value >> 4; voices_[slot].d1r = value & 15; }
    else if (reg >= 0xb0 && reg < 0xc8) { slot = reg - 0xb0; voices_[slot].dl = value >> 4; voices_[slot].d2r = value & 15; }
    else if (reg >= 0xc8 && reg < 0xe0) { slot = reg - 0xc8; voices_[slot].rc = value >> 4; voices_[slot].rr = value & 15; }
    else if (reg >= 0xe0 && reg < 0xf8) { slot = reg - 0xe0; voices_[slot].am = value & 7; }
    (void)slot;
}

void Opl4Device::reloadWave(int slot) {
    Voice& v = voices_[static_cast<size_t>(slot)];
    std::array<uint8_t,12> h = headers_[std::min<size_t>(v.wave, headers_.size()-1)];
    bool empty = std::all_of(h.begin(), h.end(), [](uint8_t x){return x==0;});
    if (empty && v.wave < 384 && rom_loaded_) {
        const uint32_t addr = uint32_t(v.wave) * 12u;
        if (addr + 12 <= memory_.size()) std::copy_n(memory_.begin() + addr, 12, h.begin());
    }
    v.format = h[0] >> 6;
    v.start = read24be(h.data()) & 0x3fffff;
    v.loop = (uint32_t(h[3]) << 8) | h[4];
    const size_t idx = std::min<size_t>(v.wave, custom_lengths_.size()-1);
    uint32_t length = custom_lengths_[idx];
    if (!length) {
        const uint16_t complement = uint16_t((uint16_t(h[5]) << 8) | h[6]);
        length = uint16_t(0u - complement);
        if (!length) length = 65536;
    }
    v.length = length;
}

void Opl4Device::setKey(int slot, bool on, bool damp) {
    Voice& v = voices_[static_cast<size_t>(slot)];
    v.damp = damp;
    if (on && !v.key) { v.key = true; v.position = 0.0; v.envelope = 0.0; v.stage = Stage::Attack; reloadWave(slot); }
    else if (!on && v.key) { v.key = false; v.stage = Stage::Release; }
    if (damp) v.stage = Stage::Release;
}

double Opl4Device::envelopeStep(Voice& v) {
    const double sustain = v.dl == 15 ? 0.0 : std::pow(10.0, -(v.dl * 3.0) / 20.0);
    switch (v.stage) {
    case Stage::Attack:
        v.envelope += (1.0 - v.envelope) * rateCoeff(v.ar, sample_rate_, true) * 4.0;
        if (v.envelope >= .999) { v.envelope = 1; v.stage = Stage::Decay1; }
        break;
    case Stage::Decay1:
        v.envelope += (sustain - v.envelope) * rateCoeff(v.d1r, sample_rate_, false);
        if (v.envelope <= sustain + .001) { v.envelope = sustain; v.stage = Stage::Decay2; }
        break;
    case Stage::Decay2:
        if (v.d2r) v.envelope += (0.0-v.envelope) * rateCoeff(v.d2r, sample_rate_, false) * .2;
        break;
    case Stage::Release:
        v.envelope += (0.0-v.envelope) * rateCoeff(v.rr ? v.rr : 7, sample_rate_, false);
        if (v.envelope < 1e-5) { v.envelope=0; v.stage=Stage::Off; }
        break;
    case Stage::Off: v.envelope=0; break;
    }
    return v.envelope;
}

float Opl4Device::pcmSample(int slot) {
    Voice& v = voices_[static_cast<size_t>(slot)];
    if (v.stage == Stage::Off || v.length == 0) return 0;
    const uint32_t index = static_cast<uint32_t>(v.position);
    if (index >= v.length) {
        if (v.loop < v.length) v.position = v.loop;
        else { v.stage = Stage::Release; v.position = v.length ? v.length-1 : 0; }
    }
    const uint32_t i = static_cast<uint32_t>(v.position);
    double value = 0;
    // YMF278B PCM format: 00=8-bit, 01=12-bit, 10=16-bit.
    if (v.format == 2) {
        const uint32_t a = v.start + i * 2;
        value = int16_t(uint16_t(memoryRead(a) << 8) | memoryRead(a + 1)) / 32768.0;
    } else if (v.format == 1) {
        const uint32_t a = v.start + (i / 2) * 3;
        // 12-bit packing: sample 0 uses byte 0 plus byte 1's low nibble;
        // sample 1 uses byte 2 plus byte 1's high nibble.
        const uint16_t raw = (i & 1)
            ? uint16_t((memoryRead(a + 2) << 4) | (memoryRead(a + 1) >> 4))
            : uint16_t((memoryRead(a) << 4) | (memoryRead(a + 1) & 0x0f));
        value = int16_t(raw << 4) / 32768.0;
    } else {
        value = int8_t(memoryRead(v.start + i)) / 128.0;
    }
    // YMF278B normal pitch is FNUM=0, OCTAVE=1 (44.1 kHz source rate).
    double step = std::pow(2.0, v.octave - 1) * (1024.0 + v.fnum) / 1024.0;
    step *= 44100.0 / sample_rate_;
    v.position += std::max(0.01, step);
    const double level = std::pow(10.0, -(v.level * 0.375) / 20.0);
    return static_cast<float>(value * envelopeStep(v) * level);
}

void Opl4Device::sampleStereo(float& left, float& right) {
    const float fm = fm_.sample();
    if (libvgm_ && libvgm_->ready()) {
        float pcm_left = 0.0f, pcm_right = 0.0f;
        libvgm_->sampleStereo(pcm_left, pcm_right);
        left = fm + pcm_left * 0.55f;
        right = fm + pcm_right * 0.55f;
        return;
    }
    double mix = fm;
    for (int i=0;i<24;++i) if (!pcm_muted_[static_cast<size_t>(i)]) mix += pcmSample(i) * 0.45;
    left = right = static_cast<float>(mix * 0.72);
}

float Opl4Device::sample() {
    float left = 0.0f, right = 0.0f;
    sampleStereo(left, right);
    return (left + right) * 0.5f;
}
void Opl4Device::setPcmMuted(int channel, bool muted) {
    if (channel < 0 || channel >= 24) return;
    pcm_muted_[static_cast<size_t>(channel)] = muted;
    uint32_t mask = 0;
    for (int i = 0; i < 24; ++i)
        if (pcm_muted_[static_cast<size_t>(i)]) mask |= 1u << i;
    if (libvgm_) libvgm_->setMuteMask(mask);
}
bool Opl4Device::pcmMuted(int channel) const { return channel>=0&&channel<24&&pcm_muted_[channel]; }
void Opl4Device::unmuteAll() { fm_.unmuteAll(); pcm_muted_.fill(false);     if (libvgm_) libvgm_->setMuteMask(0);
}

} // namespace tinyksp
