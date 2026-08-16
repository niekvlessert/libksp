#include "libvgm_ymf278b.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <new>
#include <utility>
#include <vector>

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc99-extensions"
#endif
extern "C" {
#include "emu/EmuStructs.h"
#include "emu/SoundDevs.h"
#include "emu/SoundEmu.h"
#include "emu/cores/ymf278b.h"
}
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

namespace tinyksp {
namespace {
constexpr uint32_t YMF278B_CLOCK = 33868800u;
constexpr size_t YRW801_ROM_SIZE = 2u * 1024u * 1024u;
constexpr size_t MOONSOUND_RAM_SIZE = 2u * 1024u * 1024u;

template <typename T>
bool getDeviceFunction(const DEV_INFO& dev,
                       uint8_t function_type,
                       uint8_t rw_type,
                       uint16_t user,
                       T& result) {
    void* pointer = nullptr;
    const uint8_t status = SndEmu_GetDeviceFunc(
        dev.devDef, function_type, rw_type, user, &pointer);
    if (status != EERR_OK && status != EERR_MORE_FOUND) return false;
    result = reinterpret_cast<T>(pointer);
    return result != nullptr;
}
} // namespace

struct LibVgmYmf278b::Impl {
    DEV_INFO device{};
    DEVFUNC_WRITE_A8D8 write_register = nullptr;
    DEVFUNC_READ_A8D8 read_register = nullptr;
    DEVFUNC_WRITE_MEMSIZE allocate_rom = nullptr;
    DEVFUNC_WRITE_BLOCK write_rom = nullptr;
    DEVFUNC_WRITE_MEMSIZE allocate_ram = nullptr;
    DEVFUNC_WRITE_BLOCK write_ram = nullptr;
    DEVFUNC_OPTMASK set_mute_mask = nullptr;

    bool active = false;
    uint32_t output_rate = 44100;
    uint32_t mute_mask = 0;
    std::vector<uint8_t> rom;
    std::vector<uint8_t> ram = std::vector<uint8_t>(MOONSOUND_RAM_SIZE, 0);

    // libvgm's YMF278B core runs natively at clock/768 = 44.1 kHz.
    // TinyKSP normally also uses 44.1 kHz. The accumulator keeps other output
    // rates functional without changing the chip clock or its pitch.
    double native_accumulator = 0.0;
    float held_left = 0.0f;
    float held_right = 0.0f;

    void stop() {
        if (!active) return;
        SndEmu_Stop(&device);
        std::memset(&device, 0, sizeof(device));
        active = false;
        write_register = nullptr;
        read_register = nullptr;
        allocate_rom = nullptr;
        write_rom = nullptr;
        allocate_ram = nullptr;
        write_ram = nullptr;
        set_mute_mask = nullptr;
    }

    bool start(std::string* error) {
        stop();
        DEV_GEN_CFG config{};
        config.emuCore = 0;
        config.srMode = DEVRI_SRMODE_NATIVE;
        config.flags = 0;
        config.clock = YMF278B_CLOCK;
        config.smplRate = 44100;

        const uint8_t status = SndEmu_Start(DEVID_YMF278B, &config, &device);
        if (status != EERR_OK) {
            if (error) *error = "libvgm could not start the YMF278B core (error " +
                                std::to_string(status) + ")";
            return false;
        }
        active = true;

        // TinyKSP keeps its existing OPL3 implementation. The link descriptor
        // allocated by libvgm is therefore intentionally not instantiated.
        SndEmu_FreeDevLinkData(&device);

        const bool functions_ok =
            getDeviceFunction(device, RWF_REGISTER | RWF_WRITE, DEVRW_A8D8, 0,
                              write_register) &&
            getDeviceFunction(device, RWF_REGISTER | RWF_READ, DEVRW_A8D8, 0,
                              read_register) &&
            getDeviceFunction(device, RWF_MEMORY | RWF_WRITE, DEVRW_MEMSIZE,
                              0x524F, allocate_rom) &&
            getDeviceFunction(device, RWF_MEMORY | RWF_WRITE, DEVRW_BLOCK,
                              0x524F, write_rom) &&
            getDeviceFunction(device, RWF_MEMORY | RWF_WRITE, DEVRW_MEMSIZE,
                              0x5241, allocate_ram) &&
            getDeviceFunction(device, RWF_MEMORY | RWF_WRITE, DEVRW_BLOCK,
                              0x5241, write_ram);
        if (!functions_ok) {
            if (error) *error = "libvgm YMF278B core is missing a required register or memory function";
            stop();
            return false;
        }

        // SetMuteMask is part of DEV_DEF and is also exposed by rwFuncs.
        set_mute_mask = device.devDef->SetMuteMask;

        allocate_rom(device.dataPtr, static_cast<uint32_t>(YRW801_ROM_SIZE));
        allocate_ram(device.dataPtr, static_cast<uint32_t>(MOONSOUND_RAM_SIZE));
        if (!rom.empty()) {
            write_rom(device.dataPtr, 0, static_cast<uint32_t>(rom.size()), rom.data());
        }
        if (!ram.empty()) {
            write_ram(device.dataPtr, 0, static_cast<uint32_t>(ram.size()), ram.data());
        }
        if (set_mute_mask) set_mute_mask(device.dataPtr, mute_mask);
        native_accumulator = 0.0;
        held_left = held_right = 0.0f;
        return true;
    }

