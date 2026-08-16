#pragma once

#include <cstdint>
#include <memory>
#include <string>

namespace tinyksp {

// Adapter for libkss's reference EMU2413 core. TinyKSP keeps a fallback
// implementation in Ym2413Device for builds where this core is unavailable.
class LibVgmYm2413 {
public:
    LibVgmYm2413();
    ~LibVgmYm2413();

    LibVgmYm2413(const LibVgmYm2413&) = delete;
    LibVgmYm2413& operator=(const LibVgmYm2413&) = delete;

    bool reset(uint32_t sample_rate, std::string* error = nullptr);
    bool ready() const;
    void write(uint8_t reg, uint8_t value);
    void setMuteMask(uint32_t mask);
    void sampleStereo(float& left, float& right);
    float sample();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace tinyksp
