#include "ksp_runtime.h"
#include <iostream>
#include <string>
#include <vector>

static int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

int main(int argc, char** argv) {
    if (argc != 2) return fail("usage: runtime_smoke fixture.ksp");
    tinyksp::KspPackage package;
    std::string error;
    if (!package.load(argv[1], error)) return fail("load: " + error);
    if (package.visibleTrackCount() != 3) return fail("visible track count");
    if (package.visibleTrackTitle(0) != "Sparse track") return fail("track title");
    const auto metadata = package.generalMetadata();
    if (metadata.size() != 11) return fail("general metadata count");
    bool saw_game = false, saw_custom = false, saw_track_key = false;
    for (const auto& entry : metadata) {
        if (entry.key == "game" && entry.value == "Fixture Game") saw_game = true;
        if (entry.key == "custom.field" && entry.value == "custom value") saw_custom = true;
        if (entry.key.rfind("track.", 0) == 0) saw_track_key = true;
    }
    if (!saw_game || !saw_custom || saw_track_key) return fail("general metadata values/filter");
    if (package.engineSummaries().empty() || package.engineSummaries()[0].find("Test engine") == std::string::npos)
        return fail("engine summary");

    uint16_t implementation = 0xffff;
    if (!package.resolveTrack(package.logicalTrackAt(0), tinyksp::supportedHardwareMask(), implementation, error))
        return fail("resolve: " + error);
    if (implementation != package.logicalTrackAt(0)) return fail("HVR1 fallback selection");
    std::vector<uint8_t> page;
    if (!package.materializeTrackPage(implementation, page, error)) return fail("sparse: " + error);
    if (page.size() != 64 || page[10] != 'a' || page[11] != 'b' || page[12] != 'c')
        return fail("visible fallback reconstruction");
    if (!package.materializeTrackPage(3, page, error)) return fail("PBLK: " + error);
    if (page[30] != 'X' || page[31] != 'Y' || page[32] != 'Z')
        return fail("PBLK reconstruction");

    if (!package.materializeTrackPage(package.logicalTrackAt(1), page, error)) return fail("complete: " + error);
    if (page[7] != 21) return fail("complete page reconstruction");

    if (!package.materializeTrackPage(package.logicalTrackAt(2), page, error)) return fail("RMP1: " + error);
    if (page[20] != '2' || page[23] != '5') return fail("RMP1 reconstruction");

    std::cout << "KSP parser/materializer/metadata/HVR1 smoke test passed\n";
    return 0;
}
