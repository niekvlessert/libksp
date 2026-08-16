#include "kss_vm.h"

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

static void put16(std::vector<uint8_t>& b, size_t o, uint16_t v) {
    b[o] = static_cast<uint8_t>(v); b[o + 1] = static_cast<uint8_t>(v >> 8);
}

int main() {
    namespace fs = std::filesystem;
    const std::vector<uint8_t> code = {
        0x3e,0x00,0xd3,0xa0, 0x3e,0x40,0xd3,0xa1,
        0x3e,0x01,0xd3,0xa0, 0x3e,0x01,0xd3,0xa1,
        0x3e,0x07,0xd3,0xa0, 0x3e,0x3e,0xd3,0xa1,
        0x3e,0x08,0xd3,0xa0, 0x3e,0x0f,0xd3,0xa1,
        0xc9,
        0x3e,0x08,0xd3,0xa0, 0x3e,0x0f,0xd3,0xa1,0xc9
    };
    std::vector<uint8_t> kss(32 + code.size(), 0);
    kss[0]='K'; kss[1]='S'; kss[2]='S'; kss[3]='X';
    put16(kss, 4, 0x4000); put16(kss, 6, static_cast<uint16_t>(code.size()));
    put16(kss, 8, 0x4000); put16(kss, 10, 0x4021);
    kss[14] = 0x10; // KSSX extra header
    put16(kss, 24, 0); put16(kss, 26, 0);
    std::copy(code.begin(), code.end(), kss.begin() + 32);

    const fs::path path = fs::temp_directory_path() / "tinyksp_kss_vm_smoke.kss";
    { std::ofstream out(path, std::ios::binary); out.write(reinterpret_cast<const char*>(kss.data()), static_cast<std::streamsize>(kss.size())); }

    tinyksp::KssVm vm(44100);
    std::string error;
    vm.enableTrace(true);
    if (!vm.open(path.string(), error) || !vm.start(0, error)) {
        std::cerr << error << "\n"; fs::remove(path); return 1;
    }
    std::vector<int16_t> pcm(44100 * 2);
    if (!vm.render(pcm.data(), 44100, error)) {
        std::cerr << error << "\n"; fs::remove(path); return 2;
    }
    fs::remove(path);
    if (vm.playCalls() != 59) { std::cerr << "PLAY count=" << vm.playCalls() << "\n"; return 3; }
    if (vm.trace().size() != 63) { std::cerr << "trace count=" << vm.trace().size() << "\n"; return 4; }
    const auto [lo, hi] = std::minmax_element(pcm.begin(), pcm.end());
    if (*lo == 0 && *hi == 0) { std::cerr << "KSS render is silent\n"; return 5; }
    std::cout << "KSS/KSSX direct VM smoke test passed\n";
    return 0;
}
