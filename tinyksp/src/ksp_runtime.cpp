#include "ksp_runtime.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <unordered_set>

namespace tinyksp {
namespace {

constexpr uint16_t NULL16 = 0xffff;
constexpr uint32_t NULL32 = 0xffffffffu;
constexpr uint8_t COMP_NONE = 0;
constexpr uint8_t COMP_ZX0 = 1;
constexpr uint8_t COMP_ZX0_BLOCKS = 2;
constexpr uint16_t PAGE_BASE_ZERO = 1;
constexpr uint16_t RES_REQUIRED = 1;
constexpr uint16_t RES_STREAMABLE = 2;
constexpr uint16_t RES_PAGE_SOURCE = 4;
constexpr uint16_t TRACK_HIDDEN = 1;
constexpr uint32_t ENGINE_BANKED_DATA = 1u << 1;
constexpr uint32_t ENGINE_MWK_REQUIRED = 1u << 2;
constexpr uint32_t HW_PSG = 1u << 0;
constexpr uint32_t HW_SCC = 1u << 1;
constexpr uint32_t HW_SCC_PLUS = 1u << 2;
constexpr uint32_t HW_DUAL_SCC = 1u << 3;
constexpr uint32_t HW_FMPAC = 1u << 4;
constexpr uint32_t HW_Y8950 = 1u << 5;
constexpr uint32_t HW_OPL4 = 1u << 6;
constexpr uint32_t HW_SN76489 = 1u << 7;
constexpr uint32_t HW_GG_STEREO = 1u << 8;

bool rangeOk(size_t total, uint64_t offset, uint64_t size) {
    return offset <= total && size <= static_cast<uint64_t>(total) - offset;
}

uint8_t rd8(const std::vector<uint8_t>& data, size_t off) {
    if (!rangeOk(data.size(), off, 1)) throw std::runtime_error("byte outside file");
    return data[off];
}

uint16_t rd16(const std::vector<uint8_t>& data, size_t off) {
    if (!rangeOk(data.size(), off, 2)) throw std::runtime_error("word outside file");
    return static_cast<uint16_t>(data[off] | (data[off + 1] << 8));
}

uint32_t rd32(const std::vector<uint8_t>& data, size_t off) {
    if (!rangeOk(data.size(), off, 4)) throw std::runtime_error("dword outside file");
    return static_cast<uint32_t>(data[off]) |
           (static_cast<uint32_t>(data[off + 1]) << 8) |
           (static_cast<uint32_t>(data[off + 2]) << 16) |
           (static_cast<uint32_t>(data[off + 3]) << 24);
}

uint16_t rd16p(const uint8_t* p) {
    return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

uint32_t rd32p(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

uint32_t crc32(const uint8_t* data, size_t size) {
    uint32_t value = 0xffffffffu;
    for (size_t i = 0; i < size; ++i) {
        value ^= data[i];
        for (int bit = 0; bit < 8; ++bit) {
            value = (value >> 1) ^ (0xedb88320u & (0u - (value & 1u)));
        }
    }
    return value ^ 0xffffffffu;
}

uint32_t crc32(const std::vector<uint8_t>& data) {
    return crc32(data.data(), data.size());
}

class Zx0Reader {
public:
    explicit Zx0Reader(const std::vector<uint8_t>& input) : input_(input) {}

    bool decode(size_t expected, std::vector<uint8_t>& out, std::string& error) {
        try {
            out.clear();
            out.reserve(expected);
            size_t offset = 1;
            literals(gamma(false), out, expected);
            while (true) {
                bool branch = bit();
                if (!branch) {
                    copy(offset, gamma(false), out, expected);
                    branch = bit();
                    if (!branch) {
                        literals(gamma(false), out, expected);
                        continue;
                    }
                }
                while (true) {
                    size_t msb = gamma(true);
                    if (msb == 256) {
                        if (out.size() != expected) throw std::runtime_error("ZX0 output size mismatch");
                        return true;
                    }
                    uint8_t lsb = byte();
                    if (msb > (std::numeric_limits<size_t>::max() / 128))
                        throw std::runtime_error("ZX0 offset overflow");
                    offset = msb * 128 - (lsb >> 1);
                    backtrack_ = true;
                    copy(offset, gamma(false) + 1, out, expected);
                    branch = bit();
                    if (!branch) {
                        literals(gamma(false), out, expected);
                        break;
                    }
                }
            }
        } catch (const std::exception& ex) {
            error = ex.what();
            return false;
        }
    }

private:
    uint8_t byte() {
        if (index_ >= input_.size()) throw std::runtime_error("truncated ZX0 stream");
        last_byte_ = input_[index_++];
        return last_byte_;
    }

    bool bit() {
        if (backtrack_) {
            backtrack_ = false;
            return (last_byte_ & 1) != 0;
        }
        if (mask_ == 0) {
            bits_ = byte();
            mask_ = 0x80;
        }
        bool result = (bits_ & mask_) != 0;
        mask_ >>= 1;
        return result;
    }

    size_t gamma(bool invert) {
        size_t value = 1;
        while (!bit()) {
            if (value > (std::numeric_limits<size_t>::max() >> 1))
                throw std::runtime_error("ZX0 gamma overflow");
            value = (value << 1) | (static_cast<size_t>(bit()) ^ static_cast<size_t>(invert));
        }
        return value;
    }

    void literals(size_t count, std::vector<uint8_t>& out, size_t expected) {
        if (count > expected - out.size()) throw std::runtime_error("ZX0 literal exceeds output");
        for (size_t i = 0; i < count; ++i) out.push_back(byte());
    }

    static void copy(size_t offset, size_t count, std::vector<uint8_t>& out, size_t expected) {
        if (offset == 0 || offset > out.size()) throw std::runtime_error("invalid ZX0 back-reference");
        if (count > expected - out.size()) throw std::runtime_error("ZX0 match exceeds output");
        for (size_t i = 0; i < count; ++i) out.push_back(out[out.size() - offset]);
    }

    const std::vector<uint8_t>& input_;
    size_t index_ = 0;
    uint8_t mask_ = 0;
    uint8_t bits_ = 0;
    uint8_t last_byte_ = 0;
    bool backtrack_ = false;
};

bool decodeObject(const std::vector<uint8_t>& packed, uint8_t compression,
                  size_t expected, std::vector<uint8_t>& out, std::string& error) {
    if (compression == COMP_NONE) {
        if (packed.size() != expected) {
            error = "uncompressed object size mismatch";
            return false;
        }
        out = packed;
        return true;
    }
    if (compression == COMP_ZX0) {
        return Zx0Reader(packed).decode(expected, out, error);
    }
    error = "unsupported object compression";
    return false;
}

std::vector<uint8_t> slice(const std::vector<uint8_t>& data, uint64_t off, uint64_t size) {
    if (!rangeOk(data.size(), off, size)) throw std::runtime_error("payload outside file");
    return std::vector<uint8_t>(data.begin() + static_cast<ptrdiff_t>(off),
                                data.begin() + static_cast<ptrdiff_t>(off + size));
}

bool allZero(const std::vector<uint8_t>& data, size_t off, size_t count) {
    if (!rangeOk(data.size(), off, count)) return false;
    for (size_t i = off; i < off + count; ++i) if (data[i] != 0) return false;
    return true;
}

bool isAsciiLowerKey(const std::string& key) {
    if (key.empty() || key[0] < 'a' || key[0] > 'z') return false;
    for (unsigned char c : key) {
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_') continue;
        return false;
    }
    return true;
}

bool isMetaLanguageTag(const std::string& tag) {
    size_t start = 0;
    size_t end = tag.find('-');
    const size_t primary_size = (end == std::string::npos ? tag.size() : end);
    if (primary_size < 2 || primary_size > 8) return false;
    for (size_t i = 0; i < primary_size; ++i) {
        const unsigned char c = static_cast<unsigned char>(tag[i]);
        if (c < 'a' || c > 'z') return false;
    }
    if (end == std::string::npos) return true;
    start = end + 1;
    while (start < tag.size()) {
        end = tag.find('-', start);
        const size_t size = (end == std::string::npos ? tag.size() : end) - start;
        if (size < 1 || size > 8) return false;
        for (size_t i = start; i < start + size; ++i) {
            const unsigned char c = static_cast<unsigned char>(tag[i]);
            const bool valid = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
            if (!valid) return false;
        }
        if (end == std::string::npos) return true;
        start = end + 1;
    }
    return false;
}

bool isLocalizedMetaKey(const std::string& key) {
    const size_t dot = key.find('.');
    if (dot == std::string::npos || dot == 0 || dot + 1 >= key.size()) return false;
    if (key.find('.', dot + 1) != std::string::npos) return false;
    return isAsciiLowerKey(key.substr(0, dot)) && isMetaLanguageTag(key.substr(dot + 1));
}

bool isAcceptedMetaKey(const std::string& key, bool allow_localized) {
    return isAsciiLowerKey(key) || (allow_localized && isLocalizedMetaKey(key));
}

bool isValidUtf8(const std::vector<uint8_t>& data) {
    size_t i = 0;
    while (i < data.size()) {
        const uint8_t c = data[i++];
        if (c <= 0x7f) continue;
        uint32_t code = 0;
        size_t need = 0;
        uint32_t minimum = 0;
        if (c >= 0xc2 && c <= 0xdf) {
            code = c & 0x1f; need = 1; minimum = 0x80;
        } else if (c >= 0xe0 && c <= 0xef) {
            code = c & 0x0f; need = 2; minimum = 0x800;
        } else if (c >= 0xf0 && c <= 0xf4) {
            code = c & 0x07; need = 3; minimum = 0x10000;
        } else {
            return false;
        }
        if (need > data.size() - i) return false;
        for (size_t n = 0; n < need; ++n) {
            const uint8_t tail = data[i++];
            if ((tail & 0xc0) != 0x80) return false;
            code = (code << 6) | (tail & 0x3f);
        }
        if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff))
            return false;
    }
    return true;
}

bool decimalValue(const std::string& value, uint64_t& parsed) {
    if (value.empty()) return false;
    uint64_t result = 0;
    for (unsigned char c : value) {
        if (c < '0' || c > '9') return false;
        const uint64_t digit = c - '0';
        if (result > (std::numeric_limits<uint64_t>::max() - digit) / 10) return false;
        result = result * 10 + digit;
    }
    parsed = result;
    return true;
}

bool lowerHexSha256(const std::string& value) {
    if (value.size() != 64) return false;
    for (unsigned char c : value)
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}

} // namespace

uint32_t supportedHardwareMask() {
    return HW_PSG | HW_SCC | HW_SCC_PLUS | HW_DUAL_SCC |
           HW_FMPAC | HW_Y8950 | HW_OPL4;
}

std::string hardwareDescription(uint32_t hardware) {
    std::vector<std::string> parts;
    if (hardware & HW_DUAL_SCC) parts.emplace_back("Dual SCC");
    else if (hardware & HW_SCC_PLUS) parts.emplace_back("SCC+");
    else if (hardware & HW_SCC) parts.emplace_back("SCC");
    if (hardware & HW_Y8950) parts.emplace_back("Philips Music Module (Y8950)");
    if (hardware & HW_FMPAC) parts.emplace_back("FM-PAC");
    if (hardware & HW_OPL4) parts.emplace_back("MoonSound/OPL4");
    if (hardware & HW_SN76489) parts.emplace_back("SN76489");
    if (hardware & HW_PSG) parts.emplace_back("PSG");
    if (parts.empty()) return "No declared sound hardware";
    std::string result;
    for (size_t i = 0; i < parts.size(); ++i) {
        if (i) result += " + ";
        result += parts[i];
    }
    return result;
}

void KspPackage::clear() {
    bytes_.clear();
    strings_.clear();
    engines_.clear();
    pages_.clear();
    tracks_.clear();
    resources_.clear();
    visible_tracks_.clear();
    metadata_.clear();
    metadata_warnings_.clear();
    hvr_logicals_.clear();
    hvr_candidates_.clear();
    hvr_record_by_track_.clear();
    resource_cache_.clear();
    pblk_cache_.clear();
    hpol_loaded_ = false;
    hpol_cache_ = HpolPool{};
    minor_version_ = 0;
    default_track_ = 0;
    meta_resource_ = NULL16;
    cover_resource_ = NULL16;
}

bool KspPackage::load(const std::string& path, std::string& error) {
    clear();
    try {
        std::ifstream input(path, std::ios::binary);
        if (!input) throw std::runtime_error("cannot open selected file");
        input.seekg(0, std::ios::end);
        std::streamoff length = input.tellg();
        if (length < 0 || length > 512ll * 1024ll * 1024ll)
            throw std::runtime_error("invalid or excessively large file");
        input.seekg(0, std::ios::beg);
        bytes_.resize(static_cast<size_t>(length));
        if (!bytes_.empty() && !input.read(reinterpret_cast<char*>(bytes_.data()), length))
            throw std::runtime_error("failed to read selected file");
        if (!parse(error)) {
            clear();
            return false;
        }
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        clear();
        return false;
    }
}

bool KspPackage::parse(std::string& error) {
    try {
        if (bytes_.size() < 80 || std::memcmp(bytes_.data(), "KSP1", 4) != 0)
            throw std::runtime_error("not a standalone KSP1 file");
        if (rd16(bytes_, 4) != 80) throw std::runtime_error("unsupported KSP header size");
        minor_version_ = rd16(bytes_, 6);
        if (minor_version_ > 5) throw std::runtime_error("unsupported future KSP version");
        if (rd32(bytes_, 8) != 0) throw std::runtime_error("unknown KSP file flags");
        if (rd32(bytes_, 12) != bytes_.size()) throw std::runtime_error("KSP file-size field mismatch");
        if (!allZero(bytes_, 72, 8)) throw std::runtime_error("nonzero reserved KSP header bytes");

        uint32_t stored_header_crc = rd32(bytes_, 64);
        if (stored_header_crc) {
            std::vector<uint8_t> header(bytes_.begin(), bytes_.begin() + 80);
            std::fill(header.begin() + 64, header.begin() + 68, 0);
            if (crc32(header) != stored_header_crc) throw std::runtime_error("KSP header CRC mismatch");
        }

        uint32_t engine_off = rd32(bytes_, 16);
        uint16_t engine_count = rd16(bytes_, 20);
        uint16_t engine_size = rd16(bytes_, 22);
        uint32_t page_off = rd32(bytes_, 24);
        uint16_t page_count = rd16(bytes_, 28);
        uint16_t page_size = rd16(bytes_, 30);
        uint32_t track_off = rd32(bytes_, 32);
        uint16_t track_count = rd16(bytes_, 36);
        uint16_t track_size = rd16(bytes_, 38);
        uint32_t resource_off = rd32(bytes_, 40);
        uint16_t resource_count = rd16(bytes_, 44);
        uint16_t resource_size = rd16(bytes_, 46);
        uint32_t string_off = rd32(bytes_, 48);
        uint32_t string_size = rd32(bytes_, 52);
        default_track_ = rd16(bytes_, 56);
        meta_resource_ = rd16(bytes_, 58);
        cover_resource_ = rd16(bytes_, 60);
        if (rd16(bytes_, 62) != 0) throw std::runtime_error("nonzero reserved KSP header word");

        if (engine_size < 64 || page_size < 24 || track_size < 32 || resource_size < 32)
            throw std::runtime_error("KSP table entry smaller than version-1 minimum");
        if (!rangeOk(bytes_.size(), engine_off, uint64_t(engine_count) * engine_size) ||
            !rangeOk(bytes_.size(), page_off, uint64_t(page_count) * page_size) ||
            !rangeOk(bytes_.size(), track_off, uint64_t(track_count) * track_size) ||
            !rangeOk(bytes_.size(), resource_off, uint64_t(resource_count) * resource_size) ||
            !rangeOk(bytes_.size(), string_off, string_size))
            throw std::runtime_error("KSP table outside file");
        strings_ = slice(bytes_, string_off, string_size);

        uint32_t stored_index_crc = rd32(bytes_, 68);
        if (stored_index_crc) {
            std::vector<uint8_t> index_bytes;
            auto append_range = [&](uint32_t off, uint64_t size) {
                index_bytes.insert(index_bytes.end(), bytes_.begin() + off,
                                   bytes_.begin() + static_cast<ptrdiff_t>(off + size));
            };
            append_range(engine_off, uint64_t(engine_count) * engine_size);
            append_range(page_off, uint64_t(page_count) * page_size);
            append_range(track_off, uint64_t(track_count) * track_size);
            append_range(resource_off, uint64_t(resource_count) * resource_size);
            append_range(string_off, string_size);
            if (crc32(index_bytes) != stored_index_crc)
                throw std::runtime_error("KSP index CRC mismatch");
        }

        engines_.reserve(engine_count);
        for (uint16_t i = 0; i < engine_count; ++i) {
            size_t o = engine_off + size_t(i) * engine_size;
            Engine e;
            e.flags = rd32(bytes_, o + 0);
            e.hardware = rd32(bytes_, o + 4);
            e.abi = rd16(bytes_, o + 8);
            e.tick_hz = rd16(bytes_, o + 10);
            e.load_address = rd16(bytes_, o + 12);
            e.page_size = rd16(bytes_, o + 14);
            e.init_address = rd16(bytes_, o + 16);
            e.play_address = rd16(bytes_, o + 18);
            e.stop_address = rd16(bytes_, o + 20);
            e.gateway = rd16(bytes_, o + 22);
            e.replace_start = rd16(bytes_, o + 24);
            e.first_page = rd16(bytes_, o + 26);
            e.page_count = rd16(bytes_, o + 28);
            e.default_mwk = rd16(bytes_, o + 30);
            e.template_compression = rd8(bytes_, o + 32);
            e.first_bank = rd8(bytes_, o + 33);
            e.bank_count = rd8(bytes_, o + 34);
            e.bank_width = rd8(bytes_, o + 35);
            uint32_t template_off = rd32(bytes_, o + 36);
            uint32_t template_packed = rd32(bytes_, o + 40);
            uint32_t template_raw = rd32(bytes_, o + 44);
            uint32_t template_crc = rd32(bytes_, o + 48);
            e.name_offset = rd32(bytes_, o + 52);
            if (!allZero(bytes_, o + 56, 8)) throw std::runtime_error("nonzero engine reserved bytes");
            if ((e.flags & ~0x1fu) != 0 || e.abi != 1 || e.page_size == 0 ||
                e.template_compression > COMP_ZX0 || template_raw != e.page_size)
                throw std::runtime_error("unsupported engine descriptor");
            if (uint32_t(e.first_page) + e.page_count > page_count)
                throw std::runtime_error("engine page range outside page table");
            std::vector<uint8_t> packed = slice(bytes_, template_off, template_packed);
            if (!decodeObject(packed, e.template_compression, template_raw, e.page_template, error))
                throw std::runtime_error("engine template: " + error);
            if (template_crc && crc32(e.page_template) != template_crc)
                throw std::runtime_error("engine template CRC mismatch");
            if (e.name_offset != NULL32 && e.name_offset >= strings_.size())
                throw std::runtime_error("engine name outside string table");
            engines_.push_back(std::move(e));
        }

        pages_.reserve(page_count);
        for (uint16_t i = 0; i < page_count; ++i) {
            size_t o = page_off + size_t(i) * page_size;
            Page p;
            p.engine = rd16(bytes_, o);
            p.encoding = rd8(bytes_, o + 2);
            p.compression = rd8(bytes_, o + 3);
            p.flags = rd16(bytes_, o + 4);
            uint16_t reserved = rd16(bytes_, o + 6);
            p.offset = rd32(bytes_, o + 8);
            p.packed_size = rd32(bytes_, o + 12);
            p.unpacked_size = rd32(bytes_, o + 16);
            p.final_crc = rd32(bytes_, o + 20);
            if (p.engine >= engines_.size() || p.encoding > 4 || p.compression > COMP_ZX0 || reserved)
                throw std::runtime_error("invalid page descriptor");
            if ((p.encoding == 0 || p.encoding == 1 || p.encoding == 4) && p.flags != 0)
                throw std::runtime_error("invalid page flags");
            if ((p.encoding == 2 || p.encoding == 3) && (p.flags & ~PAGE_BASE_ZERO))
                throw std::runtime_error("unknown page base flags");
            if (p.encoding == 4) {
                if (p.compression || p.offset || p.packed_size || p.unpacked_size)
                    throw std::runtime_error("hybrid page must not have a page payload");
            } else if (!rangeOk(bytes_.size(), p.offset, p.packed_size)) {
                throw std::runtime_error("page payload outside file");
            }
            const Engine& owner = engines_[p.engine];
            if (i < owner.first_page || i >= uint32_t(owner.first_page) + owner.page_count)
                throw std::runtime_error("page owner does not contain page index");
            pages_.push_back(p);
        }

        tracks_.reserve(track_count);
        for (uint16_t i = 0; i < track_count; ++i) {
            size_t o = track_off + size_t(i) * track_size;
            Track t;
            t.page = rd16(bytes_, o);
            t.song = rd16(bytes_, o + 2);
            t.flags = rd16(bytes_, o + 4);
            t.mwk = rd16(bytes_, o + 6);
            t.image = rd16(bytes_, o + 8);
            uint16_t reserved = rd16(bytes_, o + 10);
            t.title_offset = rd32(bytes_, o + 12);
            t.duration_ms = rd32(bytes_, o + 16);
            t.loop_start_ms = rd32(bytes_, o + 20);
            t.loop_end_ms = rd32(bytes_, o + 24);
            t.fade_ms = rd32(bytes_, o + 28);
            if (t.page >= pages_.size() || (t.flags & ~0x0fu) || reserved)
                throw std::runtime_error("invalid track descriptor");
            if (t.title_offset != NULL32 && t.title_offset >= strings_.size())
                throw std::runtime_error("track title outside string table");
            tracks_.push_back(t);
            if (!(t.flags & TRACK_HIDDEN)) visible_tracks_.push_back(i);
        }
        if (visible_tracks_.empty()) throw std::runtime_error("KSP has no visible tracks");
        if (default_track_ >= tracks_.size() || (tracks_[default_track_].flags & TRACK_HIDDEN))
            throw std::runtime_error("default public track is invalid or hidden");

        resources_.reserve(resource_count);
        for (uint16_t i = 0; i < resource_count; ++i) {
            size_t o = resource_off + size_t(i) * resource_size;
            Resource r;
            r.kind.assign(reinterpret_cast<const char*>(bytes_.data() + o), 4);
            r.flags = rd16(bytes_, o + 4);
            r.compression = rd8(bytes_, o + 6);
            uint8_t reserved = rd8(bytes_, o + 7);
            r.offset = rd32(bytes_, o + 8);
            r.packed_size = rd32(bytes_, o + 12);
            r.unpacked_size = rd32(bytes_, o + 16);
            r.crc = rd32(bytes_, o + 20);
            r.aux0 = rd32(bytes_, o + 24);
            r.aux1 = rd32(bytes_, o + 28);
            if ((r.flags & ~7u) || r.compression > COMP_ZX0_BLOCKS || reserved ||
                !rangeOk(bytes_.size(), r.offset, r.packed_size))
                throw std::runtime_error("invalid resource descriptor");
            resources_.push_back(std::move(r));
        }

        if (minor_version_ >= 5 && !validatePhysicalPayloadViews(error))
            throw std::runtime_error("resource payload views: " + error);

        if (!parseHardwareVariants(error))
            throw std::runtime_error("HVAR resource: " + error);

        if (meta_resource_ != NULL16) {
            if (meta_resource_ >= resources_.size() || resources_[meta_resource_].kind != "META")
                throw std::runtime_error("META header reference is not a META resource");
            std::vector<uint8_t> raw_meta;
            if (!logicalResource(meta_resource_, raw_meta, error))
                throw std::runtime_error("META resource: " + error);
            if (!parseMetadata(raw_meta, minor_version_, error))
                throw std::runtime_error("META resource: " + error);
        }
        if (cover_resource_ != NULL16) {
            if (cover_resource_ >= resources_.size() || resources_[cover_resource_].kind != "IMG5")
                throw std::runtime_error("cover header reference is not an IMG5 resource");
        }

        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}


bool KspPackage::parseMetadata(const std::vector<uint8_t>& raw, uint16_t container_minor,
                               std::string& error) {
    metadata_.clear();
    metadata_warnings_.clear();

    const bool strict = container_minor >= 3;
    const bool allow_localized = container_minor >= 4;
    const std::string spec_version = container_minor >= 5 ? "1.05" :
                                     (allow_localized ? "1.04" : "1.03");

    if (!strict) {
        size_t cursor = 0;
        if (raw.size() >= 3 && raw[0] == 0xef && raw[1] == 0xbb && raw[2] == 0xbf)
            cursor = 3;
        while (cursor <= raw.size()) {
            size_t end = cursor;
            while (end < raw.size() && raw[end] != '\n') ++end;
            size_t line_end = end;
            if (line_end > cursor && raw[line_end - 1] == '\r') --line_end;
            if (line_end > cursor) {
                auto equals = std::find(raw.begin() + static_cast<ptrdiff_t>(cursor),
                                        raw.begin() + static_cast<ptrdiff_t>(line_end),
                                        static_cast<uint8_t>('='));
                if (equals != raw.begin() + static_cast<ptrdiff_t>(line_end)) {
                    const size_t split = static_cast<size_t>(equals - raw.begin());
                    if (split > cursor) {
                        MetadataEntry entry;
                        entry.key.assign(reinterpret_cast<const char*>(raw.data() + cursor),
                                         split - cursor);
                        entry.value.assign(reinterpret_cast<const char*>(raw.data() + split + 1),
                                           line_end - split - 1);
                        metadata_.push_back(std::move(entry));
                    }
                }
            }
            if (end == raw.size()) break;
            cursor = end + 1;
        }
        return true;
    }

    if (raw.size() >= 3 && raw[0] == 0xef && raw[1] == 0xbb && raw[2] == 0xbf) {
        error = "UTF-8 BOM is forbidden in KSP " + spec_version + " META";
        return false;
    }
    if (!isValidUtf8(raw)) {
        error = "invalid UTF-8";
        return false;
    }
    for (uint8_t byte : raw) {
        if (byte == 0) { error = "embedded NUL in KSP " + spec_version + " META"; return false; }
        if (byte == '\r') { error = "CR/CRLF is forbidden in KSP " + spec_version + " META"; return false; }
    }

    std::unordered_set<std::string> keys;
    size_t cursor = 0;
    while (cursor <= raw.size()) {
        size_t end = cursor;
        while (end < raw.size() && raw[end] != '\n') ++end;
        if (end > cursor) {
            auto equals = std::find(raw.begin() + static_cast<ptrdiff_t>(cursor),
                                    raw.begin() + static_cast<ptrdiff_t>(end),
                                    static_cast<uint8_t>('='));
            if (equals == raw.begin() + static_cast<ptrdiff_t>(end)) {
                error = "META line is missing '='";
                return false;
            }
            const size_t split = static_cast<size_t>(equals - raw.begin());
            MetadataEntry entry;
            entry.key.assign(reinterpret_cast<const char*>(raw.data() + cursor), split - cursor);
            entry.value.assign(reinterpret_cast<const char*>(raw.data() + split + 1), end - split - 1);
            if (!isAcceptedMetaKey(entry.key, allow_localized)) {
                error = "invalid KSP " + spec_version + " META key: " + entry.key;
                return false;
            }
            if (!keys.insert(entry.key).second) {
                error = "duplicate KSP " + spec_version + " META key: " + entry.key;
                return false;
            }
            metadata_.push_back(std::move(entry));
        }
        if (end == raw.size()) break;
        cursor = end + 1;
    }

    const auto find_value = [&](const char* key) -> const std::string* {
        for (const auto& entry : metadata_) if (entry.key == key) return &entry.value;
        return nullptr;
    };
    const std::string expected_metadata_version = allow_localized ? "2" : "1";
    const std::string* version = find_value("metadata_version");
    if (!version || *version != expected_metadata_version) {
        error = "KSP " + spec_version + " META requires metadata_version=" +
                expected_metadata_version;
        return false;
    }
    if (allow_localized) {
        if (const std::string* language = find_value("default_language");
            language && !isMetaLanguageTag(*language)) {
            error = "default_language must be a lowercase KSP " + spec_version + " language tag";
            return false;
        }
    }
    if (const std::string* sha = find_value("source_sha256"); sha && !lowerHexSha256(*sha)) {
        error = "source_sha256 must be 64 lowercase hexadecimal digits";
        return false;
    }
    if (const std::string* year = find_value("release_year")) {
        uint64_t parsed = 0;
        if (year->size() != 4 || !decimalValue(*year, parsed)) {
            error = "release_year must be a four-digit decimal year";
            return false;
        }
    }
    if (const std::string* count = find_value("track_count")) {
        uint64_t parsed = 0;
        if (!decimalValue(*count, parsed)) {
            error = "track_count must be decimal";
            return false;
        }
        if (parsed != visible_tracks_.size()) {
            metadata_warnings_.push_back(
                "META track_count=" + *count + " differs from " +
                std::to_string(visible_tracks_.size()) + " visible logical tracks");
        }
    }
    return true;
}


bool KspPackage::validatePhysicalPayloadViews(std::string& error) const {
    struct SemanticRange {
        uint64_t start = 0;
        uint64_t end = 0;
        bool leaf = false;
        uint8_t compression = 0;
        uint32_t logical_size = 0;
        uint32_t logical_crc = 0;
        std::string control_signature;
        uint16_t resource = 0xffff;
    };

    auto overlaps = [](const SemanticRange& a, const SemanticRange& b) {
        return a.start < b.end && b.start < a.end;
    };
    auto exact = [](const SemanticRange& a, const SemanticRange& b) {
        return a.start == b.start && a.end == b.end;
    };

    std::vector<SemanticRange> ranges;
    for (uint16_t resource_index = 0; resource_index < resources_.size(); ++resource_index) {
        const Resource& r = resources_[resource_index];
        const uint64_t resource_start = r.offset;
        const uint64_t resource_end = resource_start + uint64_t(r.packed_size);
        if (resource_end < resource_start || resource_end > bytes_.size()) {
            error = "resource enclosing span outside file";
            return false;
        }

        if (r.compression == COMP_NONE || r.compression == COMP_ZX0) {
            ranges.push_back({resource_start, resource_end, true, r.compression,
                              r.unpacked_size, r.crc, {}, resource_index});
            continue;
        }
        if (r.compression != COMP_ZX0_BLOCKS) {
            error = "unsupported resource compression";
            return false;
        }
        if (r.packed_size < 16 ||
            std::memcmp(bytes_.data() + r.offset, "KZB1", 4) != 0 ||
            rd16(bytes_, r.offset + 4) != 16 ||
            rd32(bytes_, r.offset + 8) != r.unpacked_size) {
            error = "invalid KZB1 header";
            return false;
        }

        const uint16_t block_count = rd16(bytes_, r.offset + 6);
        const uint32_t table_rel = rd32(bytes_, r.offset + 12);
        const uint64_t table_size = uint64_t(block_count) * 16u;
        if (!rangeOk(r.packed_size, table_rel, table_size)) {
            error = "KZB1 table outside enclosing resource span";
            return false;
        }

        const uint64_t header_end = resource_start + 16;
        const uint64_t table_start = resource_start + table_rel;
        const uint64_t table_end = table_start + table_size;
        ranges.push_back({resource_start, header_end, false, 0, 0, 0,
                          "KZB1-header:" + std::to_string(block_count) + ":" +
                          std::to_string(table_rel) + ":" + std::to_string(r.unpacked_size),
                          resource_index});
        if (table_size != 0) {
            ranges.push_back({table_start, table_end, false, 0, 0, 0,
                              "KZB1-table:" + std::to_string(block_count) + ":" +
                              std::to_string(crc32(bytes_.data() + table_start,
                                                   static_cast<size_t>(table_size))),
                              resource_index});
        }

        uint64_t total_raw = 0;
        uint64_t minimum_end = std::max(header_end, table_end);
        uint64_t previous_read_end = 0;
        bool have_previous = false;
        for (uint16_t block = 0; block < block_count; ++block) {
            const uint64_t descriptor = table_start + uint64_t(block) * 16u;
            const uint32_t block_rel = rd32(bytes_, descriptor + 0);
            const uint32_t packed_size = rd32(bytes_, descriptor + 4);
            const uint32_t raw_size = rd32(bytes_, descriptor + 8);
            const uint32_t block_crc = rd32(bytes_, descriptor + 12);
            if (!rangeOk(r.packed_size, block_rel, packed_size)) {
                error = "KZB1 block outside enclosing resource span";
                return false;
            }
            const uint64_t block_start = resource_start + block_rel;
            const uint64_t block_end = block_start + uint64_t(packed_size);
            if (block_end < block_start || block_end > resource_end) {
                error = "KZB1 block range overflow";
                return false;
            }
            if ((r.flags & RES_STREAMABLE) && have_previous && block_start < previous_read_end) {
                error = "STREAMABLE KZB1 resource requires backward seeking";
                return false;
            }
            previous_read_end = block_end;
            have_previous = true;
            if (total_raw > std::numeric_limits<uint64_t>::max() - raw_size) {
                error = "KZB1 logical size overflow";
                return false;
            }
            total_raw += raw_size;
            minimum_end = std::max(minimum_end, block_end);
            ranges.push_back({block_start, block_end, true, COMP_ZX0,
                              raw_size, block_crc, {}, resource_index});
        }
        if (total_raw != r.unpacked_size) {
            error = "KZB1 descriptor logical sizes do not match resource size";
            return false;
        }
        if (minimum_end > resource_end) {
            error = "KZB1 minimum enclosing span exceeds packed_size";
            return false;
        }
    }

    for (size_t i = 0; i < ranges.size(); ++i) {
        for (size_t j = i + 1; j < ranges.size(); ++j) {
            const SemanticRange& a = ranges[i];
            const SemanticRange& b = ranges[j];
            if (!overlaps(a, b)) continue;
            if (a.leaf && b.leaf) {
                if (!exact(a, b)) {
                    error = "partially overlapping semantic leaf ranges";
                    return false;
                }
                if (a.compression != b.compression ||
                    a.logical_size != b.logical_size ||
                    a.logical_crc != b.logical_crc) {
                    error = "incompatible exact leaf aliases";
                    return false;
                }
                continue;
            }
            if (!a.leaf && !b.leaf) {
                if (!exact(a, b) || a.control_signature != b.control_signature) {
                    error = "incompatible or partially overlapping control ranges";
                    return false;
                }
                continue;
            }
            error = "control range overlaps a semantic leaf range";
            return false;
        }
    }
    return true;
}

bool KspPackage::parseHardwareVariants(std::string& error) {
    hvr_logicals_.clear();
    hvr_candidates_.clear();
    hvr_record_by_track_.assign(tracks_.size(), -1);

    uint16_t hvar_index = NULL16;
    for (uint16_t index = 0; index < resources_.size(); ++index) {
        if (resources_[index].kind != "HVAR") continue;
        if (hvar_index != NULL16) {
            error = "more than one package-wide HVAR resource";
            return false;
        }
        hvar_index = index;
    }
    if (hvar_index == NULL16) return true;
    const Resource& resource = resources_[hvar_index];
    if (resource.flags & (RES_REQUIRED | RES_PAGE_SOURCE)) {
        error = "HVAR must not use REQUIRED or PAGE_SOURCE flags";
        return false;
    }

    std::vector<uint8_t> raw;
    if (!logicalResource(hvar_index, raw, error)) return false;
    if (raw.size() < 24 || std::memcmp(raw.data(), "HVR1", 4) != 0) {
        error = "invalid HVR1 magic or truncated header";
        return false;
    }
    const uint16_t header_size = rd16p(raw.data() + 4);
    const uint16_t version = rd16p(raw.data() + 6);
    const uint16_t logical_count = rd16p(raw.data() + 8);
    const uint16_t candidate_count = rd16p(raw.data() + 10);
    const uint16_t logical_size = rd16p(raw.data() + 12);
    const uint16_t candidate_size = rd16p(raw.data() + 14);
    const uint32_t logical_offset = rd32p(raw.data() + 16);
    const uint32_t candidate_offset = rd32p(raw.data() + 20);
    if (header_size != 24 || version != 1 || logical_size != 12 || candidate_size != 8) {
        error = "unsupported HVR1 header or record dimensions";
        return false;
    }
    const uint64_t logical_bytes = uint64_t(logical_count) * logical_size;
    const uint64_t candidate_bytes = uint64_t(candidate_count) * candidate_size;
    if (logical_offset < header_size || candidate_offset < header_size ||
        !rangeOk(raw.size(), logical_offset, logical_bytes) ||
        !rangeOk(raw.size(), candidate_offset, candidate_bytes)) {
        error = "HVR1 table outside decoded resource";
        return false;
    }
    const uint64_t logical_end = uint64_t(logical_offset) + logical_bytes;
    const uint64_t candidate_end = uint64_t(candidate_offset) + candidate_bytes;
    if (logical_bytes && candidate_bytes &&
        uint64_t(logical_offset) < candidate_end && uint64_t(candidate_offset) < logical_end) {
        error = "HVR1 logical and candidate tables overlap";
        return false;
    }

    hvr_candidates_.reserve(candidate_count);
    for (uint16_t index = 0; index < candidate_count; ++index) {
        const uint8_t* record = raw.data() + candidate_offset + size_t(index) * candidate_size;
        HvrCandidate candidate;
        candidate.implementation_track = rd16p(record);
        candidate.quality_rank = rd16p(record + 2);
        const uint16_t flags = rd16p(record + 4);
        const uint16_t reserved = rd16p(record + 6);
        if (candidate.implementation_track >= tracks_.size() || flags || reserved) {
            error = "invalid HVR1 candidate record";
            return false;
        }
        hvr_candidates_.push_back(candidate);
    }

    std::vector<bool> candidate_used(candidate_count, false);
    hvr_logicals_.reserve(logical_count);
    for (uint16_t index = 0; index < logical_count; ++index) {
        const uint8_t* record = raw.data() + logical_offset + size_t(index) * logical_size;
        HvrLogical logical;
        logical.logical_track = rd16p(record);
        logical.first_candidate = rd16p(record + 2);
        logical.candidate_count = rd16p(record + 4);
        const uint16_t flags = rd16p(record + 6);
        const uint32_t reserved = rd32p(record + 8);
        if (logical.logical_track >= tracks_.size() ||
            (tracks_[logical.logical_track].flags & TRACK_HIDDEN) || flags || reserved ||
            !rangeOk(hvr_candidates_.size(), logical.first_candidate, logical.candidate_count)) {
            error = "invalid HVR1 logical record";
            return false;
        }
        if (hvr_record_by_track_[logical.logical_track] >= 0) {
            error = "duplicate HVR1 logical track";
            return false;
        }
        std::unordered_set<uint16_t> implementations;
        unsigned fallback_count = 0;
        for (uint16_t offset = 0; offset < logical.candidate_count; ++offset) {
            const size_t candidate_index = size_t(logical.first_candidate) + offset;
            if (candidate_used[candidate_index]) {
                error = "overlapping HVR1 candidate ranges";
                return false;
            }
            candidate_used[candidate_index] = true;
            const uint16_t implementation = hvr_candidates_[candidate_index].implementation_track;
            if (!implementations.insert(implementation).second) {
                error = "duplicate implementation in HVR1 candidate list";
                return false;
            }
            if (implementation == logical.logical_track) ++fallback_count;
        }
        if (fallback_count != 1) {
            error = "HVR1 logical fallback must occur exactly once";
            return false;
        }
        hvr_record_by_track_[logical.logical_track] = static_cast<int32_t>(hvr_logicals_.size());
        hvr_logicals_.push_back(logical);
    }
    return true;
}

std::vector<MetadataEntry> KspPackage::generalMetadata() const {
    std::vector<MetadataEntry> result;
    for (const auto& entry : metadata_) {
        std::string key_lower = entry.key;
        std::transform(key_lower.begin(), key_lower.end(), key_lower.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        if (key_lower.rfind("track.", 0) != 0) result.push_back(entry);
    }
    return result;
}

std::vector<std::string> KspPackage::engineSummaries() const {
    std::vector<std::string> result;
    result.reserve(engines_.size());
    for (size_t i = 0; i < engines_.size(); ++i) {
        const Engine& engine = engines_[i];
        std::string name = stringAt(engine.name_offset);
        if (name.empty()) name = "Engine " + std::to_string(i + 1);
        result.push_back(name + " | " + hardwareDescription(engine.hardware) +
                         " | " + std::to_string(engine.tick_hz) + " Hz" +
                         " | pages " + std::to_string(engine.page_count));
    }
    return result;
}

int KspPackage::visibleTrackCount() const { return static_cast<int>(visible_tracks_.size()); }

uint16_t KspPackage::logicalTrackAt(int visible_index) const {
    if (visible_index < 0 || static_cast<size_t>(visible_index) >= visible_tracks_.size()) return NULL16;
    return visible_tracks_[static_cast<size_t>(visible_index)];
}

std::string KspPackage::stringAt(uint32_t offset) const {
    if (offset == NULL32 || offset >= strings_.size()) return {};
    size_t end = offset;
    while (end < strings_.size() && strings_[end] != 0) ++end;
    if (end == strings_.size()) return {};
    return std::string(reinterpret_cast<const char*>(strings_.data() + offset), end - offset);
}

std::string KspPackage::visibleTrackTitle(int visible_index) const {
    uint16_t index = logicalTrackAt(visible_index);
    if (index == NULL16 || index >= tracks_.size()) return "Invalid track";
    std::string title = stringAt(tracks_[index].title_offset);
    if (title.empty()) title = "Track " + std::to_string(index + 1);
    return title;
}

std::vector<PlaybackVariant> KspPackage::playbackVariants(
        int visible_index, uint32_t available_hardware) const {
    std::vector<PlaybackVariant> variants;
    const uint16_t logical = logicalTrackAt(visible_index);
    if (logical == NULL16 || logical >= tracks_.size()) return variants;

    const int32_t record_index = logical < hvr_record_by_track_.size()
        ? hvr_record_by_track_[logical] : -1;
    if (record_index < 0) {
        if (candidateSupported(logical, available_hardware)) {
            const Engine* engine = engineForTrack(logical);
            variants.push_back({logical, engine ? engine->hardware : 0, 0,
                                engine ? hardwareDescription(engine->hardware) : "Unknown hardware",
                                true});
        }
        return variants;
    }

    const HvrLogical& record = hvr_logicals_[static_cast<size_t>(record_index)];
    for (uint16_t offset = 0; offset < record.candidate_count; ++offset) {
        const HvrCandidate& candidate =
            hvr_candidates_[size_t(record.first_candidate) + offset];
        if (!candidateSupported(candidate.implementation_track, available_hardware)) continue;
        const Engine* engine = engineForTrack(candidate.implementation_track);
        PlaybackVariant variant;
        variant.track_index = candidate.implementation_track;
        variant.hardware = engine ? engine->hardware : 0;
        variant.quality_rank = candidate.quality_rank;
        variant.label = engine ? hardwareDescription(engine->hardware) : "Unknown hardware";
        variant.visible_fallback = candidate.implementation_track == logical;
        variants.push_back(std::move(variant));
    }
    std::stable_sort(variants.begin(), variants.end(), [](const PlaybackVariant& a,
                                                          const PlaybackVariant& b) {
        return a.quality_rank > b.quality_rank;
    });
    return variants;
}

std::string KspPackage::playbackUnsupportedReason(
    int visible_index, uint32_t available_hardware) const {
    if (visible_index < 0 || visible_index >= static_cast<int>(visible_tracks_.size()))
        return "track index outside public track list";

    const uint16_t logical = visible_tracks_[static_cast<size_t>(visible_index)];
    std::vector<uint16_t> candidates;
    const int32_t record_index = logical < hvr_record_by_track_.size()
        ? hvr_record_by_track_[logical] : -1;
    if (record_index >= 0) {
        const HvrLogical& record = hvr_logicals_[static_cast<size_t>(record_index)];
        for (uint16_t i = 0; i < record.candidate_count; ++i)
            candidates.push_back(hvr_candidates_[size_t(record.first_candidate) + i].implementation_track);
    } else {
        candidates.push_back(logical);
    }

    std::vector<std::string> reasons;
    auto add = [&reasons](const std::string& reason) {
        if (std::find(reasons.begin(), reasons.end(), reason) == reasons.end())
            reasons.push_back(reason);
    };
    for (const uint16_t index : candidates) {
        const Track* t = track(index);
        const Engine* e = engineForTrack(index);
        if (!t || !e) { add("invalid track/page/engine reference"); continue; }
        const uint32_t missing = e->hardware & ~available_hardware;
        if (missing) { add("required hardware is not emulated"); continue; }
        if ((e->hardware & HW_DUAL_SCC) && (e->hardware & HW_SCC_PLUS)) {
            add("invalid combined dual-SCC and SCC+ engine mask"); continue;
        }
        if (e->hardware & (HW_SN76489 | HW_GG_STEREO)) {
            add("SN76489/Game Gear playback is not supported"); continue;
        }
        if (e->flags & ENGINE_BANKED_DATA) {
            add("banked engine data is not supported"); continue;
        }
        const uint16_t mwk = t->mwk != NULL16 ? t->mwk : e->default_mwk;
        if ((e->flags & ENGINE_MWK_REQUIRED) && mwk == NULL16) {
            add("MoonSound engine requires an MWK resource"); continue;
        }
        if (mwk != NULL16) {
            if (!(e->hardware & HW_OPL4)) {
                add("MWK is attached to a non-MoonSound engine"); continue;
            }
            if (mwk >= resources_.size()) {
                add("MWK resource index is outside the resource table"); continue;
            }
            if (resources_[mwk].kind != "MWK ") {
                add("MoonSound sample reference is " + resources_[mwk].kind + ", not MWK");
                continue;
            }
        }
        return {};
    }
    if (reasons.empty()) return "no eligible playback implementation";
    std::string result;
    for (size_t i = 0; i < reasons.size(); ++i) {
        if (i) result += "; ";
        result += reasons[i];
    }
    return result;
}

const Track* KspPackage::track(uint16_t index) const {
    return index < tracks_.size() ? &tracks_[index] : nullptr;
}

const Engine* KspPackage::engineForTrack(uint16_t index) const {
    const Track* t = track(index);
    if (!t || t->page >= pages_.size()) return nullptr;
    const Page& page = pages_[t->page];
    return page.engine < engines_.size() ? &engines_[page.engine] : nullptr;
}

bool KspPackage::candidateSupported(uint16_t track_index, uint32_t available_hardware) const {
    const Track* t = track(track_index);
    const Engine* e = engineForTrack(track_index);
    if (!t || !e) return false;
    if ((e->hardware & available_hardware) != e->hardware) return false;
    if ((e->hardware & HW_DUAL_SCC) && (e->hardware & HW_SCC_PLUS)) return false;
    if (e->hardware & (HW_SN76489 | HW_GG_STEREO)) return false;
    if (e->flags & ENGINE_BANKED_DATA) return false;
    const uint16_t mwk = t->mwk != NULL16 ? t->mwk : e->default_mwk;
    if (e->flags & ENGINE_MWK_REQUIRED) {
        if (!(e->hardware & HW_OPL4) || mwk == NULL16) return false;
    }
    if (mwk != NULL16) {
        if (!(e->hardware & HW_OPL4) || mwk >= resources_.size() ||
            resources_[mwk].kind != "MWK ") return false;
    }
    return true;
}

bool KspPackage::resolveTrack(uint16_t logical_track, uint32_t available_hardware,
                              uint16_t& implementation_track, std::string& error) const {
    if (logical_track >= tracks_.size() || (tracks_[logical_track].flags & TRACK_HIDDEN)) {
        error = "logical track index outside public track list";
        return false;
    }
    const int32_t record_index = logical_track < hvr_record_by_track_.size()
        ? hvr_record_by_track_[logical_track] : -1;
    if (record_index < 0) {
        return resolvePhysicalTrack(logical_track, available_hardware,
                                    implementation_track, error);
    }

    const HvrLogical& record = hvr_logicals_[static_cast<size_t>(record_index)];
    bool found = false;
    uint16_t best_rank = 0;
    uint16_t best_track = NULL16;
    for (uint16_t offset = 0; offset < record.candidate_count; ++offset) {
        const HvrCandidate& candidate =
            hvr_candidates_[size_t(record.first_candidate) + offset];
        if (!candidateSupported(candidate.implementation_track, available_hardware)) continue;
        if (!found || candidate.quality_rank > best_rank) {
            found = true;
            best_rank = candidate.quality_rank;
            best_track = candidate.implementation_track;
        }
    }
    if (!found) {
        error = "HVR1 logical track has no eligible implementation";
        return false;
    }
    implementation_track = best_track;
    return true;
}

bool KspPackage::resolveTrackVariant(int visible_index, int variant_index,
                                     uint32_t available_hardware,
                                     uint16_t& implementation_track,
                                     std::string& error) const {
    const auto variants = playbackVariants(visible_index, available_hardware);
    if (variants.empty()) {
        error = "track has no implementation supported by this player";
        return false;
    }
    if (variant_index < 0 || static_cast<size_t>(variant_index) >= variants.size()) {
        error = "playback type selection outside available HVR1 candidates";
        return false;
    }
    implementation_track = variants[static_cast<size_t>(variant_index)].track_index;
    return true;
}

bool KspPackage::resolvePhysicalTrack(uint16_t physical_track,
                                      uint32_t available_hardware,
                                      uint16_t& implementation_track,
                                      std::string& error) const {
    if (physical_track >= tracks_.size()) {
        error = "physical track index outside package";
        return false;
    }
    if (!candidateSupported(physical_track, available_hardware)) {
        error = "physical track needs unsupported hardware, banking or samples";
        return false;
    }
    implementation_track = physical_track;
    return true;
}

Track KspPackage::effectiveTrack(uint16_t logical_track,
                                 uint16_t implementation_track) const {
    if (logical_track >= tracks_.size() || implementation_track >= tracks_.size())
        return Track{};
    const Track& logical = tracks_[logical_track];
    const Track& implementation = tracks_[implementation_track];
    Track effective = implementation;
    effective.flags = logical.flags;
    effective.image = logical.image;
    effective.title_offset = logical.title_offset;
    if (effective.duration_ms == NULL32) effective.duration_ms = logical.duration_ms;
    if (effective.loop_start_ms == NULL32) effective.loop_start_ms = logical.loop_start_ms;
    if (effective.loop_end_ms == NULL32) effective.loop_end_ms = logical.loop_end_ms;
    if (effective.fade_ms == NULL32) effective.fade_ms = logical.fade_ms;
    return effective;
}

bool KspPackage::logicalResource(uint16_t index, std::vector<uint8_t>& output,
                                 std::string& error) const {
    auto cached = resource_cache_.find(index);
    if (cached != resource_cache_.end()) { output = cached->second; return true; }
    if (index >= resources_.size()) { error = "resource index outside table"; return false; }
    const Resource& r = resources_[index];
    try {
        std::vector<uint8_t> packed = slice(bytes_, r.offset, r.packed_size);
        if (r.compression == COMP_NONE || r.compression == COMP_ZX0) {
            if (!decodeObject(packed, r.compression, r.unpacked_size, output, error)) return false;
        } else if (r.compression == COMP_ZX0_BLOCKS) {
            if (packed.size() < 16 || std::memcmp(packed.data(), "KZB1", 4) != 0 ||
                rd16p(packed.data() + 4) != 16 || rd32p(packed.data() + 8) != r.unpacked_size) {
                error = "invalid KZB1 header";
                return false;
            }
            uint16_t block_count = rd16p(packed.data() + 6);
            uint32_t table_off = rd32p(packed.data() + 12);
            if (!rangeOk(packed.size(), table_off, uint64_t(block_count) * 16)) {
                error = "KZB1 table outside resource";
                return false;
            }
            output.clear();
            output.reserve(r.unpacked_size);
            for (uint16_t i = 0; i < block_count; ++i) {
                const uint8_t* d = packed.data() + table_off + size_t(i) * 16;
                uint32_t off = rd32p(d), size = rd32p(d + 4), raw_size = rd32p(d + 8), expected_crc = rd32p(d + 12);
                if (!rangeOk(packed.size(), off, size)) { error = "KZB1 block outside resource"; return false; }
                std::vector<uint8_t> block_packed(packed.begin() + off, packed.begin() + off + size);
                std::vector<uint8_t> block;
                if (!decodeObject(block_packed, COMP_ZX0, raw_size, block, error)) return false;
                if (expected_crc && crc32(block) != expected_crc) { error = "KZB1 block CRC mismatch"; return false; }
                output.insert(output.end(), block.begin(), block.end());
            }
            if (output.size() != r.unpacked_size) { error = "KZB1 total size mismatch"; return false; }
        } else {
            error = "unsupported resource compression";
            return false;
        }
        if (r.crc && crc32(output) != r.crc) { error = "resource CRC mismatch"; return false; }
        resource_cache_[index] = output;
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}

bool KspPackage::materializeResource(uint16_t resource_index,
                                     std::vector<uint8_t>& output,
                                     std::string& error) const {
    return logicalResource(resource_index, output, error);
}

std::string KspPackage::resourceKind(uint16_t resource_index) const {
    return resource_index < resources_.size() ? resources_[resource_index].kind : std::string();
}

bool KspPackage::pblkPool(uint16_t index, PblkPool& output, std::string& error) const {
    auto cached = pblk_cache_.find(index);
    if (cached != pblk_cache_.end()) { output = cached->second; return true; }
    if (index >= resources_.size()) { error = "PBLK resource outside table"; return false; }
    const Resource& r = resources_[index];
    if (r.kind != "PBLK" || r.compression != COMP_NONE || (r.flags & RES_PAGE_SOURCE)) {
        error = "page does not reference a valid PBLK resource";
        return false;
    }
    try {
        std::vector<uint8_t> raw = slice(bytes_, r.offset, r.packed_size);
        if (raw.size() < 32 || std::memcmp(raw.data(), "PBK1", 4) != 0) throw std::runtime_error("invalid PBK1 header");
        uint16_t header_size = rd16p(raw.data() + 4);
        uint16_t block_desc_size = rd16p(raw.data() + 6);
        uint16_t slab_desc_size = rd16p(raw.data() + 8);
        uint16_t block_size = rd16p(raw.data() + 10);
        uint32_t block_count = rd32p(raw.data() + 12);
        uint16_t slab_count = rd16p(raw.data() + 16);
        uint16_t flags = rd16p(raw.data() + 18);
        uint32_t block_table = rd32p(raw.data() + 20);
        uint32_t slab_table = rd32p(raw.data() + 24);
        uint32_t reserved = rd32p(raw.data() + 28);
        if (header_size != 32 || block_desc_size < 8 || slab_desc_size < 16 || !block_size || flags || reserved ||
            r.unpacked_size != uint64_t(block_count) * block_size ||
            !rangeOk(raw.size(), block_table, uint64_t(block_count) * block_desc_size) ||
            !rangeOk(raw.size(), slab_table, uint64_t(slab_count) * slab_desc_size))
            throw std::runtime_error("invalid PBK1 dimensions");
        std::vector<std::vector<uint8_t>> slabs;
        slabs.reserve(slab_count);
        for (uint16_t i = 0; i < slab_count; ++i) {
            const uint8_t* d = raw.data() + slab_table + size_t(i) * slab_desc_size;
            uint32_t off = rd32p(d), packed_size = rd32p(d + 4);
            uint16_t unpacked = rd16p(d + 8);
            uint8_t compression = d[10], slab_flags = d[11];
            uint32_t expected_crc = rd32p(d + 12);
            if (!unpacked || unpacked > 16384 || compression > COMP_ZX0 || slab_flags || !rangeOk(raw.size(), off, packed_size))
                throw std::runtime_error("invalid PBK1 slab");
            std::vector<uint8_t> packed(raw.begin() + off, raw.begin() + off + packed_size), slab;
            if (!decodeObject(packed, compression, unpacked, slab, error)) throw std::runtime_error(error);
            if (expected_crc && crc32(slab) != expected_crc) throw std::runtime_error("PBK1 slab CRC mismatch");
            slabs.push_back(std::move(slab));
        }
        PblkPool pool;
        pool.block_size = block_size;
        pool.blocks.reserve(block_count);
        std::vector<uint8_t> canonical;
        canonical.reserve(size_t(block_count) * block_size);
        for (uint32_t i = 0; i < block_count; ++i) {
            const uint8_t* d = raw.data() + block_table + size_t(i) * block_desc_size;
            uint16_t slab = rd16p(d), source = rd16p(d + 2);
            if (rd32p(d + 4) || slab >= slabs.size() || !rangeOk(slabs[slab].size(), source, block_size))
                throw std::runtime_error("invalid PBK1 block descriptor");
            std::vector<uint8_t> block(slabs[slab].begin() + source, slabs[slab].begin() + source + block_size);
            canonical.insert(canonical.end(), block.begin(), block.end());
            pool.blocks.push_back(std::move(block));
        }
        if (r.crc && crc32(canonical) != r.crc) throw std::runtime_error("PBLK logical CRC mismatch");
        pblk_cache_[index] = pool;
        output = std::move(pool);
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}

bool KspPackage::hpolPool(HpolPool& output, std::string& error) const {
    if (hpol_loaded_) { output = hpol_cache_; return true; }
    int found = -1;
    for (size_t i = 0; i < resources_.size(); ++i) {
        if (resources_[i].kind == "HPOL") {
            if (found >= 0) { error = "more than one HPOL resource"; return false; }
            found = static_cast<int>(i);
        }
    }
    if (found < 0) { error = "hybrid page without HPOL resource"; return false; }
    const Resource& r = resources_[static_cast<size_t>(found)];
    if (r.compression != COMP_NONE || (r.flags & (RES_REQUIRED | RES_PAGE_SOURCE)) != (RES_REQUIRED | RES_PAGE_SOURCE)) {
        error = "invalid HPOL resource flags";
        return false;
    }
    try {
        std::vector<uint8_t> raw = slice(bytes_, r.offset, r.packed_size);
        if (raw.size() < 96 || std::memcmp(raw.data(), "HPL1", 4) != 0 || rd16p(raw.data() + 4) != 96 || rd16p(raw.data() + 6) != 1)
            throw std::runtime_error("invalid HPL1 header");
        uint16_t block_size = rd16p(raw.data() + 8);
        uint16_t position_count = rd16p(raw.data() + 10);
        uint16_t page_count = rd16p(raw.data() + 12);
        uint16_t hot_count = rd16p(raw.data() + 14);
        uint16_t warm_count = rd16p(raw.data() + 16);
        uint16_t cold_count = rd16p(raw.data() + 18);
        uint16_t slab_count = rd16p(raw.data() + 20);
        if (!block_size || page_count != pages_.size() || (rd16p(raw.data() + 22) & ~1u))
            throw std::runtime_error("invalid HPL1 dimensions");
        uint32_t position_off = rd32p(raw.data() + 24);
        uint32_t map_off = rd32p(raw.data() + 28), map_packed = rd32p(raw.data() + 32), map_raw = rd32p(raw.data() + 36);
        uint32_t hot_off = rd32p(raw.data() + 40), hot_packed = rd32p(raw.data() + 44), hot_raw = rd32p(raw.data() + 48);
        uint32_t warm_off = rd32p(raw.data() + 52), warm_packed = rd32p(raw.data() + 56), warm_raw = rd32p(raw.data() + 60);
        uint32_t cold_table = rd32p(raw.data() + 64);
        uint32_t cold_data = rd32p(raw.data() + 68);
        uint32_t cold_packed_total = rd32p(raw.data() + 72), cold_raw = rd32p(raw.data() + 76);
        uint32_t hot_crc = rd32p(raw.data() + 80), warm_crc = rd32p(raw.data() + 84), cold_crc = rd32p(raw.data() + 88), map_crc = rd32p(raw.data() + 92);
        (void)cold_data;
        if (hot_raw != uint64_t(hot_count) * block_size || warm_raw != uint64_t(warm_count) * block_size ||
            cold_raw != uint64_t(cold_count) * block_size || map_raw != uint64_t(page_count) * position_count * 2 ||
            !rangeOk(raw.size(), position_off, uint64_t(position_count) * 2) ||
            !rangeOk(raw.size(), map_off, map_packed) || !rangeOk(raw.size(), hot_off, hot_packed) ||
            !rangeOk(raw.size(), warm_off, warm_packed) || !rangeOk(raw.size(), cold_table, uint64_t(slab_count) * 16))
            throw std::runtime_error("HPL1 range or size mismatch");
        HpolPool pool;
        pool.block_size = block_size;
        for (uint16_t i = 0; i < position_count; ++i) pool.positions.push_back(rd16p(raw.data() + position_off + size_t(i) * 2));
        for (size_t i = 1; i < pool.positions.size(); ++i)
            if (uint32_t(pool.positions[i - 1]) + block_size > pool.positions[i]) throw std::runtime_error("HPL1 positions overlap");
        std::vector<uint8_t> packed_map(raw.begin() + map_off, raw.begin() + map_off + map_packed), decoded_map;
        if (!decodeObject(packed_map, COMP_ZX0, map_raw, decoded_map, error)) throw std::runtime_error(error);
        if (map_crc && crc32(decoded_map) != map_crc) throw std::runtime_error("HPL1 map CRC mismatch");
        pool.matrix.reserve(decoded_map.size() / 2);
        for (size_t i = 0; i < decoded_map.size(); i += 2) pool.matrix.push_back(rd16p(decoded_map.data() + i));
        std::vector<uint8_t> all;
        auto decodeStream = [&](uint32_t off, uint32_t packed_size, uint32_t raw_size, uint32_t expected_crc) {
            if (!raw_size) return;
            std::vector<uint8_t> packed(raw.begin() + off, raw.begin() + off + packed_size), decoded;
            if (!decodeObject(packed, COMP_ZX0, raw_size, decoded, error)) throw std::runtime_error(error);
            if (expected_crc && crc32(decoded) != expected_crc) throw std::runtime_error("HPL1 tier CRC mismatch");
            all.insert(all.end(), decoded.begin(), decoded.end());
        };
        decodeStream(hot_off, hot_packed, hot_raw, hot_crc);
        decodeStream(warm_off, warm_packed, warm_raw, warm_crc);
        std::vector<uint8_t> cold;
        uint64_t packed_sum = 0;
        for (uint16_t i = 0; i < slab_count; ++i) {
            const uint8_t* d = raw.data() + cold_table + size_t(i) * 16;
            uint32_t off = rd32p(d), packed_size = rd32p(d + 4);
            uint16_t unpacked = rd16p(d + 8);
            uint8_t compression = d[10], flags = d[11];
            uint32_t expected_crc = rd32p(d + 12);
            if (!unpacked || unpacked > 16384 || unpacked % block_size || compression > COMP_ZX0 || flags || !rangeOk(raw.size(), off, packed_size))
                throw std::runtime_error("invalid HPL1 cold slab");
            std::vector<uint8_t> packed(raw.begin() + off, raw.begin() + off + packed_size), decoded;
            if (!decodeObject(packed, compression, unpacked, decoded, error)) throw std::runtime_error(error);
            if (expected_crc && crc32(decoded) != expected_crc) throw std::runtime_error("HPL1 cold slab CRC mismatch");
            packed_sum += packed_size;
            cold.insert(cold.end(), decoded.begin(), decoded.end());
        }
        if (cold.size() != cold_raw || packed_sum != cold_packed_total || (cold_crc && crc32(cold) != cold_crc))
            throw std::runtime_error("HPL1 cold totals mismatch");
        all.insert(all.end(), cold.begin(), cold.end());
        size_t total_blocks = size_t(hot_count) + warm_count + cold_count;
        if (all.size() != total_blocks * block_size) throw std::runtime_error("HPL1 block data size mismatch");
        for (size_t i = 0; i < total_blocks; ++i)
            pool.blocks.emplace_back(all.begin() + i * block_size, all.begin() + (i + 1) * block_size);
        for (uint16_t id : pool.matrix) if (id >= pool.blocks.size()) throw std::runtime_error("HPL1 map block outside pool");
        hpol_cache_ = pool;
        hpol_loaded_ = true;
        output = std::move(pool);
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}

bool KspPackage::materializeTrackPage(uint16_t implementation_track,
                                      std::vector<uint8_t>& page, std::string& error) const {
    if (implementation_track >= tracks_.size()) { error = "implementation track outside package"; return false; }
    return materializePage(tracks_[implementation_track].page, page, error);
}

bool KspPackage::materializeDynamicPage(uint16_t implementation_track, uint16_t local_page,
                                        std::vector<uint8_t>& page, std::string& error) const {
    const Engine* engine = engineForTrack(implementation_track);
    if (!engine) { error = "dynamic page track has no engine"; return false; }
    if (local_page >= engine->page_count) { error = "dynamic page index outside engine"; return false; }
    return materializePage(static_cast<uint16_t>(engine->first_page + local_page), page, error);
}

bool KspPackage::materializePage(uint16_t page_index, std::vector<uint8_t>& output,
                                 std::string& error) const {
    if (page_index >= pages_.size()) { error = "page outside package"; return false; }
    const Page& descriptor = pages_[page_index];
    const Engine& engine = engines_[descriptor.engine];
    try {
        if (descriptor.encoding == 4) {
            HpolPool pool;
            if (!hpolPool(pool, error)) return false;
            output = engine.page_template;
            size_t row = size_t(page_index) * pool.positions.size();
            if (!rangeOk(pool.matrix.size(), row, pool.positions.size())) throw std::runtime_error("HPL1 page row outside matrix");
            for (size_t i = 0; i < pool.positions.size(); ++i) {
                uint16_t pos = pool.positions[i], id = pool.matrix[row + i];
                if (!rangeOk(output.size(), pos, pool.block_size) || id >= pool.blocks.size()) throw std::runtime_error("invalid HPL1 page copy");
                std::copy(pool.blocks[id].begin(), pool.blocks[id].end(), output.begin() + pos);
            }
        } else {
            std::vector<uint8_t> packed = slice(bytes_, descriptor.offset, descriptor.packed_size), raw;
            if (!decodeObject(packed, descriptor.compression, descriptor.unpacked_size, raw, error)) return false;
            if (descriptor.encoding == 0) {
                output = engine.page_template;
                size_t cursor = 0, previous_end = 0;
                while (cursor < raw.size()) {
                    if (!rangeOk(raw.size(), cursor, 4)) throw std::runtime_error("truncated sparse page record");
                    uint16_t dest = rd16p(raw.data() + cursor), count = rd16p(raw.data() + cursor + 2);
                    cursor += 4;
                    if (!count || dest < previous_end || !rangeOk(output.size(), dest, count) || !rangeOk(raw.size(), cursor, count))
                        throw std::runtime_error("invalid sparse page record");
                    std::copy(raw.begin() + cursor, raw.begin() + cursor + count, output.begin() + dest);
                    cursor += count;
                    previous_end = size_t(dest) + count;
                }
            } else if (descriptor.encoding == 1) {
                if (raw.size() != engine.page_size) throw std::runtime_error("complete page size mismatch");
                output = std::move(raw);
            } else if (descriptor.encoding == 2) {
                output.assign(engine.page_size, 0);
                if (!(descriptor.flags & PAGE_BASE_ZERO)) output = engine.page_template;
                if (raw.size() < 16 || std::memcmp(raw.data(), "PBM1", 4) != 0 || rd16p(raw.data() + 4) != 16 || rd16p(raw.data() + 10) != 12 || rd32p(raw.data() + 12))
                    throw std::runtime_error("invalid PBM1 header");
                uint16_t resource = rd16p(raw.data() + 6), count = rd16p(raw.data() + 8);
                if (!rangeOk(raw.size(), 16, uint64_t(count) * 12)) throw std::runtime_error("PBM1 records outside payload");
                PblkPool pool;
                if (!pblkPool(resource, pool, error)) return false;
                size_t previous_end = 0;
                for (uint16_t i = 0; i < count; ++i) {
                    const uint8_t* rec = raw.data() + 16 + size_t(i) * 12;
                    uint16_t dest = rd16p(rec), bytes = rd16p(rec + 2), source = rd16p(rec + 8);
                    uint32_t block = rd32p(rec + 4);
                    if (rd16p(rec + 10) || !bytes || dest < previous_end || block >= pool.blocks.size() ||
                        !rangeOk(output.size(), dest, bytes) || !rangeOk(pool.blocks[block].size(), source, bytes))
                        throw std::runtime_error("invalid PBM1 copy record");
                    std::copy(pool.blocks[block].begin() + source, pool.blocks[block].begin() + source + bytes, output.begin() + dest);
                    previous_end = size_t(dest) + bytes;
                }
            } else if (descriptor.encoding == 3) {
                output.assign(engine.page_size, 0);
                if (!(descriptor.flags & PAGE_BASE_ZERO)) output = engine.page_template;
                if (raw.size() < 16 || std::memcmp(raw.data(), "RMP1", 4) != 0 || rd16p(raw.data() + 4) != 16 || rd16p(raw.data() + 8) != 16 || rd16p(raw.data() + 10) || rd32p(raw.data() + 12))
                    throw std::runtime_error("invalid RMP1 header");
                uint16_t count = rd16p(raw.data() + 6);
                if (!rangeOk(raw.size(), 16, uint64_t(count) * 16)) throw std::runtime_error("RMP1 records outside payload");
                size_t previous_end = 0;
                for (uint16_t i = 0; i < count; ++i) {
                    const uint8_t* rec = raw.data() + 16 + size_t(i) * 16;
                    uint16_t dest = rd16p(rec), bytes = rd16p(rec + 2), resource = rd16p(rec + 6);
                    uint8_t type = rec[4], reserved = rec[5];
                    uint32_t source = rd32p(rec + 8), tail_reserved = rd32p(rec + 12);
                    if (reserved || tail_reserved || !bytes || dest < previous_end || !rangeOk(output.size(), dest, bytes))
                        throw std::runtime_error("invalid RMP1 record");
                    if (type == 0) {
                        if (resource >= resources_.size() || !(resources_[resource].flags & RES_PAGE_SOURCE))
                            throw std::runtime_error("RMP1 copy references non-page-source resource");
                        std::vector<uint8_t> source_data;
                        if (!logicalResource(resource, source_data, error)) return false;
                        if (!rangeOk(source_data.size(), source, bytes)) throw std::runtime_error("RMP1 source range outside resource");
                        std::copy(source_data.begin() + source, source_data.begin() + source + bytes, output.begin() + dest);
                    } else if (type == 1) {
                        if (resource != NULL16 || !rangeOk(raw.size(), source, bytes)) throw std::runtime_error("invalid RMP1 inline record");
                        std::copy(raw.begin() + source, raw.begin() + source + bytes, output.begin() + dest);
                    } else if (type == 2) {
                        if (resource != NULL16 || (source & 0xffffff00u)) throw std::runtime_error("invalid RMP1 fill record");
                        std::fill(output.begin() + dest, output.begin() + dest + bytes, static_cast<uint8_t>(source));
                    } else {
                        throw std::runtime_error("unknown RMP1 record type");
                    }
                    previous_end = size_t(dest) + bytes;
                }
            } else {
                throw std::runtime_error("unknown page encoding");
            }
        }
        if (output.size() != engine.page_size) throw std::runtime_error("materialized page size mismatch");
        if (descriptor.final_crc && crc32(output) != descriptor.final_crc) throw std::runtime_error("materialized page CRC mismatch");
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}

} // namespace tinyksp
