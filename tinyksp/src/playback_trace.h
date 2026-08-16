#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace tinyksp {

enum class TracePhase : uint8_t { Init, Play };
enum class TraceDevice : uint8_t { Psg, Scc, FmPac, Y8950, Opl4FmLow, Opl4FmHigh, Opl4Pcm, Dac1, Dac8 };

struct TraceEvent {
    TracePhase phase = TracePhase::Init;
    uint64_t tick = 0;
    uint32_t order = 0;
    TraceDevice device = TraceDevice::Psg;
    uint16_t address = 0;
    uint8_t value = 0;

    bool operator==(const TraceEvent& other) const {
        return phase == other.phase && tick == other.tick && device == other.device &&
               address == other.address && value == other.value;
    }
};

inline const char* traceDeviceName(TraceDevice device) {
    switch (device) {
    case TraceDevice::Psg: return "PSG";
    case TraceDevice::Scc: return "SCC";
    case TraceDevice::FmPac: return "FM-PAC";
    case TraceDevice::Y8950: return "Y8950";
    case TraceDevice::Opl4FmLow: return "OPL4-FM-L";
    case TraceDevice::Opl4FmHigh: return "OPL4-FM-H";
    case TraceDevice::Opl4Pcm: return "OPL4-PCM";
    case TraceDevice::Dac1: return "1-bit DAC";
    case TraceDevice::Dac8: return "8-bit DAC";
    }
    return "unknown";
}

inline std::string tracePhaseName(TracePhase phase) {
    return phase == TracePhase::Init ? "INIT" : "PLAY";
}

} // namespace tinyksp
