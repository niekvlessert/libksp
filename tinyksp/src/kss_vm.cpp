#include "kss_vm.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>
#include <limits>
#include <sstream>

namespace tinyksp {
namespace {
uint16_t le16(const std::vector<uint8_t>& data, size_t offset) {
    return static_cast<uint16_t>(data[offset] | (static_cast<uint16_t>(data[offset + 1]) << 8));
}

int16_t softCompress(int32_t sample) {
    constexpr int32_t threshold = 32768 * 8 / 10;
    if (sample < -threshold) sample = ((sample + threshold) >> 2) - threshold;
    else if (sample > threshold) sample = ((sample - threshold) >> 2) + threshold;
    if (sample < -32767) sample = -32767;
    else if (sample > 32767) sample = 32767;
    return static_cast<int16_t>(sample);
}
}

KssVm::KssVm(uint32_t sample_rate)
    : cpu_(*this), sample_rate_(sample_rate ? sample_rate : 44100) {
    initializeMachine();
}

void KssVm::close() {
    std::string ignored;
    stop(ignored);
    initial_data_.clear();
    bank_data_.clear();
    file_size_ = 0;
}

bool KssVm::open(const std::string& path, std::string& error) {
    close();
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        error = "cannot open KSS file";
        return false;
    }
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    file_size_ = data.size();
    if (data.size() < 16) {
        error = "KSS file is shorter than its 16-byte header";
        return false;
    }
    const bool kssx = data[0] == 'K' && data[1] == 'S' && data[2] == 'S' && data[3] == 'X';
    const bool kscc = data[0] == 'K' && data[1] == 'S' && data[2] == 'C' && data[3] == 'C';
    if (!kssx && !kscc) {
        error = "not a KSS/KSSX file (expected KSCC or KSSX magic)";
        return false;
    }

    load_address_ = le16(data, 4);
    load_length_ = le16(data, 6);
    init_address_ = le16(data, 8);
    play_address_ = le16(data, 10);
    bank_offset_ = data[12];
    const uint8_t bank_raw = data[13];
    bank_count_ = bank_raw & 0x7f;
    bank_8k_ = (bank_raw & 0x80) != 0;
    const uint8_t extra_size = kssx ? data[14] : 0;
    sound_flags_ = data[15];
    if (extra_size != 0 && extra_size != 0x10) {
        error = "unsupported KSSX extra header size 0x";
        std::ostringstream out; out << std::hex << static_cast<unsigned>(extra_size); error += out.str();
        return false;
    }
    if (sound_flags_ & 0x02) {
        error = "Sega-mode KSS is not supported by TinyKSP's MSX playback core";
        return false;
    }

    const size_t header_size = 16u + extra_size;
    if (header_size > data.size() || static_cast<size_t>(load_length_) > data.size() - header_size) {
        error = "truncated KSS initial image";
        return false;
    }
    if (static_cast<uint32_t>(load_address_) + static_cast<uint32_t>(load_length_) > 0x10000u) {
        error = "KSS initial image lies outside the Z80 address space";
        return false;
    }
    initial_data_.assign(data.begin() + static_cast<ptrdiff_t>(header_size),
                         data.begin() + static_cast<ptrdiff_t>(header_size + load_length_));

    const size_t bank_size = bank_8k_ ? 0x2000u : 0x4000u;
    const size_t declared_banks = static_cast<size_t>(bank_count_) * bank_size;
    const size_t bank_start = header_size + load_length_;
    bank_data_.assign(declared_banks, 0);
    if (bank_start < data.size()) {
        const size_t available = std::min(declared_banks, data.size() - bank_start);
        std::copy_n(data.begin() + static_cast<ptrdiff_t>(bank_start), available, bank_data_.begin());
    }

    if (extra_size >= 0x10) {
        first_song_ = le16(data, 24);
        last_song_ = le16(data, 26);
        has_song_range_ = last_song_ >= first_song_;
    } else {
        first_song_ = 0;
        last_song_ = 0xffff;
        has_song_range_ = false;
    }

    ram_mode_ = (sound_flags_ & 0x04) != 0;
    const uint8_t audio_mode = static_cast<uint8_t>((sound_flags_ >> 3) & 0x03);
    y8950_enabled_ = audio_mode == 1 || audio_mode == 3;
    dac8_enabled_ = audio_mode == 2;
    fmpac_enabled_ = (sound_flags_ & 0x01) != 0;
    pal_mode_ = (sound_flags_ & 0x40) != 0;
    return true;
}

