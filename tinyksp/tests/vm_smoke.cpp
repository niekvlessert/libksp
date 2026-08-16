#include "ksp_vm.h"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

static bool silent(const std::vector<int16_t>& pcm) {
    const auto [lo, hi] = std::minmax_element(pcm.begin(), pcm.end());
    return *lo == 0 && *hi == 0;
}

int main(int argc, char** argv) {
    if (argc != 6) {
        std::cerr << "usage: vm_smoke NORMAL.ksp PLUS.ksp DUAL.ksp Y8950.ksp ADAPTIVE.ksp\n";
        return 2;
    }
    for (int file = 1; file <= 4; ++file) {
        tinyksp::KspVm vm(44100);
        std::string error;
        if (!vm.open(argv[file], error)) { std::cerr << error << "\n"; return 1; }
        if (vm.visibleTrackCount() != 1) return 3;
        if (vm.playbackVariantCount(0) != 1) return 4;
        if (!vm.start(0, error)) { std::cerr << error << "\n"; return 5; }
        std::vector<int16_t> pcm(44100 * 2);
        if (!vm.render(pcm.data(), 44100, error)) { std::cerr << error << "\n"; return 6; }
        if (silent(pcm)) { std::cerr << "silent render for " << argv[file] << "\n"; return 7; }
        const uint64_t expected = file == 4 ? 70 : 60;
        if (vm.playCalls() + 1 < expected || vm.playCalls() > expected + 1) {
            std::cerr << "unexpected PLAY count " << vm.playCalls() << "\n"; return 8;
        }
        if (vm.dynamicSwitches() != 1) {
            std::cerr << "dynamic switch count " << vm.dynamicSwitches() << "\n"; return 9;
        }
        if (file == 4 && (vm.y8950Writes() < 20 || vm.channelCount() != 9)) {
            std::cerr << "Y8950 path/channel map incomplete\n";
            return 10;
        }
        if (file == 1 && (vm.sccAWrites() < 30 || vm.channelCount() != 8)) {
            std::cerr << "single-SCC fallback path/channel map incomplete\n";
            return 11;
        }
        if (file == 3 && (vm.sccAWrites() < 30 || vm.sccBWrites() < 30 || vm.channelCount() != 13)) {
            std::cerr << "dual-SCC write path/channel map incomplete\n";
            return 12;
        }
    }

    // Adaptive fixture: strict HVR1 chooses hidden dual-SCC rank 300 over the
    // visible single-SCC fallback rank 100.
    tinyksp::KspVm adaptive(44100);
    std::string error;
    if (!adaptive.open(argv[5], error)) { std::cerr << error << "\n"; return 13; }
    if (adaptive.visibleTrackCount() != 1 || adaptive.playbackVariantCount(0) != 2) {
        std::cerr << "adaptive variant discovery failed\n";
        return 14;
    }
    if (adaptive.playbackVariantName(0, 0).find("Dual SCC") == std::string::npos ||
        adaptive.playbackVariantName(0, 1).find("SCC") == std::string::npos) {
        std::cerr << "adaptive variant labels incorrect\n";
        return 15;
    }
    if (adaptive.suggestedSeconds(0, 0) != 5) return 16;
    if (!adaptive.start(0, 0, error)) { std::cerr << error << "\n"; return 16; }
    if (adaptive.channelCount() != 13 || adaptive.channelName(0) != "SCC-A 1" ||
        adaptive.channelName(9) != "SCC-B 5" || adaptive.channelName(10) != "PSG A") {
        std::cerr << "dual-SCC number-key channel ordering incorrect\n";
        return 17;
    }
    for (int i = 0; i < adaptive.channelCount(); ++i) {
        bool now_muted = false;
        if (!adaptive.toggleChannelMute(i, now_muted) || !now_muted) return 18;
    }
    std::vector<int16_t> muted_pcm(4410 * 2);
    if (!adaptive.render(muted_pcm.data(), 4410, error)) { std::cerr << error << "\n"; return 19; }
    if (!silent(muted_pcm)) {
        std::cerr << "muting all active channels did not silence PCM\n";
        return 20;
    }
    adaptive.unmuteAllChannels();
    std::vector<int16_t> audible_pcm(4410 * 2);
    if (!adaptive.render(audible_pcm.data(), 4410, error)) { std::cerr << error << "\n"; return 21; }
    if (silent(audible_pcm)) {
        std::cerr << "unmuting channels did not restore PCM\n";
        return 22;
    }

    std::cout << "standalone VM variants/channel-muting/PSG/SCC/SCC+/dual-SCC/Y8950 test passed\n";
    return 0;
}
