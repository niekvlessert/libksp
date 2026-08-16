#pragma once

#include <cstdint>
#include <string>

namespace tinyksp {

class Z80Bus {
public:
    virtual ~Z80Bus() = default;
    virtual uint8_t memRead(uint16_t address) = 0;
    virtual uint8_t opcodeRead(uint16_t address) { return memRead(address); }
    virtual void memWrite(uint16_t address, uint8_t value) = 0;
    virtual uint8_t ioRead(uint16_t port) = 0;
    virtual void ioWrite(uint16_t port, uint8_t value) = 0;
};

class Z80 {
public:
    explicit Z80(Z80Bus& bus);

    void reset();
    int step();
    bool call(uint16_t address, uint64_t cycle_limit, std::string& error);

    uint16_t af() const { return static_cast<uint16_t>((a_ << 8) | f_); }
    uint16_t bc() const { return static_cast<uint16_t>((b_ << 8) | c_); }
    uint16_t de() const { return static_cast<uint16_t>((d_ << 8) | e_); }
    uint16_t hl() const { return static_cast<uint16_t>((h_ << 8) | l_); }
    uint16_t ix() const { return ix_; }
    uint16_t iy() const { return iy_; }
    uint16_t sp() const { return sp_; }
    uint16_t pc() const { return pc_; }

    void setA(uint8_t value) { a_ = value; }
    void setHL(uint16_t value) { h_ = static_cast<uint8_t>(value >> 8); l_ = static_cast<uint8_t>(value); }
    void setSP(uint16_t value) { sp_ = value; }
    void setPC(uint16_t value) { pc_ = value; }

private:
    enum class Index : uint8_t { None, IX, IY };

    static constexpr uint8_t S = 0x80;
    static constexpr uint8_t Z = 0x40;
    static constexpr uint8_t Y = 0x20;
    static constexpr uint8_t H = 0x10;
    static constexpr uint8_t X = 0x08;
    static constexpr uint8_t PV = 0x04;
    static constexpr uint8_t N = 0x02;
    static constexpr uint8_t C = 0x01;

    uint8_t fetch8();
    uint16_t fetch16();
    uint16_t read16(uint16_t address);
    void write16(uint16_t address, uint16_t value);
    void push(uint16_t value);
    uint16_t pop();

    uint16_t getRP(int p, Index index) const;
    void setRP(int p, Index index, uint16_t value);
    uint16_t getRP2(int p, Index index) const;
    void setRP2(int p, Index index, uint16_t value);
    uint16_t indexedAddress(Index index, bool& displacement_ready, int8_t& displacement);
    uint8_t readR(int r, Index index, bool& displacement_ready, int8_t& displacement);
    void writeR(int r, Index index, bool& displacement_ready, int8_t& displacement, uint8_t value);

    int executeBase(uint8_t opcode, Index index);
    int executeCB(Index index, bool indexed, int8_t displacement = 0);
    int executeED();

    bool condition(int code) const;
    static bool parity(uint8_t value);
    static uint8_t sz53(uint8_t value);
    static uint8_t szp53(uint8_t value);

    uint8_t inc8(uint8_t value);
    uint8_t dec8(uint8_t value);
    uint8_t add8(uint8_t lhs, uint8_t rhs, bool carry);
    uint8_t sub8(uint8_t lhs, uint8_t rhs, bool carry);
    void cp8(uint8_t lhs, uint8_t rhs);
    uint16_t add16(uint16_t lhs, uint16_t rhs);
    uint16_t adc16(uint16_t lhs, uint16_t rhs, bool subtract);
    void alu(int operation, uint8_t value);
    void daa();

    Z80Bus& bus_;
    uint8_t a_ = 0, f_ = 0, b_ = 0, c_ = 0, d_ = 0, e_ = 0, h_ = 0, l_ = 0;
    uint8_t a2_ = 0, f2_ = 0, b2_ = 0, c2_ = 0, d2_ = 0, e2_ = 0, h2_ = 0, l2_ = 0;
    uint16_t ix_ = 0, iy_ = 0, sp_ = 0xffff, pc_ = 0;
    uint8_t i_ = 0, r_ = 0;
    bool iff1_ = false, iff2_ = false, halted_ = false;
    uint8_t im_ = 0;
};

} // namespace tinyksp