void KssVm::initializeMachine() {
    // Match libkss VM_init_memory: RET-filled low memory, PSG helper jumps,
    // zeroed $4000-$FFFF, then the KSS initial image overlays its load range.
    memory_.fill(0xc9);
    memory_[0x0093] = 0xc3; memory_[0x0094] = 0x01; memory_[0x0095] = 0x00;
    memory_[0x0096] = 0xc3; memory_[0x0097] = 0x09; memory_[0x0098] = 0x00;
    const uint8_t psg_write_stub[] = {0xd3,0xa0,0xf5,0x7b,0xd3,0xa1,0xf1,0xc9};
    std::copy(std::begin(psg_write_stub), std::end(psg_write_stub), memory_.begin() + 0x0001);
    const uint8_t psg_read_stub[] = {0xd3,0xa0,0xdb,0xa2,0xc9};
    std::copy(std::begin(psg_read_stub), std::end(psg_read_stub), memory_.begin() + 0x0009);
    std::fill(memory_.begin() + 0x4000, memory_.end(), 0);
    if (!initial_data_.empty())
        std::copy(initial_data_.begin(), initial_data_.end(), memory_.begin() + load_address_);

    cpu_.reset();
    cpu_.setSP(0xf380);
    psg_.reset(sample_rate_);
    scc_.reset(sample_rate_, true);
    scc_.writeAddress(0x9000, 0x3f); // libkss VM_SCC_AUTO reset state
    y8950_.reset(sample_rate_);
    fmpac_.reset(sample_rate_);
    bank_page4_ = bank_page5_ = -1;
    invalid_bank_page4_ = invalid_bank_page5_ = false;
    psg_register_ = fmpac_register_ = y8950_register_ = 0;
    dac1_ = dac8_ = 0;
    dac_writes_ = 0;
    play_calls_ = 0;
    bank_switches_ = 0;
    trace_phase_ = TracePhase::Init;
    trace_tick_ = 0;
    trace_order_ = 0;
    if (trace_enabled_) trace_.clear();
}

bool KssVm::start(uint16_t song, std::string& error) {
    if (initial_data_.empty() && load_length_ != 0) {
        error = "no KSS file is open";
        return false;
    }
    if (has_song_range_ && (song < first_song_ || song > last_song_)) {
        std::ostringstream out;
        out << "KSS song " << song << " lies outside declared range "
            << first_song_ << ".." << last_song_;
        error = out.str();
        return false;
    }
    initializeMachine();
    cpu_.setA(static_cast<uint8_t>(song & 0xff));
    trace_phase_ = TracePhase::Init;
    trace_tick_ = 0;
    if (!callRoutine(init_address_, 30'000'000, error)) return false;

    const double tick_hz = pal_mode_ ? 50.0 : 60.0;
    samples_per_tick_ = static_cast<double>(sample_rate_) / tick_hz;
    samples_until_tick_ = samples_per_tick_;
    dc_filter_weight_ = 1.0 / ((1.0 / sample_rate_) / (1.0e-6 * 47000.0) + 1.0);
    dc_filter_in_[0] = dc_filter_in_[1] = 0.0;
    dc_filter_out_[0] = dc_filter_out_[1] = 0.0;
    started_ = true;
    return true;
}

bool KssVm::stop(std::string&) {
    started_ = false;
    return true;
}

bool KssVm::callRoutine(uint16_t address, uint64_t cycles, std::string& error) {
    if (address == 0) return true;
    return cpu_.call(address, cycles, error);
}

bool KssVm::runPlayTick(std::string& error) {
    trace_phase_ = TracePhase::Play;
    trace_tick_ = play_calls_ + 1;
    if (!callRoutine(play_address_, 5'000'000, error)) return false;
    ++play_calls_;
    return true;
}

void KssVm::record(TraceDevice device, uint16_t address, uint8_t value) {
    if (!trace_enabled_) return;
    trace_.push_back({trace_phase_, trace_tick_, trace_order_++, device, address, value});
}

bool KssVm::pageUsesBank(uint16_t address) const {
    if (address >= 0x8000 && address < 0xa000) return bank_page4_ >= 0 || invalid_bank_page4_;
    if (address >= 0xa000 && address < 0xc000) return bank_page5_ >= 0 || invalid_bank_page5_;
    return false;
}

