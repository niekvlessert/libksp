#include "ksp_runtime.h"
#include "ksp_vm.h"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

static int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

int main(int argc, char** argv) {
    if (argc != 7)
        return fail("usage: ksp103_smoke VALID EQUAL NOELIGIBLE HIGHINDEX WARNING NOMETA");
    std::string error;
    tinyksp::KspPackage package;
    if (!package.load(argv[1], error)) return fail("valid load: " + error);
    if (package.minorVersion() != 3 || package.visibleTrackCount() != 51 ||
        package.trackCount() != 153 || !package.hasHardwareVariants())
        return fail("Shovel Knight 51/153 profile dimensions");
    if (!package.metadataWarnings().empty()) return fail("unexpected metadata warning");
    const auto variants = package.playbackVariants(0, tinyksp::supportedHardwareMask());
    if (variants.size() != 3 || variants[0].quality_rank != 300 ||
        variants[1].quality_rank != 200 || variants[2].quality_rank != 100)
        return fail("HVR1 rank ordering");
    if (variants[0].label.find("Dual SCC") == std::string::npos ||
        variants[1].label.find("SCC+") == std::string::npos ||
        variants[2].label.find("SCC") == std::string::npos)
        return fail("HVR1 hardware labels");
    uint16_t selected = 0xffff;
    if (!package.resolveTrack(0, tinyksp::supportedHardwareMask(), selected, error) || selected != 102)
        return fail("highest-rank automatic selection: " + error);
    const tinyksp::Track dual = package.effectiveTrack(0, selected);
    const tinyksp::Track plus = package.effectiveTrack(0, 51);
    if (dual.duration_ms != 5000 || dual.loop_start_ms != 1000 || dual.fade_ms != 750)
        return fail("implementation timing override/fallback");
    if (plus.duration_ms != 3000 || plus.loop_start_ms != 1000 || plus.fade_ms != 500)
        return fail("field-by-field logical timing inheritance");

    tinyksp::KspVm vm(44100);
    if (!vm.open(argv[1], error)) return fail("VM valid open: " + error);
    if (!vm.startPhysical(102, error)) return fail("direct hidden implementation start: " + error);
    std::vector<int16_t> pcm(4410 * 2);
    if (!vm.render(pcm.data(), 4410, error)) return fail("direct hidden render: " + error);
    if (std::all_of(pcm.begin(), pcm.end(), [](int16_t v) { return v == 0; }))
        return fail("direct hidden implementation rendered silence");

    tinyksp::KspPackage equal;
    if (!equal.load(argv[2], error)) return fail("equal rank load: " + error);
    if (!equal.resolveTrack(0, tinyksp::supportedHardwareMask(), selected, error) || selected != 51)
        return fail("equal rank did not use candidate-table order");

    tinyksp::KspPackage unavailable;
    if (!unavailable.load(argv[3], error)) return fail("no-eligible load: " + error);
    if (unavailable.resolveTrack(0, tinyksp::supportedHardwareMask(), selected, error))
        return fail("no-eligible HVR1 candidate unexpectedly resolved");

    tinyksp::KspPackage high;
    if (!high.load(argv[4], error)) return fail("high-index load: " + error);
    if (high.trackCount() != 260 ||
        !high.resolveTrack(0, tinyksp::supportedHardwareMask(), selected, error) || selected != 259)
        return fail("HVR1 implementation index above 255");

    tinyksp::KspPackage warning;
    if (!warning.load(argv[5], error)) return fail("warning load: " + error);
    if (warning.metadataWarnings().empty()) return fail("track_count mismatch warning missing");

    tinyksp::KspPackage no_meta;
    if (!no_meta.load(argv[6], error) || no_meta.minorVersion() != 3)
        return fail("strict 1.03 without META must remain loadable: " + error);

    std::cout << "KSP 1.03 META/HVAR/HVR1 conformance smoke test passed\n";
    return 0;
}
