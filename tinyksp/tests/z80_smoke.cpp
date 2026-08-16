#include "z80.h"

#include <array>
#include <cstdint>
#include <iostream>
#include <string>

class Bus final : public tinyksp::Z80Bus {
public:
    uint8_t memRead(uint16_t a) override { return mem[a]; }
    void memWrite(uint16_t a, uint8_t v) override { mem[a] = v; }
    uint8_t ioRead(uint16_t p) override { return ports[p & 0xff]; }
    void ioWrite(uint16_t p, uint8_t v) override { ports[p & 0xff] = v; }
    std::array<uint8_t,65536> mem{};
    std::array<uint8_t,256> ports{};
};

int main() {
    Bus bus;
    // Covers IX displacement, DDCB, LDIR, arithmetic, port I/O and RET.
    const uint8_t program[] = {
        0xdd,0x21,0x00,0x20,       // LD IX,2000
        0xdd,0x36,0x01,0x7f,       // LD (IX+1),7F
        0xdd,0x34,0x01,            // INC (IX+1) -> 80
        0xdd,0xcb,0x01,0xc6,       // SET 0,(IX+1) -> 81
        0xdd,0x7e,0x01,            // LD A,(IX+1)
        0xc6,0x01,                 // ADD A,1 -> 82
        0xd3,0xa1,                 // OUT (A1),A
        0x21,0x00,0x21,            // LD HL,2100
        0x11,0x00,0x22,            // LD DE,2200
        0x01,0x04,0x00,            // LD BC,4
        0xed,0xb0,                 // LDIR
        0xc9
    };
    for (size_t i=0;i<sizeof(program);++i) bus.mem[0x4000+i]=program[i];
    bus.mem[0x2100]=1; bus.mem[0x2101]=2; bus.mem[0x2102]=3; bus.mem[0x2103]=4;
    tinyksp::Z80 cpu(bus);
    cpu.setSP(0xf000);
    std::string error;
    if (!cpu.call(0x4000, 100000, error)) { std::cerr << error << "\n"; return 1; }
    if (bus.mem[0x2001] != 0x81 || bus.ports[0xa1] != 0x82) return 2;
    for (int i=0;i<4;++i) if (bus.mem[0x2200+i] != i+1) return 3;
    if (cpu.bc() != 0 || cpu.hl() != 0x2104 || cpu.de() != 0x2204) return 4;
    std::cout << "Z80 base/index/CB/ED smoke test passed\n";
    return 0;
}
