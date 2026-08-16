#include "ksp_runtime.h"
#include "yamaha_chips.h"

#include <iostream>
#include <string>
#include <vector>

static int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

int main(int argc, char** argv) {
    if (argc != 3) return fail("usage: ksp105_smoke SHARED NONMONOTONIC");
    std::string error;

    tinyksp::KspPackage shared;
    if (!shared.load(argv[1], error)) return fail("shared KSP 1.05 load: " + error);
    if (shared.minorVersion() != 5 || shared.resourceCount() != 31)
        return fail("shared KSP 1.05 dimensions");
    std::vector<uint8_t> first, last, r1, r2;
    if (!shared.materializeResource(0, first, error) ||
        !shared.materializeResource(28, last, error) ||
        !shared.materializeResource(29, r1, error) ||
        !shared.materializeResource(30, r2, error))
        return fail("shared resource materialization: " + error);
    if (first.size() != 151 || last.size() != 151 ||
        std::string(first.begin(), first.begin() + 5) != std::string("MBMS\x10", 5) ||
        std::string(last.begin(), last.begin() + 5) != std::string("MBMS\x10", 5) ||
        first == last || std::string(r1.begin(), r1.end()) != "RAW-ALIAS" || r1 != r2)
        return fail("shared resource decoded bytes");
    tinyksp::Opl4Device opl4;
    opl4.reset(44100);
    if (!opl4.loadMwk(first, error) || opl4.customSampleCount() != 1)
        return fail("first shared MWK decode: " + error);
    opl4.reset(44100);
    if (!opl4.loadMwk(last, error) || opl4.customSampleCount() != 1)
        return fail("last shared MWK decode: " + error);

    tinyksp::KspPackage nonmonotonic;
    if (!nonmonotonic.load(argv[2], error))
        return fail("non-monotonic KSP 1.05 load: " + error);
    std::vector<uint8_t> logical;
    if (!nonmonotonic.materializeResource(0, logical, error))
        return fail("non-monotonic resource materialization: " + error);
    if (std::string(logical.begin(), logical.end()) != "SECONDFIRST-")
        return fail("KZB1 descriptor logical order was not preserved");

    std::cout << "KSP 1.05 shared payload view smoke test passed\n";
    return 0;
}