uint8_t KssVm::bankRead(uint16_t address) const {
    const bool page4 = address < 0xa000;
    const int bank = page4 ? bank_page4_ : bank_page5_;
    const bool invalid = page4 ? invalid_bank_page4_ : invalid_bank_page5_;
    if (invalid || bank < 0) return 0;
    const size_t bank_size = bank_8k_ ? 0x2000u : 0x4000u;
    const int physical = bank - static_cast<int>(bank_offset_);
    if (physical < 0 || physical >= bank_count_) return 0;
    size_t within = 0;
    if (bank_8k_) within = address & 0x1fff;
    else within = address - 0x8000;
    const size_t offset = static_cast<size_t>(physical) * bank_size + within;
    return offset < bank_data_.size() ? bank_data_[offset] : 0;
}

bool KssVm::mainWritable(uint16_t address) const {
    if (!ram_mode_ && address >= 0x8000 && address < 0xc000) return false;
    return true;
}

uint8_t KssVm::memRead(uint16_t address) {
    return pageUsesBank(address) ? bankRead(address) : memory_[address];
}

void KssVm::memWrite(uint16_t address, uint8_t value) {
    // libkss dispatches SCC writes before mapper selection and ordinary memory writes.
    if (address == 0x9000 || address == 0xb000 || address == 0xbffe) {
        if (address == 0x9000 && value != 0) scc_.writeAddress(address, 0x3f);
        else scc_.writeAddress(address, value);
    } else if ((address >= 0x9800 && address <= 0x98ff) ||
               (address >= 0xb800 && address <= 0xb8ff)) {
        scc_.writeAddress(address, value);
        record(TraceDevice::Scc, address, value);
    }

    if (dac8_enabled_ && address >= 0x5000 && address <= 0x5fff) {
        dac8_ = static_cast<int32_t>(static_cast<int>(value) - 0x80) << 4;
        ++dac_writes_;
        record(TraceDevice::Dac8, address, value);
    }

    if (bank_8k_ && (address == 0x9000 || address == 0xb000)) {
        const bool valid = value >= bank_offset_ && value < static_cast<uint16_t>(bank_offset_) + bank_count_;
        if (address == 0x9000) {
            bank_page4_ = valid ? value : -1;
            invalid_bank_page4_ = !valid;
        } else {
            bank_page5_ = valid ? value : -1;
            invalid_bank_page5_ = !valid;
        }
        ++bank_switches_;
    }

    // Bank ROM and non-RAM-mode main page 2 are read-only in libkss.
    if (pageUsesBank(address) || !mainWritable(address)) return;
    memory_[address] = value;
}

uint8_t KssVm::ioRead(uint16_t port) {
    switch (port & 0xff) {
    case 0xa2: return psg_.read();
    case 0x7c: case 0xf0: return fmpac_.readStatus();
    case 0x7d: case 0xf1: return fmpac_.readData();
    case 0xc0: return y8950_.readStatus();
    case 0xc1: return y8950_.readData();
    default: return 0xff;
    }
}

void KssVm::ioWrite(uint16_t port, uint8_t value) {
    const uint8_t p = static_cast<uint8_t>(port & 0xff);
    switch (p) {
    case 0xa0:
        psg_register_ = value & 0x0f;
        psg_.select(value);
        break;
    case 0xa1:
        psg_.write(value);
        record(TraceDevice::Psg, psg_register_, value);
        break;
    case 0x7c: case 0xf0:
        if (fmpac_enabled_) {
            fmpac_register_ = value & 0x3f;
            fmpac_.select(value);
        }
        break;
    case 0x7d: case 0xf1:
        if (fmpac_enabled_) {
            fmpac_.write(value);
            record(TraceDevice::FmPac, fmpac_register_, value);
        }
        break;
    case 0xc0:
        if (y8950_enabled_) {
            y8950_register_ = value;
            y8950_.select(value);
        }
        break;
    case 0xc1:
        if (y8950_enabled_) {
            y8950_.write(value);
            record(TraceDevice::Y8950, y8950_register_, value);
        }
        break;
    case 0xaa:
        dac1_ >>= 1;
        if (value & 0x80) dac1_ += 2048;
        ++dac_writes_;
        record(TraceDevice::Dac1, 0xaa, value);
        break;
    case 0xab:
        dac1_ >>= 1;
        if (value & 0x01) dac1_ += 2048;
        ++dac_writes_;
        record(TraceDevice::Dac1, 0xab, value);
        break;
    case 0xfe:
        if (!bank_8k_) {
            const bool valid = value >= bank_offset_ && value < static_cast<uint16_t>(bank_offset_) + bank_count_;
            if (valid) {
                bank_page4_ = bank_page5_ = value;
            } else {
                // libkss restores the main slot's $8000-$BFFF bank on invalid selectors.
                bank_page4_ = bank_page5_ = -1;
            }
            invalid_bank_page4_ = invalid_bank_page5_ = false;
            ++bank_switches_;
        }
        break;
    default:
        break;
    }
}

