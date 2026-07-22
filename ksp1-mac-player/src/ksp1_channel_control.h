#ifndef KSP1_CHANNEL_CONTROL_H
#define KSP1_CHANNEL_CONTROL_H

#include <stddef.h>
#include <stdint.h>

#define KSP1_SCC_CHANNEL_COUNT 5u
#define KSP1_DUAL_SCC_CHANNEL_COUNT 10u
#define KSP1_SCC_ALL_CHANNELS_MASK 0x1fu

/* Returns 0..9 for keys 1..9,0. Returns -1 for all other keys. */
int ksp1_channel_index_from_key(int key);

/* SCC mask bits are mute bits: bit 0 mutes channel 1, etc. */
uint32_t ksp1_toggle_scc_channel_mask(uint32_t mask, unsigned channel);
int ksp1_scc_channel_is_enabled(uint32_t mask, unsigned channel);

void ksp1_format_scc_channel_status(char *output, size_t output_size,
                                    uint32_t primary_mask,
                                    uint32_t secondary_mask,
                                    int dual_scc);

#endif
