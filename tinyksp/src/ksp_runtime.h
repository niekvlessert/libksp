#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace tinyksp {

struct Engine {
    uint32_t flags = 0;
    uint32_t hardware = 0;
    uint16_t abi = 0;
    uint16_t tick_hz = 0;
    uint16_t load_address = 0;
    uint16_t page_size = 0;
    uint16_t init_address = 0;
    uint16_t play_address = 0;
    uint16_t stop_address = 0;
    uint16_t gateway = 0;
    uint16_t replace_start = 0;
    uint16_t first_page = 0;
    uint16_t page_count = 0;
    uint16_t default_mwk = 0xffff;
    uint8_t template_compression = 0;
    uint8_t first_bank = 0;
    uint8_t bank_count = 0;
    uint8_t bank_width = 0;
    uint32_t name_offset = 0xffffffffu;
    std::vector<uint8_t> page_template;
};

struct MetadataEntry {
    std::string key;
    std::string value;
};

struct PlaybackVariant {
    uint16_t track_index = 0xffff;
    uint32_t hardware = 0;
    uint16_t quality_rank = 0;
    std::string label;
    bool visible_fallback = false;
};

struct Track {
    uint16_t page = 0;
    uint16_t song = 0;
    uint16_t flags = 0;
    uint16_t mwk = 0xffff;
    uint16_t image = 0xffff;
    uint32_t title_offset = 0xffffffffu;
    uint32_t duration_ms = 0xffffffffu;
    uint32_t loop_start_ms = 0xffffffffu;
    uint32_t loop_end_ms = 0xffffffffu;
    uint32_t fade_ms = 0xffffffffu;
};

class KspPackage {
public:
    bool load(const std::string& path, std::string& error);
    void clear();

    int visibleTrackCount() const;
    uint16_t logicalTrackAt(int visible_index) const;
    std::string visibleTrackTitle(int visible_index) const;
    std::vector<PlaybackVariant> playbackVariants(int visible_index,
                                                  uint32_t available_hardware) const;
    std::string playbackUnsupportedReason(int visible_index,
                                          uint32_t available_hardware) const;

    bool resolveTrack(uint16_t logical_track, uint32_t available_hardware,
                      uint16_t& implementation_track, std::string& error) const;
    bool resolveTrackVariant(int visible_index, int variant_index,
                             uint32_t available_hardware,
                             uint16_t& implementation_track, std::string& error) const;
    bool resolvePhysicalTrack(uint16_t physical_track, uint32_t available_hardware,
                              uint16_t& implementation_track, std::string& error) const;
    Track effectiveTrack(uint16_t logical_track, uint16_t implementation_track) const;
    bool materializeTrackPage(uint16_t implementation_track,
                              std::vector<uint8_t>& page, std::string& error) const;
    bool materializeDynamicPage(uint16_t implementation_track, uint16_t local_page,
                                std::vector<uint8_t>& page, std::string& error) const;
    bool materializeResource(uint16_t resource_index, std::vector<uint8_t>& output,
                             std::string& error) const;
    std::string resourceKind(uint16_t resource_index) const;

    const Track* track(uint16_t index) const;
    const Engine* engineForTrack(uint16_t index) const;
    uint16_t minorVersion() const { return minor_version_; }
    uint64_t fileSize() const { return bytes_.size(); }
    size_t engineCount() const { return engines_.size(); }
    size_t pageCount() const { return pages_.size(); }
    size_t trackCount() const { return tracks_.size(); }
    size_t resourceCount() const { return resources_.size(); }
    uint16_t defaultTrack() const { return default_track_; }
    uint16_t coverResource() const { return cover_resource_; }
    const std::vector<MetadataEntry>& metadata() const { return metadata_; }
    const std::vector<std::string>& metadataWarnings() const { return metadata_warnings_; }
    bool hasHardwareVariants() const { return !hvr_logicals_.empty(); }
    std::vector<MetadataEntry> generalMetadata() const;
    std::vector<std::string> engineSummaries() const;

private:
    struct Page {
        uint16_t engine = 0;
        uint8_t encoding = 0;
        uint8_t compression = 0;
        uint16_t flags = 0;
        uint32_t offset = 0;
        uint32_t packed_size = 0;
        uint32_t unpacked_size = 0;
        uint32_t final_crc = 0;
    };

    struct Resource {
        std::string kind;
        uint16_t flags = 0;
        uint8_t compression = 0;
        uint32_t offset = 0;
        uint32_t packed_size = 0;
        uint32_t unpacked_size = 0;
        uint32_t crc = 0;
        uint32_t aux0 = 0;
        uint32_t aux1 = 0;
    };

    struct PblkPool {
        uint16_t block_size = 0;
        std::vector<std::vector<uint8_t>> blocks;
    };

    struct HpolPool {
        uint16_t block_size = 0;
        std::vector<uint16_t> positions;
        std::vector<uint16_t> matrix;
        std::vector<std::vector<uint8_t>> blocks;
    };

    struct HvrLogical {
        uint16_t logical_track = 0xffff;
        uint16_t first_candidate = 0;
        uint16_t candidate_count = 0;
    };

    struct HvrCandidate {
        uint16_t implementation_track = 0xffff;
        uint16_t quality_rank = 0;
    };

    bool parse(std::string& error);
    bool parseMetadata(const std::vector<uint8_t>& raw, uint16_t container_minor,
                       std::string& error);
    bool parseHardwareVariants(std::string& error);
    bool validatePhysicalPayloadViews(std::string& error) const;
    bool materializePage(uint16_t page_index, std::vector<uint8_t>& output,
                         std::string& error) const;
    bool logicalResource(uint16_t index, std::vector<uint8_t>& output,
                         std::string& error) const;
    bool pblkPool(uint16_t index, PblkPool& output, std::string& error) const;
    bool hpolPool(HpolPool& output, std::string& error) const;
    bool candidateSupported(uint16_t track_index, uint32_t available_hardware) const;
    std::string stringAt(uint32_t offset) const;

    std::vector<uint8_t> bytes_;
    uint16_t minor_version_ = 0;
    uint16_t default_track_ = 0;
    uint16_t meta_resource_ = 0xffff;
    uint16_t cover_resource_ = 0xffff;
    std::vector<uint8_t> strings_;
    std::vector<Engine> engines_;
    std::vector<Page> pages_;
    std::vector<Track> tracks_;
    std::vector<Resource> resources_;
    std::vector<uint16_t> visible_tracks_;
    std::vector<MetadataEntry> metadata_;
    std::vector<std::string> metadata_warnings_;
    std::vector<HvrLogical> hvr_logicals_;
    std::vector<HvrCandidate> hvr_candidates_;
    std::vector<int32_t> hvr_record_by_track_;

    mutable std::unordered_map<uint16_t, std::vector<uint8_t>> resource_cache_;
    mutable std::unordered_map<uint16_t, PblkPool> pblk_cache_;
    mutable bool hpol_loaded_ = false;
    mutable HpolPool hpol_cache_;
};

uint32_t supportedHardwareMask();
std::string hardwareDescription(uint32_t hardware);

} // namespace tinyksp
