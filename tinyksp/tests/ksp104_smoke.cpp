#include "ksp_runtime.h"

#include <iostream>
#include <string>

static int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

static const std::string* meta(const tinyksp::KspPackage& package, const std::string& key) {
    for (const auto& entry : package.metadata()) if (entry.key == key) return &entry.value;
    return nullptr;
}

int main(int argc, char** argv) {
    if (argc != 5)
        return fail("usage: ksp104_smoke VALID LOCALIZED NOMETA STRICT103");
    std::string error;

    tinyksp::KspPackage valid;
    if (!valid.load(argv[1], error)) return fail("valid 1.04 load: " + error);
    if (valid.minorVersion() != 4 || valid.visibleTrackCount() != 51 ||
        valid.trackCount() != 153 || !valid.hasHardwareVariants())
        return fail("1.04 package/HVR dimensions");
    const std::string* version = meta(valid, "metadata_version");
    const std::string* language = meta(valid, "default_language");
    if (!version || *version != "2" || !language || *language != "en")
        return fail("1.04 metadata grammar/default language");

    tinyksp::KspPackage localized;
    if (!localized.load(argv[2], error)) return fail("localized 1.04 load: " + error);
    const std::string* japanese = meta(localized, "title.ja");
    const std::string* brazilian = meta(localized, "title.pt-br");
    const std::string* traditional = meta(localized, "title.zh-hant");
    const std::string* future = meta(localized, "future_label.ja");
    if (!japanese || japanese->find("パロディウス") == std::string::npos ||
        !brazilian || *brazilian != "Parodius Da!" ||
        !traditional || traditional->empty() || !future || future->empty())
        return fail("localized values not retained");

    tinyksp::KspPackage no_meta;
    if (!no_meta.load(argv[3], error) || no_meta.minorVersion() != 4)
        return fail("strict 1.04 without META must remain loadable: " + error);

    tinyksp::KspPackage strict103;
    if (!strict103.load(argv[4], error) || strict103.minorVersion() != 3)
        return fail("strict 1.03 compatibility: " + error);
    version = meta(strict103, "metadata_version");
    if (!version || *version != "1") return fail("1.03 metadata_version=1 compatibility");

    std::cout << "KSP 1.04 localized META conformance smoke test passed\n";
    return 0;
}