    void renderNativeSample(float& out_left, float& out_right) {
        if (!active || !device.devDef || !device.devDef->Update) {
            out_left = out_right = 0.0f;
            return;
        }
        DEV_SMPL left = 0;
        DEV_SMPL right = 0;
        DEV_SMPL* outputs[2] = {&left, &right};
        device.devDef->Update(device.dataPtr, 1, outputs);
        constexpr float scale = 1.0f / 32768.0f;
        out_left = static_cast<float>(left) * scale;
        out_right = static_cast<float>(right) * scale;
    }
};

LibVgmYmf278b::LibVgmYmf278b() : impl_(new (std::nothrow) Impl) {}
LibVgmYmf278b::~LibVgmYmf278b() {
    if (impl_) impl_->stop();
    delete impl_;
}

bool LibVgmYmf278b::reset(uint32_t output_sample_rate, std::string* error) {
    if (!impl_) {
        if (error) *error = "unable to allocate libvgm YMF278B adapter";
        return false;
    }
    impl_->output_rate = output_sample_rate ? output_sample_rate : 44100;
    if (!impl_->active && !impl_->start(error)) return false;

    impl_->device.devDef->Reset(impl_->device.dataPtr);
    // TinyKSP's previous host accepted wave writes immediately. Enable NEW2
    // here as the MoonSound host default; later engine writes can still change it.
    impl_->write_register(impl_->device.dataPtr, 2, 0x05);
    impl_->write_register(impl_->device.dataPtr, 3, 0x02);
    if (!impl_->rom.empty()) {
        impl_->write_rom(impl_->device.dataPtr, 0,
                         static_cast<uint32_t>(impl_->rom.size()), impl_->rom.data());
    }
    if (!impl_->ram.empty()) {
        impl_->write_ram(impl_->device.dataPtr, 0,
                         static_cast<uint32_t>(impl_->ram.size()), impl_->ram.data());
    }
    if (impl_->set_mute_mask) impl_->set_mute_mask(impl_->device.dataPtr, impl_->mute_mask);
    impl_->native_accumulator = 0.0;
    impl_->held_left = impl_->held_right = 0.0f;
    return true;
}

bool LibVgmYmf278b::ready() const { return impl_ && impl_->active; }

void LibVgmYmf278b::write(uint8_t offset, uint8_t value) {
    if (impl_ && impl_->active && impl_->write_register)
        impl_->write_register(impl_->device.dataPtr, offset, value);
}

uint8_t LibVgmYmf278b::read(uint8_t offset) const {
    if (!impl_ || !impl_->active || !impl_->read_register) return 0;
    return impl_->read_register(impl_->device.dataPtr, offset);
}

bool LibVgmYmf278b::loadRom(const uint8_t* data, size_t size, std::string* error) {
    if (!impl_ || !data || size < YRW801_ROM_SIZE) {
        if (error) *error = "YRW801 ROM must contain at least 2 MiB";
        return false;
    }
    impl_->rom.assign(data, data + YRW801_ROM_SIZE);
    if (impl_->active) {
        impl_->allocate_rom(impl_->device.dataPtr, static_cast<uint32_t>(YRW801_ROM_SIZE));
        impl_->write_rom(impl_->device.dataPtr, 0,
                         static_cast<uint32_t>(impl_->rom.size()), impl_->rom.data());
    }
    return true;
}

bool LibVgmYmf278b::loadRam(const uint8_t* data, size_t size, std::string* error) {
    if (!impl_ || !data || size > MOONSOUND_RAM_SIZE) {
        if (error) *error = "MoonSound RAM image is invalid or exceeds 2 MiB";
        return false;
    }
    impl_->ram.assign(MOONSOUND_RAM_SIZE, 0);
    std::copy_n(data, size, impl_->ram.begin());
    if (impl_->active) {
        impl_->allocate_ram(impl_->device.dataPtr, static_cast<uint32_t>(MOONSOUND_RAM_SIZE));
        impl_->write_ram(impl_->device.dataPtr, 0,
                         static_cast<uint32_t>(impl_->ram.size()), impl_->ram.data());
    }
    return true;
}


void LibVgmYmf278b::setDsReferenceMode(bool enabled) {
    if (!impl_ || !impl_->active) return;
    ymf278b_set_ds_reference_mode(impl_->device.dataPtr, enabled ? 1 : 0);
}

void LibVgmYmf278b::setMuteMask(uint32_t mask) {
    if (!impl_) return;
    impl_->mute_mask = mask & 0x00FFFFFFu;
    if (impl_->active && impl_->set_mute_mask)
        impl_->set_mute_mask(impl_->device.dataPtr, impl_->mute_mask);
}

void LibVgmYmf278b::sampleStereo(float& left, float& right) {
    if (!impl_ || !impl_->active) {
        left = right = 0.0f;
        return;
    }
    const double increment = 44100.0 / static_cast<double>(std::max(1u, impl_->output_rate));
    impl_->native_accumulator += increment;
    while (impl_->native_accumulator >= 1.0) {
        impl_->renderNativeSample(impl_->held_left, impl_->held_right);
        impl_->native_accumulator -= 1.0;
    }
    left = impl_->held_left;
    right = impl_->held_right;
}

float LibVgmYmf278b::sample() {
    float left = 0.0f, right = 0.0f;
    sampleStereo(left, right);
    return (left + right) * 0.5f;
}

} // namespace tinyksp
