#include "ksp1_desktop_bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint16_t read_le16(const uint8_t *data) {
    return (uint16_t)(data[0] | ((uint16_t)data[1] << 8));
}

static void write_le16(uint8_t *data, uint16_t value) {
    data[0] = (uint8_t)(value & 0xffu);
    data[1] = (uint8_t)(value >> 8);
}

static int contains_z80_call(const uint8_t *data, size_t size, uint16_t address) {
    size_t i;
    for (i = 0; i + 2u < size; ++i) {
        if (data[i] == 0xcdu && data[i + 1u] == (uint8_t)(address & 0xffu) &&
            data[i + 2u] == (uint8_t)(address >> 8))
            return 1;
    }
    return 0;
}

KSP1DualSccAbi ksp1_detect_dual_scc_abi(const KSP1Engine *engine,
                                        const uint8_t *page,
                                        size_t page_size) {
    if (!engine || !page) return KSP1_DUAL_SCC_ABI_NONE;
    if ((engine->hardware_flags & KSP1_HW_DUAL_SCC) &&
        contains_z80_call(page, page_size, KSP1_CALLBACK_SELECT_A) &&
        contains_z80_call(page, page_size, KSP1_CALLBACK_SELECT_B) &&
        contains_z80_call(page, page_size, KSP1_CALLBACK_SELECT_NONE))
        return KSP1_DUAL_SCC_ABI_KSP1;

    /* Early dual-SCC converters used D900 for an 8-bit page request and D903
     * for SCC selection in A, but did not set the KSP 1.0 dual-SCC flag. */
    if (engine->page_count > 1u && !(engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) &&
        engine->replace_start != 0u &&
        contains_z80_call(page, page_size, KSP1_CALLBACK_SELECT_A) &&
        contains_z80_call(page, page_size, KSP1_CALLBACK_LEGACY_SEL))
        return KSP1_DUAL_SCC_ABI_LEGACY_D900_D903;

    return KSP1_DUAL_SCC_ABI_NONE;
}

static int put_bridge_code(uint8_t *image, uint32_t image_size,
                           uint16_t load_address, uint16_t address,
                           const uint8_t *code, size_t code_size,
                           char *error, size_t error_size) {
    uint32_t offset;
    if (address < load_address ||
        (uint32_t)address + code_size > (uint32_t)load_address + image_size - 16u) {
        snprintf(error, error_size, "desktop ABI stub $%04X is outside KSCC load range",
                 address);
        return 0;
    }
    offset = 16u + (uint32_t)address - load_address;
    memcpy(image + offset, code, code_size);
    return 1;
}

