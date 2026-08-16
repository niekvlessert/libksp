#include "yamaha_chips.h"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <fstream>
#include <cstdio>
#include <string>
#include <vector>

using namespace tinyksp;

static void opllWrite(Ym2413Device& d, uint8_t r, uint8_t v) {
    d.select(r); d.write(v);
}
static void opl4Write(Opl4Device& d, uint8_t r, uint8_t v) {
    d.selectWave(r); d.writeWave(v);
}

int main() {
    Ym2413Device fm;
    fm.reset(44100);
    opllWrite(fm, 0x30, 0x10); // preset 1, loud
    opllWrite(fm, 0x10, 0x80);
    opllWrite(fm, 0x20, 0x16); // block 3 + key
    double energy = 0;
    for (int i = 0; i < 44100 / 4; ++i) energy += std::abs(fm.sample());
    if (energy < 1.0 || fm.writeCount() != 3) {
        std::cerr << "YM2413 did not produce audio\n";
        return 1;
    }

    // Combined YM2413 rhythm bits must trigger independent decaying voices.
    fm.reset(44100);
    opllWrite(fm, 0x16, 0x90); opllWrite(fm, 0x26, 0x05);
    opllWrite(fm, 0x17, 0x80); opllWrite(fm, 0x27, 0x05);
    opllWrite(fm, 0x18, 0x70); opllWrite(fm, 0x28, 0x05);
    opllWrite(fm, 0x36, 0x00); opllWrite(fm, 0x37, 0x00); opllWrite(fm, 0x38, 0x00);
    opllWrite(fm, 0x0e, 0x20);
    opllWrite(fm, 0x0e, 0x39); // rhythm mode + BD + SD + HH on one write
    double rhythm_energy = 0.0;
    for (int i = 0; i < 44100 / 2; ++i) rhythm_energy += std::abs(fm.sample());
    if (!fm.rhythmMode() || rhythm_energy < 5.0) {
        std::cerr << "YM2413 rhythm mode did not produce percussion\n";
        return 1;
    }

    std::vector<uint8_t> mwk;
    mwk.insert(mwk.end(), {'M','B','M','S',0x10,0x0d,0,0,0,0});
    std::vector<uint8_t> flags(64,0); flags[0] = 1;
    mwk.insert(mwk.end(), flags.begin(), flags.end());
    // 13-byte source header: bytes 2..10 copied, bytes 11/12 sample length.
    uint8_t source[13] = {};
    source[2] = 0; source[3] = 0; // loop 0
    source[4] = 0xff; source[5] = 0x00; // two's-complement length fallback
    source[6] = 0xf0; source[7] = 0xf0; source[8] = 0x00;
    source[9] = 0xf0; source[10] = 0xf7;
    source[11] = 0x00; source[12] = 0x01; // 256 bytes
    mwk.insert(mwk.end(), source, source + 13);
    for (int i = 0; i < 256; ++i) {
        const double x = std::sin(6.283185307179586 * i / 32.0);
        mwk.push_back(static_cast<uint8_t>(static_cast<int8_t>(x * 110.0)));
    }

    Opl4Device opl4;
    opl4.reset(44100);
    std::string error;
    if (!opl4.loadMwk(mwk, error)) {
        std::cerr << "MWK load failed: " << error << '\n';
        return 1;
    }
    // YMF278B register 20h+n: bit 0 is wave-number bit 8 and
    // bits 1..7 are F-number bits 0..6.
    opl4Write(opl4, 0x08, 0x34);
    opl4Write(opl4, 0x20, 0xab); // wave=0x134, FNUM low=0x55
    opl4Write(opl4, 0x38, 0x05); // FNUM high=5 -> 0x2d5
    if (opl4.pcmWaveNumber(0) != 0x134 || opl4.pcmFnum(0) != 0x2d5) {
        std::cerr << "OPL4 register 20h wave/F-number bit layout is wrong\n";
        return 1;
    }

    opl4Write(opl4, 0x08, 0x80); // RAM wave 384
    opl4Write(opl4, 0x20, 0x01);
    opl4Write(opl4, 0x38, 0x00);
    opl4Write(opl4, 0x50, 0x00);
    opl4Write(opl4, 0x68, 0x88); // key on, center
    energy = 0;
    for (int i = 0; i < 44100 / 4; ++i) energy += std::abs(opl4.sample());
    if (energy < 1.0 || opl4.customSampleCount() != 1 || opl4.pcmWriteCount() < 5) {
        std::cerr << "OPL4 PCM did not produce audio\n";
        return 1;
    }

    // YMF278B ROM PCM format regression. Format 01 is 12-bit and uses
    // Yamaha's three-byte/two-sample nibble layout; format 10 is 16-bit.
    {
        constexpr uint32_t rom_size = 2u * 1024u * 1024u;
        constexpr uint32_t sample_count = 256;
        std::vector<uint8_t> rom(rom_size, 0);
        auto putHeader = [&](int wave, uint8_t format, uint32_t start) {
            const size_t h = static_cast<size_t>(wave) * 12;
            rom[h + 0] = uint8_t((format << 6) | ((start >> 16) & 0x3f));
            rom[h + 1] = uint8_t(start >> 8);
            rom[h + 2] = uint8_t(start);
            rom[h + 3] = 0; rom[h + 4] = 0;
            const uint16_t end = uint16_t(0u - sample_count);
            rom[h + 5] = uint8_t(end >> 8);
            rom[h + 6] = uint8_t(end);
        };
        putHeader(0, 1, 0x1000); // 12-bit
        putHeader(1, 2, 0x2000); // 16-bit
        for (uint32_t i = 0; i < sample_count; i += 2) {
            const auto s0 = int16_t(std::sin(6.283185307179586 * i / 32.0) * 1800.0);
            const auto s1 = int16_t(std::sin(6.283185307179586 * (i + 1) / 32.0) * 1800.0);
            const uint16_t u0 = uint16_t(s0) & 0x0fff;
            const uint16_t u1 = uint16_t(s1) & 0x0fff;
            const uint32_t a = 0x1000 + (i / 2) * 3;
            rom[a + 0] = uint8_t(u0 >> 4);
            rom[a + 1] = uint8_t(((u1 & 0x0f) << 4) | (u0 & 0x0f));
            rom[a + 2] = uint8_t(u1 >> 4);
        }
        for (uint32_t i = 0; i < sample_count; ++i) {
            const int16_t v = int16_t(std::sin(6.283185307179586 * i / 32.0) * 28000.0);
            rom[0x2000 + i * 2] = uint8_t(uint16_t(v) >> 8);
            rom[0x2001 + i * 2] = uint8_t(v);
        }
        const std::string rom_path = "/tmp/tinyksp_yamaha_smoke_yrw801.rom";
        { std::ofstream out(rom_path, std::ios::binary); out.write(reinterpret_cast<const char*>(rom.data()), rom.size()); }
        auto smoothness = [&](uint8_t wave) {
            Opl4Device d; d.reset(44100); std::string e;
            if (!d.loadYrw801Rom(rom_path, e)) return 1000.0;
            opl4Write(d, 0x08, wave);
            opl4Write(d, 0x20, 0x00);
            opl4Write(d, 0x38, 0x00);
            opl4Write(d, 0x50, 0x00);
            opl4Write(d, 0x98, 0xf0);
            opl4Write(d, 0xb0, 0x00);
            opl4Write(d, 0xc8, 0x0f);
            opl4Write(d, 0x68, 0x88);
            double difference = 0.0, magnitude = 0.0;
            float previous = 0.0f;
            for (int i = 0; i < 512; ++i) {
                const float current = d.sample();
                if (i >= 64) {
                    difference += std::abs(current - previous);
                    magnitude += std::abs(current);
                }
                previous = current;
            }
            return difference / std::max(1e-9, magnitude);
        };
        const double smooth12 = smoothness(0);
        const double smooth16 = smoothness(1);
        std::remove(rom_path.c_str());
        if (smooth12 > 0.35 || smooth16 > 0.35) {
            std::cerr << "OPL4 12/16-bit PCM decoding is wrong: " << smooth12 << ", " << smooth16 << '\n';
            return 1;
        }
    }

    // Custom MWK 12-bit length regression. MWK stores payload bytes, but the
    // OPL4 end field is a decoded-sample count. For 256 12-bit samples the
    // payload is 384 bytes; using 384 as the voice length reads 128 samples
    // beyond the payload instead of looping at sample 256.
    {
        constexpr uint32_t sample_count = 256;
        std::vector<uint8_t> custom12;
        custom12.insert(custom12.end(), {'M','B','M','S',0x10,0x0d,0,0,0,0});
        std::vector<uint8_t> flags12(64, 0); flags12[0] = 0x41; // present + 12-bit
        custom12.insert(custom12.end(), flags12.begin(), flags12.end());
        uint8_t header12[13] = {};
        header12[2] = 0; header12[3] = 0; // loop at sample zero
        const uint16_t end12 = uint16_t(0u - sample_count);
        header12[4] = uint8_t(end12 >> 8); header12[5] = uint8_t(end12);
        header12[6] = 0xf0; header12[7] = 0xf0; header12[8] = 0x00;
        header12[9] = 0xf0; header12[10] = 0xf7;
        constexpr uint16_t payload_bytes = 384;
        header12[11] = uint8_t(payload_bytes); header12[12] = uint8_t(payload_bytes >> 8);
        custom12.insert(custom12.end(), header12, header12 + 13);
        for (uint32_t i = 0; i < sample_count; i += 2) {
            const int16_t s0 = int16_t(std::sin(6.283185307179586 * i / 32.0) * 1800.0);
            const int16_t s1 = int16_t(std::sin(6.283185307179586 * (i + 1) / 32.0) * 1800.0);
            const uint16_t u0 = uint16_t(s0) & 0x0fff;
            const uint16_t u1 = uint16_t(s1) & 0x0fff;
            custom12.push_back(uint8_t(u0 >> 4));
            custom12.push_back(uint8_t(((u1 & 0x0f) << 4) | (u0 & 0x0f)));
            custom12.push_back(uint8_t(u1 >> 4));
        }
        Opl4Device d; d.reset(44100); std::string e;
        if (!d.loadMwk(custom12, e)) {
            std::cerr << "custom 12-bit MWK load failed: " << e << '\n';
            return 1;
        }
        opl4Write(d, 0x08, 0x80); // RAM wave 384
        opl4Write(d, 0x20, 0x01);
        opl4Write(d, 0x38, 0x10); // normal 44.1 kHz
        opl4Write(d, 0x50, 0x00);
        opl4Write(d, 0x98, 0xf0);
        opl4Write(d, 0xb0, 0x00);
        opl4Write(d, 0xc8, 0x0f);
        opl4Write(d, 0x68, 0x88);
        double post_loop_energy = 0.0;
        for (int i = 0; i < 384; ++i) {
            const float v = d.sample();
            if (i >= 272) post_loop_energy += std::abs(v);
        }
        if (post_loop_energy < 1.0) {
            std::cerr << "custom 12-bit MWK used payload bytes as sample length\n";
            return 1;
        }
    }

    // YMF278B pitch regression: FNUM=0 and OCTAVE=1 is normal 44.1 kHz
    // playback, so the 32-sample test sine must produce about 128 cycles in
    // 4096 output samples. The old code produced about 256 cycles (one octave high).
    {
        Opl4Device pitch;
        pitch.reset(44100);
        if (!pitch.loadMwk(mwk, error)) {
            std::cerr << "pitch-test MWK load failed: " << error << '\n';
            return 1;
        }
        opl4Write(pitch, 0x08, 0x80); // RAM wave 384
        opl4Write(pitch, 0x20, 0x01); // wave bit 8, FNUM low zero
        opl4Write(pitch, 0x38, 0x10); // OCTAVE=1, FNUM high zero
        opl4Write(pitch, 0x50, 0x00);
        opl4Write(pitch, 0x98, 0xf0); // immediate attack
        opl4Write(pitch, 0xb0, 0x00);
        opl4Write(pitch, 0xc8, 0x0f);
        opl4Write(pitch, 0x68, 0x88);
        int rising = 0;
        float previous = pitch.sample();
        for (int i = 1; i < 4096 + 128; ++i) {
            const float current = pitch.sample();
            if (i >= 128 && previous <= 0.0f && current > 0.0f) ++rising;
            previous = current;
        }
        if (rising < 118 || rising > 138) {
            std::cerr << "OPL4 normal-pitch octave is wrong; rising crossings=" << rising << '\n';
            return 1;
        }
    }

    std::vector<uint8_t> bad = mwk;
    bad.resize(20);
    if (opl4.loadMwk(bad, error)) {
        std::cerr << "truncated MWK was accepted\n";
        return 1;
    }
    std::cout << "YM2413 and OPL4/MWK smoke tests passed\n";
    return 0;
}
