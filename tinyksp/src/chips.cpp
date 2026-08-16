#include "chips.h"
#include "emu2212.h"

#include <algorithm>
#include <cmath>

namespace tinyksp {
namespace {
constexpr std::array<float, 16> PSG_LEVEL = {
    0.0000f, 0.0040f, 0.0057f, 0.0080f,
    0.0113f, 0.0160f, 0.0226f, 0.0320f,
    0.0453f, 0.0640f, 0.0905f, 0.1280f,
    0.1810f, 0.2560f, 0.3620f, 0.5120f
};
}

void PsgDevice::reset(uint32_t sample_rate) {
    sample_rate_ = sample_rate ? sample_rate : 44100;
    registers_.fill(0);
    registers_[7] = 0x3f;
    selected_ = 0;
    tone_phase_.fill(0.0);
    muted_.fill(false);
    noise_phase_ = 0.0;
    noise_lfsr_ = 0x1ffff;
    restartEnvelope();
    std::string ignored;
    (void)libvgm_.reset(sample_rate_, &ignored);
}

void PsgDevice::restartEnvelope() {
    const uint8_t shape = registers_[13] & 0x0f;
    envelope_continue_ = (shape & 0x08) != 0;
    const bool attack = (shape & 0x04) != 0;
    envelope_alternate_ = (shape & 0x02) != 0;
    envelope_hold_ = (shape & 0x01) != 0;
    envelope_step_ = attack ? 0 : 31;
    envelope_direction_ = attack ? 1 : -1;
    envelope_phase_ = 0.0;
    envelope_holding_ = false;
    write_count_ = 0;
}

void PsgDevice::write(uint8_t value) {
    const uint8_t reg = selected_;
    registers_[selected_] = value;
    ++write_count_;
    libvgm_.write(reg, value);
    if (selected_ == 13) restartEnvelope();
}

float PsgDevice::envelopeVolume() {
    uint16_t period = static_cast<uint16_t>(registers_[11] | (registers_[12] << 8));
    if (period == 0) period = 1;
    envelope_phase_ += CLOCK / (256.0 * period * sample_rate_);
    while (envelope_phase_ >= 1.0) {
        envelope_phase_ -= 1.0;
        if (envelope_holding_) continue;
        envelope_step_ += envelope_direction_;
        if (envelope_step_ < 0 || envelope_step_ > 31) {
            if (!envelope_continue_) {
                envelope_step_ = 0;
                envelope_holding_ = true;
            } else if (envelope_hold_) {
                if (envelope_alternate_) envelope_direction_ = -envelope_direction_;
                envelope_step_ = envelope_direction_ > 0 ? 31 : 0;
                envelope_holding_ = true;
            } else {
                if (envelope_alternate_) envelope_direction_ = -envelope_direction_;
                envelope_step_ = envelope_direction_ > 0 ? 0 : 31;
            }
        }
    }
    const int level = std::clamp(envelope_step_ >> 1, 0, 15);
    return PSG_LEVEL[static_cast<size_t>(level)];
}

float PsgDevice::sample() {
    if (libvgm_.ready()) return libvgm_.sample();
    const uint8_t mixer = registers_[7];
    uint8_t noise_period = registers_[6] & 0x1f;
    if (noise_period == 0) noise_period = 1;
    noise_phase_ += CLOCK / (16.0 * noise_period * sample_rate_);
    while (noise_phase_ >= 1.0) {
        noise_phase_ -= 1.0;
        const uint32_t feedback = (noise_lfsr_ ^ (noise_lfsr_ >> 3)) & 1u;
        noise_lfsr_ = (noise_lfsr_ >> 1) | (feedback << 16);
    }
    const bool noise_high = (noise_lfsr_ & 1u) != 0;
    const float envelope = envelopeVolume();
    float mix = 0.0f;
    for (int channel = 0; channel < 3; ++channel) {
        uint16_t period = static_cast<uint16_t>(registers_[channel * 2] |
                                               ((registers_[channel * 2 + 1] & 0x0f) << 8));
        if (period == 0) period = 1;
        tone_phase_[channel] += CLOCK / (16.0 * period * sample_rate_);
        tone_phase_[channel] -= std::floor(tone_phase_[channel]);
        const bool tone_high = tone_phase_[channel] < 0.5;
        const bool tone_gate = (mixer & (1u << channel)) != 0 || tone_high;
        const bool noise_gate = (mixer & (1u << (channel + 3))) != 0 || noise_high;
        if (!muted_[static_cast<size_t>(channel)] && tone_gate && noise_gate) {
            const uint8_t volume = registers_[8 + channel];
            mix += (volume & 0x10) ? envelope : PSG_LEVEL[volume & 0x0f];
        }
    }
    return mix * 0.52f;
}

void PsgDevice::setMuted(int channel, bool muted) {
    if (channel >= 0 && channel < static_cast<int>(muted_.size()))
        muted_[static_cast<size_t>(channel)] = muted;
    uint32_t mask = 0;
    for (int i = 0; i < static_cast<int>(muted_.size()); ++i)
        if (muted_[static_cast<size_t>(i)]) mask |= 1u << i;
    libvgm_.setMuteMask(mask);
}

void PsgDevice::unmuteAll() {
    muted_.fill(false);
    libvgm_.setMuteMask(0);
}

bool PsgDevice::muted(int channel) const {
    return channel >= 0 && channel < static_cast<int>(muted_.size()) &&
           muted_[static_cast<size_t>(channel)];
}

void SccDevice::reset(uint32_t sample_rate, bool enhanced) {
    sample_rate_ = sample_rate ? sample_rate : 44100;
    enhanced_ = enhanced;
    if (!chip_) chip_ = SCC_new(static_cast<uint32_t>(CLOCK), sample_rate_);
    if (chip_) {
        SCC_set_rate(chip_, sample_rate_);
        SCC_set_quality(chip_, 0);
        SCC_set_type(chip_, enhanced_ ? SCC_ENHANCED : SCC_STANDARD);
        SCC_reset(chip_);
    }
    muted_.fill(false);
    if (chip_) SCC_setMask(chip_, 0);
    write_count_ = 0;
}

SccDevice::~SccDevice() {
    SCC_delete(chip_);
    chip_ = nullptr;
}

void SccDevice::setEnhanced(bool enhanced) {
    enhanced_ = enhanced;
    if (chip_) SCC_set_type(chip_, enhanced_ ? SCC_ENHANCED : SCC_STANDARD);
}

void SccDevice::write(uint8_t offset, uint8_t value) {
    ++write_count_;
    if (chip_) SCC_write(chip_, enhanced_ ? 0xb800u + offset : 0x9800u + offset, value);
}

void SccDevice::writeAddress(uint16_t address, uint8_t value) {
    ++write_count_;
    if (chip_) SCC_write(chip_, address, value);
}

uint8_t SccDevice::read(uint8_t offset) const {
    if (!chip_) return 0xff;
    return static_cast<uint8_t>(SCC_read(
        chip_, enhanced_ ? 0xb800u + offset : 0x9800u + offset));
}

float SccDevice::sample() {
    return chip_ ? static_cast<float>(SCC_calc(chip_)) / 32768.0f : 0.0f;
}

void SccDevice::setMuted(int channel, bool muted) {
    if (channel >= 0 && channel < static_cast<int>(muted_.size()))
        muted_[static_cast<size_t>(channel)] = muted;
    uint32_t mask = 0;
    for (int i = 0; i < static_cast<int>(muted_.size()); ++i)
        if (muted_[static_cast<size_t>(i)]) mask |= 1u << i;
    if (chip_) SCC_setMask(chip_, mask);
}

bool SccDevice::muted(int channel) const {
    return channel >= 0 && channel < static_cast<int>(muted_.size()) &&
           muted_[static_cast<size_t>(channel)];
}

void SccDevice::unmuteAll() {
    muted_.fill(false);
    if (chip_) SCC_setMask(chip_, 0);
}

} // namespace tinyksp

