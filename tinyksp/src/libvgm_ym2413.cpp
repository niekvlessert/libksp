#include "libvgm_ym2413.h"

#include <new>

extern "C" {
#include "emu2413.h"
}

namespace tinyksp {
struct LibVgmYm2413::Impl {
    OPLL* chip = nullptr;
    uint32_t sample_rate = 44100;
    uint32_t mute_mask = 0;

    void stop() {
        if (chip) OPLL_delete(chip);
        chip = nullptr;
    }
};

LibVgmYm2413::LibVgmYm2413() : impl_(std::make_unique<Impl>()) {}

LibVgmYm2413::~LibVgmYm2413() {
    if (impl_) impl_->stop();
}

bool LibVgmYm2413::reset(uint32_t sample_rate, std::string* error) {
    if (!impl_) {
        if (error) *error = "unable to allocate libvgm YM2413 adapter";
        return false;
    }
    impl_->sample_rate = sample_rate ? sample_rate : 44100;
    if (!impl_->chip) {
        impl_->chip = OPLL_new(3579545u, impl_->sample_rate);
        if (!impl_->chip) {
            if (error) *error = "libkss could not create the YM2413 core";
            return false;
        }
    } else {
        OPLL_setRate(impl_->chip, impl_->sample_rate);
    }
    OPLL_reset(impl_->chip);
    OPLL_setChipType(impl_->chip, OPLL_2413_TONE);
    OPLL_setMask(impl_->chip, impl_->mute_mask);
    return true;
}

bool LibVgmYm2413::ready() const {
    return impl_ && impl_->chip;
}

void LibVgmYm2413::write(uint8_t reg, uint8_t value) {
    if (ready()) OPLL_writeReg(impl_->chip, reg, value);
}

void LibVgmYm2413::setMuteMask(uint32_t mask) {
    if (!impl_) return;
    impl_->mute_mask = mask & 0x00003fffu;
    if (impl_->chip) OPLL_setMask(impl_->chip, impl_->mute_mask);
}

void LibVgmYm2413::sampleStereo(float& left, float& right) {
    if (!ready()) {
        left = right = 0.0f;
        return;
    }
    // KSSPLAY uses the mono OPLL path for ordinary FM-PAC playback and
    // duplicates it into both stereo channels.
    const int16_t sample = OPLL_calc(impl_->chip);
    left = right = static_cast<float>(sample) / 32768.0f;
}

float LibVgmYm2413::sample() {
    float left = 0.0f;
    float right = 0.0f;
    sampleStereo(left, right);
    return (left + right) * 0.5f;
}

} // namespace tinyksp
