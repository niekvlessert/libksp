#ifndef KSP1_SEEK_CONTROL_H
#define KSP1_SEEK_CONTROL_H

#include <stdint.h>

#define KSP1_SEEK_SMALL_SECONDS 10
#define KSP1_SEEK_LARGE_SECONDS 60

/* Returns the signed seek delta for [, ], {, and }. Returns 0 otherwise. */
int ksp1_seek_delta_from_key(int key);

/* Adds a signed second delta to the current frame and clamps to [0, end_frame]. */
uint64_t ksp1_seek_target_frame(uint64_t current_frame,
                                int delta_seconds,
                                uint32_t sample_rate,
                                uint64_t end_frame);

#endif
