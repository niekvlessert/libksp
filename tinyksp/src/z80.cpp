#include "z80.h"

#include <algorithm>
#include <iomanip>
#include <sstream>
#include <utility>

namespace tinyksp {

Z80::Z80(Z80Bus& bus) : bus_(bus) { reset(); }

void Z80::reset() {
    a_ = f_ = b_ = c_ = d_ = e_ = h_ = l_ = 0;
    a2_ = f2_ = b2_ = c2_ = d2_ = e2_ = h2_ = l2_ = 0;
    ix_ = iy_ = 0;
    sp_ = 0xffff;
    pc_ = 0;
    i_ = r_ = 0;
    iff1_ = iff2_ = false;
    halted_ = false;
    im_ = 0;
}

uint8_t Z80::fetch8() {
    const uint8_t value = bus_.opcodeRead(pc_++);
    r_ = static_cast<uint8_t>((r_ & 0x80) | ((r_ + 1) & 0x7f));
    return value;
}

uint16_t Z80::fetch16() {
    const uint8_t lo = fetch8();
    const uint8_t hi = fetch8();
    return static_cast<uint16_t>(lo | (hi << 8));
}

uint16_t Z80::read16(uint16_t address) {
    const uint8_t lo = bus_.memRead(address);
    const uint8_t hi = bus_.memRead(static_cast<uint16_t>(address + 1));
    return static_cast<uint16_t>(lo | (hi << 8));
}

void Z80::write16(uint16_t address, uint16_t value) {
    bus_.memWrite(address, static_cast<uint8_t>(value));
    bus_.memWrite(static_cast<uint16_t>(address + 1), static_cast<uint8_t>(value >> 8));
}

void Z80::push(uint16_t value) {
    bus_.memWrite(--sp_, static_cast<uint8_t>(value >> 8));
    bus_.memWrite(--sp_, static_cast<uint8_t>(value));
}

uint16_t Z80::pop() {
    const uint8_t lo = bus_.memRead(sp_++);
    const uint8_t hi = bus_.memRead(sp_++);
    return static_cast<uint16_t>(lo | (hi << 8));
}

bool Z80::parity(uint8_t value) {
    value ^= static_cast<uint8_t>(value >> 4);
    value &= 0x0f;
    return ((0x6996u >> value) & 1u) == 0;
}

uint8_t Z80::sz53(uint8_t value) {
    return static_cast<uint8_t>((value & (S | Y | X)) | (value == 0 ? Z : 0));
}

uint8_t Z80::szp53(uint8_t value) {
    return static_cast<uint8_t>(sz53(value) | (parity(value) ? PV : 0));
}

bool Z80::condition(int code) const {
    switch (code & 7) {
    case 0: return !(f_ & Z);
    case 1: return (f_ & Z) != 0;
    case 2: return !(f_ & C);
    case 3: return (f_ & C) != 0;
    case 4: return !(f_ & PV);
    case 5: return (f_ & PV) != 0;
    case 6: return !(f_ & S);
    default: return (f_ & S) != 0;
    }
}

uint16_t Z80::getRP(int p, Index index) const {
    switch (p & 3) {
    case 0: return bc();
    case 1: return de();
    case 2: return index == Index::IX ? ix_ : index == Index::IY ? iy_ : hl();
    default: return sp_;
    }
}

void Z80::setRP(int p, Index index, uint16_t value) {
    switch (p & 3) {
    case 0: b_ = static_cast<uint8_t>(value >> 8); c_ = static_cast<uint8_t>(value); break;
    case 1: d_ = static_cast<uint8_t>(value >> 8); e_ = static_cast<uint8_t>(value); break;
    case 2:
        if (index == Index::IX) ix_ = value;
        else if (index == Index::IY) iy_ = value;
        else setHL(value);
        break;
    default: sp_ = value; break;
    }
}

uint16_t Z80::getRP2(int p, Index index) const {
    if ((p & 3) == 3) return af();
    return getRP(p, index);
}

void Z80::setRP2(int p, Index index, uint16_t value) {
    if ((p & 3) == 3) {
        a_ = static_cast<uint8_t>(value >> 8);
        f_ = static_cast<uint8_t>(value);
    } else {
        setRP(p, index, value);
    }
}

uint16_t Z80::indexedAddress(Index index, bool& displacement_ready, int8_t& displacement) {
    if (index == Index::None) return hl();
    if (!displacement_ready) {
        displacement = static_cast<int8_t>(fetch8());
        displacement_ready = true;
    }
    const uint16_t base = index == Index::IX ? ix_ : iy_;
    return static_cast<uint16_t>(base + displacement);
}

uint8_t Z80::readR(int r, Index index, bool& displacement_ready, int8_t& displacement) {
    switch (r & 7) {
    case 0: return b_;
    case 1: return c_;
    case 2: return d_;
    case 3: return e_;
    case 4:
        if (index == Index::IX) return static_cast<uint8_t>(ix_ >> 8);
        if (index == Index::IY) return static_cast<uint8_t>(iy_ >> 8);
        return h_;
    case 5:
        if (index == Index::IX) return static_cast<uint8_t>(ix_);
        if (index == Index::IY) return static_cast<uint8_t>(iy_);
        return l_;
    case 6: return bus_.memRead(indexedAddress(index, displacement_ready, displacement));
    default: return a_;
    }
}

void Z80::writeR(int r, Index index, bool& displacement_ready, int8_t& displacement, uint8_t value) {
    switch (r & 7) {
    case 0: b_ = value; break;
    case 1: c_ = value; break;
    case 2: d_ = value; break;
    case 3: e_ = value; break;
    case 4:
        if (index == Index::IX) ix_ = static_cast<uint16_t>((value << 8) | (ix_ & 0xff));
        else if (index == Index::IY) iy_ = static_cast<uint16_t>((value << 8) | (iy_ & 0xff));
        else h_ = value;
        break;
    case 5:
        if (index == Index::IX) ix_ = static_cast<uint16_t>((ix_ & 0xff00) | value);
        else if (index == Index::IY) iy_ = static_cast<uint16_t>((iy_ & 0xff00) | value);
        else l_ = value;
        break;
    case 6: bus_.memWrite(indexedAddress(index, displacement_ready, displacement), value); break;
    default: a_ = value; break;
    }
}

uint8_t Z80::inc8(uint8_t value) {
    const uint8_t result = static_cast<uint8_t>(value + 1);
    f_ = static_cast<uint8_t>((f_ & C) | sz53(result) |
                              ((value & 0x0f) == 0x0f ? H : 0) |
                              (value == 0x7f ? PV : 0));
    return result;
}

uint8_t Z80::dec8(uint8_t value) {
    const uint8_t result = static_cast<uint8_t>(value - 1);
    f_ = static_cast<uint8_t>((f_ & C) | sz53(result) | N |
                              ((value & 0x0f) == 0 ? H : 0) |
                              (value == 0x80 ? PV : 0));
    return result;
}

uint8_t Z80::add8(uint8_t lhs, uint8_t rhs, bool carry) {
    const uint16_t ci = carry && (f_ & C) ? 1 : 0;
    const uint16_t sum = static_cast<uint16_t>(lhs) + rhs + ci;
    const uint8_t result = static_cast<uint8_t>(sum);
    f_ = static_cast<uint8_t>(sz53(result) |
                              (((lhs ^ rhs ^ result) & 0x10) ? H : 0) |
                              ((~(lhs ^ rhs) & (lhs ^ result) & 0x80) ? PV : 0) |
                              (sum & 0x100 ? C : 0));
    return result;
}

uint8_t Z80::sub8(uint8_t lhs, uint8_t rhs, bool carry) {
    const uint16_t ci = carry && (f_ & C) ? 1 : 0;
    const uint16_t diff = static_cast<uint16_t>(lhs) - rhs - ci;
    const uint8_t result = static_cast<uint8_t>(diff);
    f_ = static_cast<uint8_t>(sz53(result) | N |
                              (((lhs ^ rhs ^ result) & 0x10) ? H : 0) |
                              (((lhs ^ rhs) & (lhs ^ result) & 0x80) ? PV : 0) |
                              (diff & 0x100 ? C : 0));
    return result;
}

void Z80::cp8(uint8_t lhs, uint8_t rhs) {
    const uint16_t diff = static_cast<uint16_t>(lhs) - rhs;
    const uint8_t result = static_cast<uint8_t>(diff);
    f_ = static_cast<uint8_t>((result & S) | (result == 0 ? Z : 0) |
                              (rhs & (Y | X)) | N |
                              (((lhs ^ rhs ^ result) & 0x10) ? H : 0) |
                              (((lhs ^ rhs) & (lhs ^ result) & 0x80) ? PV : 0) |
                              (diff & 0x100 ? C : 0));
}

uint16_t Z80::add16(uint16_t lhs, uint16_t rhs) {
    const uint32_t sum = static_cast<uint32_t>(lhs) + rhs;
    const uint16_t result = static_cast<uint16_t>(sum);
    f_ = static_cast<uint8_t>((f_ & (S | Z | PV)) |
                              ((result >> 8) & (Y | X)) |
                              (((lhs ^ rhs ^ result) & 0x1000) ? H : 0) |
                              (sum & 0x10000 ? C : 0));
    return result;
}

uint16_t Z80::adc16(uint16_t lhs, uint16_t rhs, bool subtract) {
    const uint32_t ci = (f_ & C) ? 1u : 0u;
    const uint32_t wide = subtract ? static_cast<uint32_t>(lhs) - rhs - ci
                                   : static_cast<uint32_t>(lhs) + rhs + ci;
    const uint16_t result = static_cast<uint16_t>(wide);
    const bool half = ((lhs ^ rhs ^ result) & 0x1000) != 0;
    const bool overflow = subtract
        ? (((lhs ^ rhs) & (lhs ^ result) & 0x8000) != 0)
        : ((~(lhs ^ rhs) & (lhs ^ result) & 0x8000) != 0);
    f_ = static_cast<uint8_t>(((result >> 8) & (S | Y | X)) |
                              (result == 0 ? Z : 0) |
                              (half ? H : 0) |
                              (overflow ? PV : 0) |
                              (subtract ? N : 0) |
                              ((wide & 0x10000) ? C : 0));
    return result;
}

void Z80::alu(int operation, uint8_t value) {
    switch (operation & 7) {
    case 0: a_ = add8(a_, value, false); break;
    case 1: a_ = add8(a_, value, true); break;
    case 2: a_ = sub8(a_, value, false); break;
    case 3: a_ = sub8(a_, value, true); break;
    case 4: a_ &= value; f_ = static_cast<uint8_t>(szp53(a_) | H); break;
    case 5: a_ ^= value; f_ = szp53(a_); break;
    case 6: a_ |= value; f_ = szp53(a_); break;
    default: cp8(a_, value); break;
    }
}

void Z80::daa() {
    const uint8_t before = a_;
    uint8_t correction = 0;
    bool carry = (f_ & C) != 0;
    if (!(f_ & N)) {
        if ((f_ & H) || (a_ & 0x0f) > 9) correction |= 0x06;
        if (carry || a_ > 0x99) { correction |= 0x60; carry = true; }
        a_ = static_cast<uint8_t>(a_ + correction);
    } else {
        if (f_ & H) correction |= 0x06;
        if (carry) correction |= 0x60;
        a_ = static_cast<uint8_t>(a_ - correction);
    }
    f_ = static_cast<uint8_t>((f_ & N) | szp53(a_) |
                              (((before ^ a_) & 0x10) ? H : 0) |
                              (carry ? C : 0));
}

int Z80::executeCB(Index index, bool indexed, int8_t displacement) {
    const uint8_t opcode = fetch8();
    const int x = opcode >> 6;
    const int y = (opcode >> 3) & 7;
    const int z = opcode & 7;
    bool disp_ready = indexed;
    int8_t disp = displacement;
    uint8_t value;
    uint16_t address = 0;
    if (indexed) {
        const uint16_t base = index == Index::IX ? ix_ : iy_;
        address = static_cast<uint16_t>(base + displacement);
        value = bus_.memRead(address);
    } else {
        value = readR(z, Index::None, disp_ready, disp);
    }

    if (x == 0) {
        uint8_t result = value;
        uint8_t carry = 0;
        switch (y) {
        case 0: carry = static_cast<uint8_t>(value >> 7); result = static_cast<uint8_t>((value << 1) | carry); break;
        case 1: carry = value & 1; result = static_cast<uint8_t>((value >> 1) | (carry << 7)); break;
        case 2: carry = static_cast<uint8_t>(value >> 7); result = static_cast<uint8_t>((value << 1) | ((f_ & C) ? 1 : 0)); break;
        case 3: carry = value & 1; result = static_cast<uint8_t>((value >> 1) | ((f_ & C) ? 0x80 : 0)); break;
        case 4: carry = static_cast<uint8_t>(value >> 7); result = static_cast<uint8_t>(value << 1); break;
        case 5: carry = value & 1; result = static_cast<uint8_t>((value >> 1) | (value & 0x80)); break;
        case 6: carry = static_cast<uint8_t>(value >> 7); result = static_cast<uint8_t>((value << 1) | 1); break;
        case 7: carry = value & 1; result = static_cast<uint8_t>(value >> 1); break;
        }
        f_ = static_cast<uint8_t>(szp53(result) | (carry ? C : 0));
        if (indexed) {
            bus_.memWrite(address, result);
            if (z != 6) {
                bool dummy = true; int8_t zero = 0;
                writeR(z, Index::None, dummy, zero, result);
            }
        } else {
            writeR(z, Index::None, disp_ready, disp, result);
        }
    } else if (x == 1) {
        const bool clear = (value & (1u << y)) == 0;
        f_ = static_cast<uint8_t>((f_ & C) | H | (clear ? (Z | PV) : 0) |
                                  ((y == 7 && !clear) ? S : 0) |
                                  (value & (Y | X)));
    } else {
        uint8_t result = x == 2 ? static_cast<uint8_t>(value & ~(1u << y))
                                : static_cast<uint8_t>(value | (1u << y));
        if (indexed) {
            bus_.memWrite(address, result);
            if (z != 6) {
                bool dummy = true; int8_t zero = 0;
                writeR(z, Index::None, dummy, zero, result);
            }
        } else {
            writeR(z, Index::None, disp_ready, disp, result);
        }
    }
    return indexed ? 23 : (z == 6 ? 15 : 8);
}

int Z80::executeED() {
    const uint8_t opcode = fetch8();
    const int x = opcode >> 6;
    const int y = (opcode >> 3) & 7;
    const int z = opcode & 7;
    const int p = y >> 1;
    const int q = y & 1;

    if (x == 1) {
        switch (z) {
        case 0: { // IN r,(C)
            const uint8_t value = bus_.ioRead(bc());
            if (y != 6) {
                bool ready = true; int8_t disp = 0;
                writeR(y, Index::None, ready, disp, value);
            }
            f_ = static_cast<uint8_t>((f_ & C) | szp53(value));
            return 12;
        }
        case 1: { // OUT (C),r
            uint8_t value = 0;
            if (y != 6) {
                bool ready = true; int8_t disp = 0;
                value = readR(y, Index::None, ready, disp);
            }
            bus_.ioWrite(bc(), value);
            return 12;
        }
        case 2: { // SBC/ADC HL,rp
            const uint16_t result = adc16(hl(), getRP(p, Index::None), q == 0);
            setHL(result);
            return 15;
        }
        case 3: { // LD (nn),rp / rp,(nn)
            const uint16_t address = fetch16();
            if (q == 0) write16(address, getRP(p, Index::None));
            else setRP(p, Index::None, read16(address));
            return 20;
        }
        case 4: // NEG aliases
            a_ = sub8(0, a_, false);
            return 8;
        case 5: // RETN/RETI aliases
            pc_ = pop(); iff1_ = iff2_; return 14;
        case 6: { // IM
            static constexpr uint8_t modes[8] = {0,0,1,2,0,0,1,2};
            im_ = modes[y];
            return 8;
        }
        case 7:
            switch (y) {
            case 0: i_ = a_; return 9;
            case 1: r_ = a_; return 9;
            case 2:
                a_ = i_;
                f_ = static_cast<uint8_t>((f_ & C) | sz53(a_) | (iff2_ ? PV : 0));
                return 9;
            case 3:
                a_ = r_;
                f_ = static_cast<uint8_t>((f_ & C) | sz53(a_) | (iff2_ ? PV : 0));
                return 9;
            case 4: { // RRD
                const uint8_t m = bus_.memRead(hl());
                const uint8_t next_m = static_cast<uint8_t>((a_ << 4) | (m >> 4));
                a_ = static_cast<uint8_t>((a_ & 0xf0) | (m & 0x0f));
                bus_.memWrite(hl(), next_m);
                f_ = static_cast<uint8_t>((f_ & C) | szp53(a_));
                return 18;
            }
            case 5: { // RLD
                const uint8_t m = bus_.memRead(hl());
                const uint8_t next_m = static_cast<uint8_t>((m << 4) | (a_ & 0x0f));
                a_ = static_cast<uint8_t>((a_ & 0xf0) | (m >> 4));
                bus_.memWrite(hl(), next_m);
                f_ = static_cast<uint8_t>((f_ & C) | szp53(a_));
                return 18;
            }
            default: return 8;
            }
        }
    }

    if (x == 2 && y >= 4) {
        const bool decrement = (y & 1) != 0;
        const bool repeat = y >= 6;
        switch (z) {
        case 0: // LDI/LDD/LDIR/LDDR
        {
            const uint8_t value = bus_.memRead(hl());
            bus_.memWrite(de(), value);
            setHL(static_cast<uint16_t>(hl() + (decrement ? -1 : 1)));
            const uint16_t next_de = static_cast<uint16_t>(de() + (decrement ? -1 : 1));
            d_ = static_cast<uint8_t>(next_de >> 8); e_ = static_cast<uint8_t>(next_de);
            const uint16_t next_bc = static_cast<uint16_t>(bc() - 1);
            b_ = static_cast<uint8_t>(next_bc >> 8); c_ = static_cast<uint8_t>(next_bc);
            const uint8_t sum = static_cast<uint8_t>(a_ + value);
            f_ = static_cast<uint8_t>((f_ & (S | Z | C)) | (next_bc ? PV : 0) |
                                      (sum & X) | ((sum << 4) & Y));
            if (repeat && next_bc) { pc_ = static_cast<uint16_t>(pc_ - 2); return 21; }
            return 16;
        }
        case 1: // CPI/CPD/CPIR/CPDR
        {
            const uint8_t value = bus_.memRead(hl());
            const uint8_t result = static_cast<uint8_t>(a_ - value);
            setHL(static_cast<uint16_t>(hl() + (decrement ? -1 : 1)));
            const uint16_t next_bc = static_cast<uint16_t>(bc() - 1);
            b_ = static_cast<uint8_t>(next_bc >> 8); c_ = static_cast<uint8_t>(next_bc);
            const bool half = ((a_ ^ value ^ result) & 0x10) != 0;
            const uint8_t adjusted = static_cast<uint8_t>(result - (half ? 1 : 0));
            f_ = static_cast<uint8_t>((f_ & C) | (result & S) | (result == 0 ? Z : 0) |
                                      (half ? H : 0) | (next_bc ? PV : 0) | N |
                                      (adjusted & X) | ((adjusted << 4) & Y));
            if (repeat && next_bc && result != 0) { pc_ = static_cast<uint16_t>(pc_ - 2); return 21; }
            return 16;
        }
        case 2: // INI/IND/INIR/INDR
        {
            const uint8_t value = bus_.ioRead(bc());
            bus_.memWrite(hl(), value);
            setHL(static_cast<uint16_t>(hl() + (decrement ? -1 : 1)));
            b_ = static_cast<uint8_t>(b_ - 1);
            const uint16_t k = static_cast<uint16_t>(value + static_cast<uint8_t>(c_ + (decrement ? -1 : 1)));
            f_ = static_cast<uint8_t>(sz53(b_) | (value & 0x80 ? N : 0) |
                                      (k & 0x100 ? (H | C) : 0) |
                                      (parity(static_cast<uint8_t>((k & 7) ^ b_)) ? PV : 0));
            if (repeat && b_ != 0) { pc_ = static_cast<uint16_t>(pc_ - 2); return 21; }
            return 16;
        }
        case 3: // OUTI/OUTD/OTIR/OTDR
        {
            const uint8_t value = bus_.memRead(hl());
            bus_.ioWrite(bc(), value);
            setHL(static_cast<uint16_t>(hl() + (decrement ? -1 : 1)));
            b_ = static_cast<uint8_t>(b_ - 1);
            const uint16_t k = static_cast<uint16_t>(value + static_cast<uint8_t>(l_));
            f_ = static_cast<uint8_t>(sz53(b_) | (value & 0x80 ? N : 0) |
                                      (k & 0x100 ? (H | C) : 0) |
                                      (parity(static_cast<uint8_t>((k & 7) ^ b_)) ? PV : 0));
            if (repeat && b_ != 0) { pc_ = static_cast<uint16_t>(pc_ - 2); return 21; }
            return 16;
        }
        default: return 8;
        }
    }

    return 8; // documented NOP behavior for undefined ED opcodes
}

int Z80::executeBase(uint8_t opcode, Index index) {
    const int x = opcode >> 6;
    const int y = (opcode >> 3) & 7;
    const int z = opcode & 7;
    const int p = y >> 1;
    const int q = y & 1;
    bool disp_ready = false;
    int8_t disp = 0;
    const int prefix_cost = index == Index::None ? 0 : 4;

    if (x == 0) {
        switch (z) {
        case 0:
            switch (y) {
            case 0: return 4 + prefix_cost;
            case 1: std::swap(a_, a2_); std::swap(f_, f2_); return 4 + prefix_cost;
            case 2: {
                const int8_t offset = static_cast<int8_t>(fetch8());
                b_ = static_cast<uint8_t>(b_ - 1);
                if (b_) { pc_ = static_cast<uint16_t>(pc_ + offset); return 13 + prefix_cost; }
                return 8 + prefix_cost;
            }
            case 3: {
                const int8_t offset = static_cast<int8_t>(fetch8());
                pc_ = static_cast<uint16_t>(pc_ + offset);
                return 12 + prefix_cost;
            }
            default: {
                const int8_t offset = static_cast<int8_t>(fetch8());
                if (condition(y - 4)) { pc_ = static_cast<uint16_t>(pc_ + offset); return 12 + prefix_cost; }
                return 7 + prefix_cost;
            }
            }
        case 1:
            if (!q) { setRP(p, index, fetch16()); return 10 + prefix_cost; }
            setRP(2, index, add16(getRP(2, index), getRP(p, index)));
            return 11 + prefix_cost;
        case 2:
            if (!q) {
                switch (p) {
                case 0: bus_.memWrite(bc(), a_); return 7 + prefix_cost;
                case 1: bus_.memWrite(de(), a_); return 7 + prefix_cost;
                case 2: { const uint16_t nn = fetch16(); write16(nn, getRP(2, index)); return 16 + prefix_cost; }
                default: { const uint16_t nn = fetch16(); bus_.memWrite(nn, a_); return 13 + prefix_cost; }
                }
            } else {
                switch (p) {
                case 0: a_ = bus_.memRead(bc()); return 7 + prefix_cost;
                case 1: a_ = bus_.memRead(de()); return 7 + prefix_cost;
                case 2: { const uint16_t nn = fetch16(); setRP(2, index, read16(nn)); return 16 + prefix_cost; }
                default: { const uint16_t nn = fetch16(); a_ = bus_.memRead(nn); return 13 + prefix_cost; }
                }
            }
        case 3:
            if (!q) setRP(p, index, static_cast<uint16_t>(getRP(p, index) + 1));
            else setRP(p, index, static_cast<uint16_t>(getRP(p, index) - 1));
            return 6 + prefix_cost;
        case 4: {
            const uint8_t value = readR(y, index, disp_ready, disp);
            writeR(y, index, disp_ready, disp, inc8(value));
            return (y == 6 ? (index == Index::None ? 11 : 23) : 4 + prefix_cost);
        }
        case 5: {
            const uint8_t value = readR(y, index, disp_ready, disp);
            writeR(y, index, disp_ready, disp, dec8(value));
            return (y == 6 ? (index == Index::None ? 11 : 23) : 4 + prefix_cost);
        }
        case 6: {
            if (y == 6 && index != Index::None) indexedAddress(index, disp_ready, disp);
            const uint8_t value = fetch8();
            writeR(y, index, disp_ready, disp, value);
            return y == 6 ? (index == Index::None ? 10 : 19) : 7 + prefix_cost;
        }
        case 7:
            switch (y) {
            case 0: { const uint8_t c = static_cast<uint8_t>(a_ >> 7); a_ = static_cast<uint8_t>((a_ << 1) | c); f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | (c ? C : 0)); break; }
            case 1: { const uint8_t c = a_ & 1; a_ = static_cast<uint8_t>((a_ >> 1) | (c << 7)); f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | (c ? C : 0)); break; }
            case 2: { const uint8_t c = static_cast<uint8_t>(a_ >> 7); a_ = static_cast<uint8_t>((a_ << 1) | ((f_ & C) ? 1 : 0)); f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | (c ? C : 0)); break; }
            case 3: { const uint8_t c = a_ & 1; a_ = static_cast<uint8_t>((a_ >> 1) | ((f_ & C) ? 0x80 : 0)); f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | (c ? C : 0)); break; }
            case 4: daa(); break;
            case 5: a_ ^= 0xff; f_ = static_cast<uint8_t>((f_ & (S|Z|PV|C)) | (a_ & (Y|X)) | H | N); break;
            case 6: f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | C); break;
            case 7: { const bool old = (f_ & C) != 0; f_ = static_cast<uint8_t>((f_ & (S|Z|PV)) | (a_ & (Y|X)) | (old ? H : C)); break; }
            }
            return 4 + prefix_cost;
        }
    }

    if (x == 1) {
        if (y == 6 && z == 6) { halted_ = true; return 4 + prefix_cost; }
        const uint8_t value = readR(z, index, disp_ready, disp);
        // DD/FD LD H/L,(IX+d) and LD (IX+d),H/L use the real H/L registers.
        Index destination_index = index;
        if (index != Index::None && z == 6 && (y == 4 || y == 5)) destination_index = Index::None;
        Index source_index = index;
        if (index != Index::None && y == 6 && (z == 4 || z == 5)) source_index = Index::None;
        uint8_t adjusted = value;
        if (source_index != index) adjusted = readR(z, source_index, disp_ready, disp);
        writeR(y, destination_index, disp_ready, disp, adjusted);
        if (y == 6 || z == 6) return index == Index::None ? 7 : 19;
        return 4 + prefix_cost;
    }

    if (x == 2) {
        alu(y, readR(z, index, disp_ready, disp));
        return z == 6 ? (index == Index::None ? 7 : 19) : 4 + prefix_cost;
    }

    switch (z) {
    case 0:
        if (condition(y)) { pc_ = pop(); return 11 + prefix_cost; }
        return 5 + prefix_cost;
    case 1:
        if (!q) { setRP2(p, index, pop()); return 10 + prefix_cost; }
        switch (p) {
        case 0: pc_ = pop(); return 10 + prefix_cost;
        case 1:
            std::swap(b_, b2_); std::swap(c_, c2_); std::swap(d_, d2_); std::swap(e_, e2_);
            std::swap(h_, h2_); std::swap(l_, l2_); return 4 + prefix_cost;
        case 2: pc_ = getRP(2, index); return 4 + prefix_cost;
        default: sp_ = getRP(2, index); return 6 + prefix_cost;
        }
    case 2: {
        const uint16_t address = fetch16();
        if (condition(y)) pc_ = address;
        return 10 + prefix_cost;
    }
    case 3:
        switch (y) {
        case 0: pc_ = fetch16(); return 10 + prefix_cost;
        case 1: return executeCB(Index::None, false) + prefix_cost;
        case 2: { const uint8_t port = fetch8(); bus_.ioWrite(static_cast<uint16_t>((a_ << 8) | port), a_); return 11 + prefix_cost; }
        case 3: { const uint8_t port = fetch8(); a_ = bus_.ioRead(static_cast<uint16_t>((a_ << 8) | port)); return 11 + prefix_cost; }
        case 4: { const uint16_t value = read16(sp_); write16(sp_, getRP(2, index)); setRP(2, index, value); return 19 + prefix_cost; }
        case 5: { // Prefix does not alter EX DE,HL.
            const uint16_t value = de();
            d_ = h_; e_ = l_; setHL(value); return 4 + prefix_cost;
        }
        case 6: iff1_ = iff2_ = false; return 4 + prefix_cost;
        default: iff1_ = iff2_ = true; return 4 + prefix_cost;
        }
    case 4: {
        const uint16_t address = fetch16();
        if (condition(y)) { push(pc_); pc_ = address; return 17 + prefix_cost; }
        return 10 + prefix_cost;
    }
    case 5:
        if (!q) { push(getRP2(p, index)); return 11 + prefix_cost; }
        if (p == 0) { const uint16_t address = fetch16(); push(pc_); pc_ = address; return 17 + prefix_cost; }
        return 4 + prefix_cost; // nested prefixes handled by step()
    case 6:
        alu(y, fetch8()); return 7 + prefix_cost;
    case 7:
        push(pc_); pc_ = static_cast<uint16_t>(y * 8); return 11 + prefix_cost;
    }
    return 4 + prefix_cost;
}

