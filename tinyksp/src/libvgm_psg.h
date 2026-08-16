#pragma once

#include <cstdint>
#include <memory>
#include <string>

namespace tinyksp {

// Adapter for libkss's reference EMU2149 core. The historical class name is
// retained because it is also used by the chip abstraction.
class LibVgmPsg {
public:
    LibVgmPsg();
    ~LibVgmPsg();

    LibVgmPsg(const LibVgmPsg&) = delete;
    LibVgmPsg& operator=(const LibVgmPsg&) = delete;

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
