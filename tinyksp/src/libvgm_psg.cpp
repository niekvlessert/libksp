#include "libvgm_psg.h"

#include <new>
extern "C" {
#include "emu2149.h"
#include "psg_rconv.h"
}

namespace tinyksp {
struct LibVgmPsg::Impl {
    PSG* chip = nullptr;
    PSG_RateConv* converter = nullptr;
    uint32_t sample_rate = 44100;
    uint32_t mute_mask = 0;

    void stop() {
        if (converter) PSG_RateConv_delete(converter);
        converter = nullptr;
        if (chip) PSG_delete(chip);
        chip = nullptr;
    }
};

LibVgmPsg::LibVgmPsg() : impl_(std::make_unique<Impl>()) {}

LibVgmPsg::~LibVgmPsg() {
    if (impl_) impl_->stop();
}

bool LibVgmPsg::reset(uint32_t sample_rate, std::string* error) {
    if (!impl_) {
        if (error) *error = "unable to allocate libkss EMU2149 adapter";
        return false;
    }
    impl_->sample_rate = sample_rate ? sample_rate : 44100;
    if (!impl_->chip) {
        impl_->chip = PSG_new(3579545u, impl_->sample_rate);
        if (!impl_->chip) {
            if (error) *error = "libkss could not start the PSG core";
            return false;
        }
        impl_->converter = PSG_RateConv_new();
        if (!impl_->converter) {
            if (error) *error = "libkss could not create the PSG rate converter";
            impl_->stop();
            return false;
        }
        // These are the exact VM defaults used by libkss: MSX's PSG clock
        // divider is enabled, quality 0 bypasses its rate converter, and
        // AUTO volume mode selects the YM2149 table.
        PSG_setClockDivider(impl_->chip, 1);
        PSG_setQuality(impl_->chip, 0);
        PSG_setVolumeMode(impl_->chip, 0);
    } else {
        PSG_setRate(impl_->chip, impl_->sample_rate);
    }
    PSG_reset(impl_->chip);
    PSG_setVolumeMode(impl_->chip, 0);
    // KSSPLAY's default PSG quality is the sinc converter (quality 2). The
    // chip itself runs at MSX clock/16 after its divider, while the converter
    // produces the requested PCM rate.
    PSG_RateConv_reset(impl_->converter, impl_->chip, impl_->sample_rate);
    PSG_setMask(impl_->chip, impl_->mute_mask);
    return true;
}

bool LibVgmPsg::ready() const {
    return impl_ && impl_->chip;
}

void LibVgmPsg::write(uint8_t reg, uint8_t value) {
    if (ready()) PSG_writeReg(impl_->chip, reg, value);
}

void LibVgmPsg::setMuteMask(uint32_t mask) {
    if (!impl_) return;
    impl_->mute_mask = mask & 0x00000007u;
    if (ready()) PSG_setMask(impl_->chip, impl_->mute_mask);
}

void LibVgmPsg::sampleStereo(float& left, float& right) {
    if (!ready()) {
        left = right = 0.0f;
        return;
    }
    const float value = static_cast<float>(PSG_RateConv_calc(impl_->converter)) /
                        32768.0f;
    left = right = value;
}

float LibVgmPsg::sample() {
    float left = 0.0f;
    float right = 0.0f;
    sampleStereo(left, right);
    return (left + right) * 0.5f;
}

} // namespace tinyksp