namespace tinyksp {
namespace {
constexpr std::array<uint8_t, 9> OPL_OPERATOR_BASE = {0, 1, 2, 8, 9, 10, 16, 17, 18};
constexpr std::array<double, 16> OPL_MULTIPLIER = {
    0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0,
    8.0, 9.0, 10.0, 10.0, 12.0, 12.0, 15.0, 15.0
};
constexpr double TWO_PI = 6.283185307179586476925286766559;
}

int Y8950Device::slotForOffset(uint8_t offset) {
    offset &= 0x1f;
    for (int channel = 0; channel < 9; ++channel) {
        if (offset == OPL_OPERATOR_BASE[static_cast<size_t>(channel)]) return channel * 2;
        if (offset == static_cast<uint8_t>(OPL_OPERATOR_BASE[static_cast<size_t>(channel)] + 3))
            return channel * 2 + 1;
    }
    return -1;
}

uint8_t Y8950Device::offsetForSlot(int slot) {
    const int channel = slot / 2;
    return static_cast<uint8_t>(OPL_OPERATOR_BASE[static_cast<size_t>(channel)] + (slot & 1 ? 3 : 0));
}

void Y8950Device::reset(uint32_t sample_rate) {
    sample_rate_ = sample_rate ? sample_rate : 44100;
    registers_.fill(0);
    operators_.fill(Operator{});
    muted_.fill(false);
    selected_ = 0;
    status_ = 0;
    lfo_phase_ = 0.0;
    noise_lfsr_ = 0x1ffff;
    write_count_ = 0;
}

void Y8950Device::setOperatorKey(int slot, bool on) {
    Operator& op = operators_[static_cast<size_t>(slot)];
    if (on && !op.key) {
        op.key = true;
        op.phase = 0.0;
        op.envelope = 0.0;
        op.stage = EnvelopeStage::Attack;
    } else if (!on && op.key) {
        op.key = false;
        if (op.stage != EnvelopeStage::Off) op.stage = EnvelopeStage::Release;
    }
}

void Y8950Device::setKey(int channel, bool on) {
    setOperatorKey(channel * 2, on);
    setOperatorKey(channel * 2 + 1, on);
}

void Y8950Device::updateRhythmKeys() {
    const uint8_t rhythm = registers_[0xbd];
    if (!(rhythm & 0x20)) return;
    setKey(6, (rhythm & 0x10) != 0);
    setOperatorKey(15, (rhythm & 0x08) != 0); // snare
    setOperatorKey(16, (rhythm & 0x04) != 0); // tom
    setOperatorKey(17, (rhythm & 0x02) != 0); // cymbal
    setOperatorKey(14, (rhythm & 0x01) != 0); // hi-hat
}

void Y8950Device::write(uint8_t value) {
    const uint8_t reg = selected_;
    const uint8_t old = registers_[reg];
    registers_[reg] = value;
    ++write_count_;

    if (reg >= 0xb0 && reg <= 0xb8 && !(registers_[0xbd] & 0x20)) {
        const int channel = reg - 0xb0;
        if ((old ^ value) & 0x20) setKey(channel, (value & 0x20) != 0);
    } else if (reg == 0xbd) {
        updateRhythmKeys();
    } else if (reg == 0x04) {
        // Minimal timer/status contract. Reset bit clears timer flags; timers are
        // not advanced because music engines normally only poll for readiness.
        if (value & 0x80) status_ = 0;
    }
}

double Y8950Device::waveform(double phase, uint8_t waveform_id) const {
    phase -= std::floor(phase);
    const double sine = std::sin(TWO_PI * phase);
    switch (waveform_id & 3) {
    case 1: return sine < 0.0 ? 0.0 : sine;
    case 2: return std::abs(sine) * 2.0 - 1.0;
    case 3: return phase < 0.25 ? std::sin(TWO_PI * phase) : 0.0;
    default: return sine;
    }
}

double Y8950Device::envelopeStep(Operator& op, int slot, int channel) {
    const uint8_t off = offsetForSlot(slot);
    const uint8_t ardr = registers_[0x60 + off];
    const uint8_t slrr = registers_[0x80 + off];
    const uint8_t flags = registers_[0x20 + off];
    const int block = (registers_[0xb0 + channel] >> 2) & 7;
    const bool key_scale_rate = (flags & 0x10) != 0;
    const int rate_boost = key_scale_rate ? block : (block >> 1);
    auto coeff = [&](int rate, bool attack) {
        if (rate <= 0) return 0.0;
        const int effective = std::min(19, rate + rate_boost);
        const double seconds = (attack ? 6.0 : 12.0) * std::pow(0.5, effective * 0.52);
        return 1.0 - std::exp(-1.0 / (std::max(0.0005, seconds) * sample_rate_));
    };
    const int attack = (ardr >> 4) & 15;
    const int decay = ardr & 15;
    const int release = slrr & 15;
    const int sustain_level = (slrr >> 4) & 15;
    const double sustain = sustain_level == 15 ? 0.0 : std::pow(10.0, -(sustain_level * 3.0) / 20.0);

    switch (op.stage) {
    case EnvelopeStage::Attack: {
        const double c = coeff(attack, true);
        if (c == 0.0) break;
        op.envelope += (1.0 - op.envelope) * c * 4.0;
        if (op.envelope >= 0.999) { op.envelope = 1.0; op.stage = EnvelopeStage::Decay; }
        break;
    }
    case EnvelopeStage::Decay:
        op.envelope += (sustain - op.envelope) * coeff(decay, false);
        if (op.envelope <= sustain + 0.001) {
            op.envelope = sustain;
            op.stage = EnvelopeStage::Sustain;
        }
        break;
    case EnvelopeStage::Sustain:
        if (!(flags & 0x20)) {
            op.envelope += (0.0 - op.envelope) * coeff(release ? release : decay, false) * 0.25;
            if (op.envelope < 1e-5) { op.envelope = 0.0; op.stage = EnvelopeStage::Off; }
        }
        break;
    case EnvelopeStage::Release:
        op.envelope += (0.0 - op.envelope) * coeff(release, false);
        if (op.envelope < 1e-5) { op.envelope = 0.0; op.stage = EnvelopeStage::Off; }
        break;
    case EnvelopeStage::Off:
        op.envelope = 0.0;
        break;
    }
    return op.envelope;
}

double Y8950Device::operatorSample(int slot, int channel, double phase_modulation, double feedback) {
    Operator& op = operators_[static_cast<size_t>(slot)];
    const uint8_t off = offsetForSlot(slot);
    const uint8_t flags = registers_[0x20 + off];
    const uint8_t level = registers_[0x40 + off];
    const uint16_t fnum = static_cast<uint16_t>(registers_[0xa0 + channel] |
                          ((registers_[0xb0 + channel] & 3) << 8));
    const int block = (registers_[0xb0 + channel] >> 2) & 7;
    double frequency = (CLOCK / 72.0) * fnum * std::pow(2.0, block - 1) / 524288.0;
    if (flags & 0x40) frequency *= 1.0 + 0.0065 * std::sin(TWO_PI * lfo_phase_ * 6.1);
    frequency *= OPL_MULTIPLIER[flags & 15];
    op.phase += frequency / sample_rate_;
    op.phase -= std::floor(op.phase);

    const double env = envelopeStep(op, slot, channel);
    const double total_level = std::pow(10.0, -((level & 0x3f) * 0.75) / 20.0);
    const double am = (flags & 0x80) ? (0.88 + 0.12 * std::sin(TWO_PI * lfo_phase_ * 3.7)) : 1.0;
    const uint8_t wave_id = (registers_[1] & 0x20) ? registers_[0xe0 + off] : 0;
    const double raw = waveform(op.phase + phase_modulation + feedback, wave_id) * env * total_level * am;
    op.previous = op.last;
    op.last = raw;
    return raw;
}

float Y8950Device::sample() {
    lfo_phase_ += 1.0 / sample_rate_;
    if (lfo_phase_ >= 1.0) lfo_phase_ -= 1.0;
    const uint32_t bit = ((noise_lfsr_ >> 0) ^ (noise_lfsr_ >> 3)) & 1u;
    noise_lfsr_ = (noise_lfsr_ >> 1) | (bit << 16);

    double mix = 0.0;
    const bool rhythm_mode = (registers_[0xbd] & 0x20) != 0;
    for (int channel = 0; channel < 9; ++channel) {
        const uint8_t control = registers_[0xc0 + channel];
        const int feedback_level = (control >> 1) & 7;
        Operator& modop = operators_[static_cast<size_t>(channel * 2)];
        const double feedback = feedback_level == 0 ? 0.0 :
            (modop.last + modop.previous) * std::ldexp(1.0, feedback_level - 8);
        double mod = operatorSample(channel * 2, channel, 0.0, feedback);
        double car = operatorSample(channel * 2 + 1, channel, (control & 1) ? 0.0 : mod * 0.55, 0.0);
        double value = (control & 1) ? (car + mod * 0.5) : car;
        if (rhythm_mode && channel >= 7) {
            const double noise = (noise_lfsr_ & 1u) ? 1.0 : -1.0;
            if (channel == 7 && (registers_[0xbd] & 0x09)) value = value * 0.55 + noise * std::abs(value) * 0.45;
            if (channel == 8 && (registers_[0xbd] & 0x02)) value = value * 0.7 + noise * std::abs(value) * 0.3;
        }
        if (!muted_[static_cast<size_t>(channel)]) mix += value;
    }
    return static_cast<float>(mix * 0.19);
}

void Y8950Device::setMuted(int channel, bool muted) {
    if (channel >= 0 && channel < static_cast<int>(muted_.size()))
        muted_[static_cast<size_t>(channel)] = muted;
}

bool Y8950Device::muted(int channel) const {
    return channel >= 0 && channel < static_cast<int>(muted_.size()) &&
           muted_[static_cast<size_t>(channel)];
}

} // namespace tinyksp
