#pragma once

#include <cstdint>
#include <string>

namespace tinyksp {

class MacAudioOutput {
public:
    MacAudioOutput();
    ~MacAudioOutput();

    MacAudioOutput(const MacAudioOutput&) = delete;
    MacAudioOutput& operator=(const MacAudioOutput&) = delete;

    bool start(std::string& error);
    bool restart(std::string& error);
    bool write(const int16_t* interleaved_stereo, uint32_t frames,
               std::string& error);
    bool drain(std::string& error);
    void stop();

private:
    struct Impl;
    Impl* impl_ = nullptr;
};

} // namespace tinyksp