bool KssVm::render(int16_t* output, uint32_t frames, std::string& error) {
    if (!started_) {
        error = "no KSS song is running";
        return false;
    }
    if (!output && frames) {
        error = "null audio output buffer";
        return false;
    }
    for (uint32_t frame = 0; frame < frames; ++frame) {
        while (samples_until_tick_ <= 0.0) {
            if (!runPlayTick(error)) return false;
            samples_until_tick_ += samples_per_tick_;
        }
        float mixed = psg_.sample() + scc_.sample();
        if (fmpac_enabled_) mixed += fmpac_.sample();
        if (y8950_enabled_) mixed += y8950_.sample();
        if (dac_writes_) mixed += static_cast<float>(dac1_ + dac8_) / 32768.0f;
        const int32_t input = static_cast<int32_t>(mixed * 32767.0f);
        for (int channel = 0; channel < 2; ++channel) {
            dc_filter_out_[channel] = dc_filter_weight_ *
                (dc_filter_out_[channel] + input - dc_filter_in_[channel]);
            dc_filter_in_[channel] = input;
            output[frame * 2 + channel] = softCompress(static_cast<int32_t>(dc_filter_out_[channel]));
        }
        samples_until_tick_ -= 1.0;
    }
    return true;
}

std::string KssVm::hardwareDescription() const {
    std::string out = "PSG + SCC(auto)";
    if (fmpac_enabled_) out += " + FM-PAC";
    if (y8950_enabled_) out += " + Y8950";
    if (dac8_enabled_) out += " + 8-bit DAC";
    return out;
}

int KssVm::channelCount() const {
    int count = 3 + 5;
    if (fmpac_enabled_) count += 9;
    if (y8950_enabled_) count += 9;
    return count;
}

std::string KssVm::channelName(int channel) const {
    if (channel < 0 || channel >= channelCount()) return "Invalid channel";
    if (channel < 3) return std::string("PSG ") + static_cast<char>('A' + channel);
    channel -= 3;
    if (channel < 5) return "SCC " + std::to_string(channel + 1);
    channel -= 5;
    if (fmpac_enabled_) {
        if (channel < 9) return "FM-PAC " + std::to_string(channel + 1);
        channel -= 9;
    }
    return "Y8950 FM " + std::to_string(channel + 1);
}

bool KssVm::channelMuted(int channel) const {
    if (channel < 0 || channel >= channelCount()) return false;
    if (channel < 3) return psg_.muted(channel);
    channel -= 3;
    if (channel < 5) return scc_.muted(channel);
    channel -= 5;
    if (fmpac_enabled_) {
        if (channel < 9) return fmpac_.muted(channel);
        channel -= 9;
    }
    return y8950_.muted(channel);
}

bool KssVm::toggleChannelMute(int channel, bool& now_muted) {
    if (channel < 0 || channel >= channelCount()) return false;
    now_muted = !channelMuted(channel);
    if (channel < 3) psg_.setMuted(channel, now_muted);
    else if ((channel -= 3) < 5) scc_.setMuted(channel, now_muted);
    else {
        channel -= 5;
        if (fmpac_enabled_ && channel < 9) fmpac_.setMuted(channel, now_muted);
        else {
            if (fmpac_enabled_) channel -= 9;
            y8950_.setMuted(channel, now_muted);
        }
    }
    return true;
}

void KssVm::unmuteAllChannels() {
    psg_.unmuteAll();
    scc_.unmuteAll();
    fmpac_.unmuteAll();
    y8950_.unmuteAll();
}

} // namespace tinyksp
