#include "ksp1_seek_control.h"

#include <limits.h>

int ksp1_seek_delta_from_key(int key) {
    switch (key) {
    case '[': return -KSP1_SEEK_SMALL_SECONDS;
    case ']': return KSP1_SEEK_SMALL_SECONDS;
    case '{': return -KSP1_SEEK_LARGE_SECONDS;
    case '}': return KSP1_SEEK_LARGE_SECONDS;
    default: return 0;
    }
}

uint64_t ksp1_seek_target_frame(uint64_t current_frame,
                                int delta_seconds,
                                uint32_t sample_rate,
                                uint64_t end_frame) {
    uint64_t magnitude;
    uint64_t delta_frames;

    if (sample_rate == 0u || delta_seconds == 0)
        return current_frame > end_frame ? end_frame : current_frame;

    magnitude = delta_seconds < 0
        ? (uint64_t)(-(int64_t)delta_seconds)
        : (uint64_t)delta_seconds;
    if (magnitude > UINT64_MAX / sample_rate)
        delta_frames = UINT64_MAX;
    else
        delta_frames = magnitude * sample_rate;

    if (delta_seconds < 0)
        return delta_frames >= current_frame ? 0u : current_frame - delta_frames;

    if (current_frame >= end_frame || delta_frames >= end_frame - current_frame)
        return end_frame;
    return current_frame + delta_frames;
}
