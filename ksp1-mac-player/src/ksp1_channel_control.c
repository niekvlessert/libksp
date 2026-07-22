#include "ksp1_channel_control.h"

#include <stdio.h>

int ksp1_channel_index_from_key(int key) {
    if (key >= '1' && key <= '9') return key - '1';
    if (key == '0') return 9;
    return -1;
}

uint32_t ksp1_toggle_scc_channel_mask(uint32_t mask, unsigned channel) {
    if (channel >= KSP1_SCC_CHANNEL_COUNT)
        return mask & KSP1_SCC_ALL_CHANNELS_MASK;
    return (mask ^ (1u << channel)) & KSP1_SCC_ALL_CHANNELS_MASK;
}

int ksp1_scc_channel_is_enabled(uint32_t mask, unsigned channel) {
    if (channel >= KSP1_SCC_CHANNEL_COUNT) return 0;
    return (mask & (1u << channel)) == 0u;
}

static char channel_character(uint32_t mask, unsigned channel, char key) {
    return ksp1_scc_channel_is_enabled(mask, channel) ? key : '-';
}

void ksp1_format_scc_channel_status(char *output, size_t output_size,
                                    uint32_t primary_mask,
                                    uint32_t secondary_mask,
                                    int dual_scc) {
    if (!output || output_size == 0u) return;
    if (dual_scc) {
        (void)snprintf(output, output_size,
                       "SCC A [%c %c %c %c %c]  SCC B [%c %c %c %c %c]",
                       channel_character(primary_mask, 0u, '1'),
                       channel_character(primary_mask, 1u, '2'),
                       channel_character(primary_mask, 2u, '3'),
                       channel_character(primary_mask, 3u, '4'),
                       channel_character(primary_mask, 4u, '5'),
                       channel_character(secondary_mask, 0u, '6'),
                       channel_character(secondary_mask, 1u, '7'),
                       channel_character(secondary_mask, 2u, '8'),
                       channel_character(secondary_mask, 3u, '9'),
                       channel_character(secondary_mask, 4u, '0'));
    } else {
        (void)snprintf(output, output_size, "SCC [%c %c %c %c %c]",
                       channel_character(primary_mask, 0u, '1'),
                       channel_character(primary_mask, 1u, '2'),
                       channel_character(primary_mask, 2u, '3'),
                       channel_character(primary_mask, 3u, '4'),
                       channel_character(primary_mask, 4u, '5'));
    }
}
