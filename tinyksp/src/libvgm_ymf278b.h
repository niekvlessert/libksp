#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace tinyksp {

class LibVgmYmf278b {
public:
    LibVgmYmf278b();
    ~LibVgmYmf278b();

    LibVgmYmf278b(const LibVgmYmf278b&) = delete;
    LibVgmYmf278b& operator=(const LibVgmYmf278b&) = delete;

    bool reset(uint32_t output_sample_rate, std::string* error = nullptr);
    bool ready() const;

    void write(uint8_t offset, uint8_t value);
    uint8_t read(uint8_t offset) const;

    bool loadRom(const uint8_t* data, size_t size, std::string* error = nullptr);
    bool loadRam(const uint8_t* data, size_t size, std::string* error = nullptr);

    void setMuteMask(uint32_t mask);
    void setDsReferenceMode(bool enabled);
    float sample();
    void sampleStereo(float& left, float& right);

private:
    struct Impl;
    Impl* impl_ = nullptr;
};

} // namespace tinyksp
