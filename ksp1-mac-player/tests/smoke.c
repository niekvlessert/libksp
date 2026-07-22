#include "ksp1_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint16_t rd16(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint8_t expected_device_flags(const KSP1Engine *engine) {
    uint8_t flags = 0;
    if (engine->hardware_flags & (1u << 4)) flags |= 0x01u;
    if (engine->hardware_flags & (1u << 5)) flags |= 0x08u;
    if (engine->hardware_flags & (1u << 7)) flags |= 0x02u;
    if (engine->hardware_flags & (1u << 8)) flags |= 0x04u;
    if (engine->tick_hz == 50u) flags |= 0x40u;
    return flags;
}

static int check_bridge(KSP1Runtime *runtime, uint16_t track_index) {
    uint8_t *image = NULL;
    uint32_t image_size = 0;
    const KSP1Track *track = ksp1_track(runtime, track_index);
    const KSP1Page *page;
    const KSP1Engine *engine;
    char error[256];

    if (!track) return 0;
    page = ksp1_page(runtime, track->page_index);
    engine = page ? ksp1_engine(runtime, page->engine_index) : NULL;
    if (!engine) return 0;
    if (!ksp1_build_kscc_image(runtime, track_index, &image, &image_size,
                               error, sizeof(error))) {
        fprintf(stderr, "%s\n", error);
        return 0;
    }
    {
        uint32_t expected_size = 16u + engine->page_size;
        int page2_runtime = (engine->flags & KSP1_ENGINE_PAGE2_RUNTIME) != 0;
        if (page2_runtime)
            expected_size += 0x4000u;
    if (image_size != expected_size || memcmp(image, "KSCC", 4) ||
        rd16(image + 4) != engine->load_address ||
        rd16(image + 6) != expected_size - 16u ||
        rd16(image + 8) != engine->init_address ||
        rd16(image + 10) != engine->play_address ||
        image[15] != (uint8_t)(expected_device_flags(engine) |
                               (page2_runtime ? 0x04u : 0u))) {
        fprintf(stderr, "invalid KSCC bridge for track %u\n", track_index);
        free(image);
        return 0;
    }
    }
    free(image);
    return 1;
}

int main(int argc, char **argv) {
    KSP1Runtime *runtime;
    const KSP1Header *header;
    char error[256];
    if (argc != 2) return 2;
    runtime = ksp1_open(argv[1], error, sizeof(error));
    if (!runtime) {
        fprintf(stderr, "%s\n", error);
        return 1;
    }
    if (!ksp1_validate_all_pages(runtime, error, sizeof(error))) {
        fprintf(stderr, "%s\n", error);
        ksp1_close(runtime);
        return 1;
    }
    header = ksp1_header(runtime);
    if (!header->track_count || !check_bridge(runtime, 0) ||
        !check_bridge(runtime, (uint16_t)(header->track_count - 1u))) {
        ksp1_close(runtime);
        return 1;
    }
    ksp1_close(runtime);
    return 0;
}