int Z80::step() {
    if (halted_) return 4;
    Index index = Index::None;
    int prefixes = 0;
    while (true) {
        const uint8_t opcode = fetch8();
        if (opcode == 0xdd || opcode == 0xfd) {
            index = opcode == 0xdd ? Index::IX : Index::IY;
            ++prefixes;
            continue;
        }
        if (opcode == 0xcb) {
            if (index != Index::None) {
                const int8_t displacement = static_cast<int8_t>(fetch8());
                return executeCB(index, true, displacement) + std::max(0, prefixes - 1) * 4;
            }
            return executeCB(Index::None, false) + prefixes * 4;
        }
        if (opcode == 0xed) return executeED() + prefixes * 4;
        return executeBase(opcode, index) + std::max(0, prefixes - (index == Index::None ? 0 : 1)) * 4;
    }
}

bool Z80::call(uint16_t address, uint64_t cycle_limit, std::string& error) {
    constexpr uint16_t sentinel = 0xffff;
    halted_ = false;
    push(sentinel);
    pc_ = address;
    uint64_t cycles = 0;
    while (pc_ != sentinel) {
        if (cycles >= cycle_limit) {
            std::ostringstream out;
            out << "Z80 routine exceeded cycle limit at PC=$" << std::hex << std::setw(4)
                << std::setfill('0') << pc_;
            error = out.str();
            return false;
        }
        cycles += static_cast<uint64_t>(step());
        if (halted_) {
            error = "Z80 routine halted before returning";
            return false;
        }
    }
    return true;
}

} // namespace tinyksp
