#ifndef KSP1_RUNTIME_H
#define KSP1_RUNTIME_H
#include <stddef.h>
#include <stdint.h>

#define KSP1_NO_INDEX 0xffffu
#define KSP1_NO_STRING 0xffffffffu
#define KSP1_PAGE_SPARSE_OVERLAY 0u
#define KSP1_PAGE_COMPLETE 1u
#define KSP1_PAGE_SHARED_BLOCK_MAP 2u
#define KSP1_PAGE_RESOURCE_MAP 3u
#define KSP1_PAGE_HYBRID_POOL 4u
#define KSP1_COMPRESSION_NONE 0u
#define KSP1_COMPRESSION_ZX0 1u
#define KSP1_COMPRESSION_ZX0_BLOCKS 2u
#define KSP1_ENGINE_DYNAMIC_PAGES 1u
#define KSP1_RESOURCE_REQUIRED 1u
#define KSP1_RESOURCE_PAGE_SOURCE 4u

typedef struct KSP1Header {
    uint32_t file_size;
    uint32_t engine_table_offset;
    uint16_t engine_count, engine_entry_size;
    uint32_t page_table_offset;
    uint16_t page_count, page_entry_size;
    uint32_t track_table_offset;
    uint16_t track_count, track_entry_size;
    uint32_t resource_table_offset;
    uint16_t resource_count, resource_entry_size;
    uint32_t string_table_offset, string_table_size;
    uint16_t default_track, meta_resource, cover_resource;
    uint32_t header_crc, index_crc;
} KSP1Header;

typedef struct KSP1Engine {
    uint32_t flags, hardware_flags;
    uint16_t abi_version, tick_hz, load_address, page_size;
    uint16_t init_address, play_address, stop_address, gateway_address;
    uint16_t replace_start, first_page, page_count, default_mwk;
    uint8_t template_compression, bank_base, bank_count, bank_width;
    uint32_t template_offset, template_packed_size, template_unpacked_size;
    uint32_t template_crc, name_offset;
} KSP1Engine;

typedef struct KSP1Page {
    uint16_t engine_index;
    uint8_t encoding, compression;
    uint16_t flags;
    uint32_t payload_offset, packed_size, unpacked_size, crc;
} KSP1Page;

typedef struct KSP1Track {
    uint16_t page_index, song_id, flags, mwk_resource, image_resource;
    uint32_t title_offset, duration_ms, loop_start_ms, loop_end_ms, fade_ms;
} KSP1Track;

typedef struct KSP1Resource {
    char type[5];
    uint16_t flags;
    uint8_t compression;
    uint32_t offset, packed_size, unpacked_size, crc, aux0, aux1;
    uint8_t *decoded;
} KSP1Resource;

typedef struct KSP1Runtime KSP1Runtime;

KSP1Runtime *ksp1_open(const char *path, char *error, size_t error_size);
void ksp1_close(KSP1Runtime *runtime);
const KSP1Header *ksp1_header(const KSP1Runtime *runtime);
const KSP1Engine *ksp1_engine(const KSP1Runtime *runtime, uint16_t index);
const KSP1Page *ksp1_page(const KSP1Runtime *runtime, uint16_t index);
const KSP1Track *ksp1_track(const KSP1Runtime *runtime, uint16_t index);
const KSP1Resource *ksp1_resource(const KSP1Runtime *runtime, uint16_t index);
const char *ksp1_string(const KSP1Runtime *runtime, uint32_t offset);
int ksp1_materialize_page(KSP1Runtime *runtime, uint16_t page_index,
                          uint8_t *output, size_t output_size,
                          char *error, size_t error_size);
int ksp1_materialize_track(KSP1Runtime *runtime, uint16_t track_index,
                           uint8_t **output, size_t *output_size,
                           const KSP1Engine **engine, const KSP1Track **track,
                           char *error, size_t error_size);
int ksp1_validate_all_pages(KSP1Runtime *runtime, char *error, size_t error_size);
int ksp1_build_kscc_image(KSP1Runtime *runtime, uint16_t track_index,
                          uint8_t **image, uint32_t *image_size,
                          char *error, size_t error_size);
#endif
