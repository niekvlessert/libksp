#ifndef KSP1_ZX0_H
#define KSP1_ZX0_H
#include <stddef.h>
#include <stdint.h>
int ksp1_zx0_decompress(const uint8_t *input, size_t input_size,
                        uint8_t *output, size_t output_size,
                        char *error, size_t error_size);
#endif
