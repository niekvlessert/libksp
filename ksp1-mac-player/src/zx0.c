#include "zx0.h"
#include <stdarg.h>
#include <stdio.h>

typedef struct ZX0Reader {
    const uint8_t *input;
    size_t input_size;
    size_t input_pos;
    uint8_t bit_value;
    uint8_t bit_mask;
    uint8_t last_byte;
    int backtrack;
    uint8_t *output;
    size_t output_size;
    size_t output_pos;
    char *error;
    size_t error_size;
} ZX0Reader;

static int fail(ZX0Reader *r, const char *fmt, ...) {
    if (r->error && r->error_size) {
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(r->error, r->error_size, fmt, ap);
        va_end(ap);
    }
    return 0;
}

static int read_byte(ZX0Reader *r, uint8_t *value) {
    if (r->input_pos >= r->input_size) return fail(r, "truncated ZX0 stream");
    r->last_byte = r->input[r->input_pos++];
    *value = r->last_byte;
    return 1;
}

static int read_bit(ZX0Reader *r, unsigned *value) {
    uint8_t byte;
    if (r->backtrack) {
        r->backtrack = 0;
        *value = r->last_byte & 1u;
        return 1;
    }
    if (!r->bit_mask) {
        if (!read_byte(r, &byte)) return 0;
        r->bit_value = byte;
        r->bit_mask = 0x80u;
    }
    *value = (r->bit_value & r->bit_mask) != 0;
    r->bit_mask >>= 1;
    return 1;
}

static int gamma_value(ZX0Reader *r, unsigned invert, uint32_t *result) {
    uint32_t value = 1;
    unsigned bit;
    for (;;) {
        if (!read_bit(r, &bit)) return 0;
        if (bit) break;
        if (value > 0x7fffffffu) return fail(r, "ZX0 gamma value overflow");
        value <<= 1;
        if (!read_bit(r, &bit)) return 0;
        value |= bit ^ invert;
    }
    *result = value;
    return 1;
}

static int literals(ZX0Reader *r, uint32_t count) {
    while (count--) {
        uint8_t value;
        if (r->output_pos >= r->output_size) return fail(r, "ZX0 output overflow");
        if (!read_byte(r, &value)) return 0;
        r->output[r->output_pos++] = value;
    }
    return 1;
}

static int copy_match(ZX0Reader *r, uint32_t offset, uint32_t count) {
    if (!offset || offset > r->output_pos) return fail(r, "invalid ZX0 offset %u", offset);
    while (count--) {
        if (r->output_pos >= r->output_size) return fail(r, "ZX0 output overflow");
        r->output[r->output_pos] = r->output[r->output_pos - offset];
        r->output_pos++;
    }
    return 1;
}

int ksp1_zx0_decompress(const uint8_t *input, size_t input_size,
                        uint8_t *output, size_t output_size,
                        char *error, size_t error_size) {
    ZX0Reader r;
    uint32_t offset = 1, count, msb;
    unsigned bit;
    uint8_t lsb;
    r.input = input;
    r.input_size = input_size;
    r.input_pos = 0;
    r.bit_value = 0;
    r.bit_mask = 0;
    r.last_byte = 0;
    r.backtrack = 0;
    r.output = output;
    r.output_size = output_size;
    r.output_pos = 0;
    r.error = error;
    r.error_size = error_size;
    if (error && error_size) error[0] = '\0';

    if (!gamma_value(&r, 0, &count) || !literals(&r, count)) return 0;
    for (;;) {
        if (!read_bit(&r, &bit)) return 0;
        if (!bit) {
            if (!gamma_value(&r, 0, &count) || !copy_match(&r, offset, count)) return 0;
            if (!read_bit(&r, &bit)) return 0;
            if (!bit) {
                if (!gamma_value(&r, 0, &count) || !literals(&r, count)) return 0;
                continue;
            }
        }
        for (;;) {
            if (!gamma_value(&r, 1, &msb)) return 0;
            if (msb == 256u) {
                if (r.output_pos != output_size)
                    return fail(&r, "ZX0 size mismatch: got %zu, expected %zu", r.output_pos, output_size);
                return 1;
            }
            if (!read_byte(&r, &lsb)) return 0;
            offset = msb * 128u - (lsb >> 1);
            r.backtrack = 1;
            if (!gamma_value(&r, 0, &count) || !copy_match(&r, offset, count + 1u)) return 0;
            if (!read_bit(&r, &bit)) return 0;
            if (!bit) {
                if (!gamma_value(&r, 0, &count) || !literals(&r, count)) return 0;
                break;
            }
        }
    }
}
