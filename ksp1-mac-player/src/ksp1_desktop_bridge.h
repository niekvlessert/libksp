#ifndef KSP1_DESKTOP_BRIDGE_H
#define KSP1_DESKTOP_BRIDGE_H

#include "ksp1_runtime.h"

#include <stddef.h>
#include <stdint.h>

#define KSP1_GATEWAY_MAILBOX_LOW   0xD89Eu
#define KSP1_GATEWAY_MAILBOX_HIGH  0xD89Fu
#define KSP1_SCC_SELECTOR_MAILBOX  0xD84Fu
#define KSP1_STUB_SELECT_A         0xD850u
#define KSP1_STUB_SELECT_B         0xD856u
#define KSP1_STUB_SELECT_NONE      0xD85Cu
#define KSP1_STUB_LEGACY_PAGE      0xD862u
#define KSP1_STUB_LEGACY_SELECT    0xD86Cu
#define KSP1_CALLBACK_SELECT_A     0xD900u
#define KSP1_CALLBACK_LEGACY_SEL   0xD903u
#define KSP1_CALLBACK_SELECT_B     0xD904u
#define KSP1_CALLBACK_SELECT_NONE  0xD908u

typedef enum KSP1DualSccAbi {
    KSP1_DUAL_SCC_ABI_NONE = 0,
    KSP1_DUAL_SCC_ABI_KSP1,
    KSP1_DUAL_SCC_ABI_LEGACY_D900_D903
} KSP1DualSccAbi;

KSP1DualSccAbi ksp1_detect_dual_scc_abi(const KSP1Engine *engine,
                                        const uint8_t *page,
                                        size_t page_size);

int ksp1_prepare_kscc_bridge_image(uint8_t **image, uint32_t *image_size,
                                   const KSP1Engine *engine,
                                   KSP1DualSccAbi dual_abi,
                                   char *error, size_t error_size);

#endif