int ksp1_prepare_kscc_bridge_image(uint8_t **image, uint32_t *image_size,
                                   const KSP1Engine *engine,
                                   KSP1DualSccAbi dual_abi,
                                   char *error, size_t error_size) {
    static const uint8_t dynamic_gateway_hl16[] = { 0x22, 0x9e, 0xd8, 0xc9 };
    /* ABI 1 requires A to mirror the low byte of HL.  For engines with at
     * most 256 pages, using A is equivalent for conforming engines and also
     * supports early converters (including ESCHATOS N163) that supplied only
     * A and left HL as a working pointer.  XOR A writes the mandatory zero
     * high byte and returns with carry clear. */
    static const uint8_t dynamic_gateway_a8[] = {
        0x32, 0x9e, 0xd8,       /* LD (D89E),A */
        0xaf,                   /* XOR A */
        0x32, 0x9f, 0xd8,       /* LD (D89F),A */
        0xc9                    /* RET */
    };
    static const uint8_t select_a[] = { 0x3e, 0x00, 0x32, 0x4f, 0xd8, 0xc9 };
    static const uint8_t select_b[] = { 0x3e, 0x01, 0x32, 0x4f, 0xd8, 0xc9 };
    static const uint8_t select_none[] = { 0x3e, 0x02, 0x32, 0x4f, 0xd8, 0xc9 };
    static const uint8_t legacy_page[] = {
        0x32, 0x9e, 0xd8,       /* LD (D89E),A */
        0xf5,                   /* PUSH AF */
        0xaf,                   /* XOR A */
        0x32, 0x9f, 0xd8,       /* LD (D89F),A */
        0xf1,                   /* POP AF */
        0xc9                    /* RET */
    };
    static const uint8_t legacy_select[] = { 0x32, 0x4f, 0xd8, 0xc9 };
    static const uint8_t jump_select_a[] = { 0xc3, 0x50, 0xd8 };
    static const uint8_t jump_select_b[] = { 0xc3, 0x56, 0xd8 };
    static const uint8_t jump_select_none[] = { 0xc3, 0x5c, 0xd8 };
    static const uint8_t jump_legacy_page[] = { 0xc3, 0x62, 0xd8 };
    static const uint8_t jump_legacy_select[] = { 0xc3, 0x6c, 0xd8 };
    uint8_t *expanded;
    uint16_t load_address, old_length, new_length;
    uint32_t required_end;
    const uint8_t *dynamic_gateway = NULL;
    size_t dynamic_gateway_size = 0;
    int needs_dynamic;

    if (!image || !*image || !image_size || *image_size < 16u ||
        memcmp(*image, "KSCC", 4) != 0 || !engine) {
        snprintf(error, error_size, "invalid KSCC bridge image");
        return 0;
    }
    needs_dynamic = (engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) != 0 ||
                    dual_abi == KSP1_DUAL_SCC_ABI_LEGACY_D900_D903;
    if (engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) {
        if (engine->page_count <= 256u) {
            dynamic_gateway = dynamic_gateway_a8;
            dynamic_gateway_size = sizeof(dynamic_gateway_a8);
        } else {
            dynamic_gateway = dynamic_gateway_hl16;
            dynamic_gateway_size = sizeof(dynamic_gateway_hl16);
        }
    }
    if (!needs_dynamic && dual_abi == KSP1_DUAL_SCC_ABI_NONE) return 1;
    if ((engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) && !engine->gateway_address) {
        snprintf(error, error_size, "dynamic engine has no gateway address");
        return 0;
    }

    load_address = read_le16(*image + 4);
    old_length = read_le16(*image + 6);
    required_end = (uint32_t)load_address + old_length;
    if (engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) {
        uint32_t gateway_end = (uint32_t)engine->gateway_address + dynamic_gateway_size;
        if (gateway_end > required_end) required_end = gateway_end;
    }
    if (dual_abi != KSP1_DUAL_SCC_ABI_NONE) {
        uint32_t callback_end = (uint32_t)KSP1_CALLBACK_SELECT_NONE + 3u;
        if (callback_end > required_end) required_end = callback_end;
    }
    if (required_end > 0x10000u || required_end < load_address ||
        required_end - load_address > 0xffffu) {
        snprintf(error, error_size, "desktop ABI stubs do not fit in KSCC address space");
        return 0;
    }
    new_length = (uint16_t)(required_end - load_address);
    if ((uint32_t)old_length + 16u > *image_size) {
        snprintf(error, error_size, "truncated KSCC bridge image");
        return 0;
    }

    expanded = (uint8_t *)calloc(1u, 16u + new_length);
    if (!expanded) {
        snprintf(error, error_size, "out of memory extending KSCC bridge image");
        return 0;
    }
    memcpy(expanded, *image, 16u + old_length);
    write_le16(expanded + 6, new_length);
    free(*image);
    *image = expanded;
    *image_size = 16u + new_length;

    if ((engine->flags & KSP1_ENGINE_DYNAMIC_PAGES) &&
        !put_bridge_code(expanded, *image_size, load_address,
                         engine->gateway_address, dynamic_gateway,
                         dynamic_gateway_size, error, error_size))
        return 0;

    if (dual_abi == KSP1_DUAL_SCC_ABI_KSP1) {
        if (!put_bridge_code(expanded, *image_size, load_address, KSP1_STUB_SELECT_A,
                             select_a, sizeof(select_a), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_STUB_SELECT_B,
                             select_b, sizeof(select_b), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_STUB_SELECT_NONE,
                             select_none, sizeof(select_none), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_CALLBACK_SELECT_A,
                             jump_select_a, sizeof(jump_select_a), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_CALLBACK_SELECT_B,
                             jump_select_b, sizeof(jump_select_b), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_CALLBACK_SELECT_NONE,
                             jump_select_none, sizeof(jump_select_none), error, error_size))
            return 0;
    } else if (dual_abi == KSP1_DUAL_SCC_ABI_LEGACY_D900_D903) {
        if (!put_bridge_code(expanded, *image_size, load_address, KSP1_STUB_LEGACY_PAGE,
                             legacy_page, sizeof(legacy_page), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_STUB_LEGACY_SELECT,
                             legacy_select, sizeof(legacy_select), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_CALLBACK_SELECT_A,
                             jump_legacy_page, sizeof(jump_legacy_page), error, error_size) ||
            !put_bridge_code(expanded, *image_size, load_address, KSP1_CALLBACK_LEGACY_SEL,
                             jump_legacy_select, sizeof(jump_legacy_select), error, error_size))
            return 0;
    }
    return 1;
}
