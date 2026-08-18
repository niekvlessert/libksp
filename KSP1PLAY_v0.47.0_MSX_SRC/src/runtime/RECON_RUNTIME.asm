; KSP 1.x PBM1/PBLK and RMP1 page materializer.
; Installed by KSPOS at C400h in the process page-3 segment.
; PAGE3_WORKRAM hides this segment only while the engine is executing.
org 0xC400
include "RECON_RUNTIME_SYMBOLS.inc"

PORT_OPL4_WAVE_A equ 0x7E
PORT_OPL4_WAVE_D equ 0x7F

    jp recon_apply
    jp recon_release
    jp recon_dynamic
    jp recon_disk_read_cached
    jp recon_cache_invalidate
    jp recon_zx_select
    jp recon_cold_stream_begin
    jp recon_cold_prefetch_next
    jp recon_preload_track
    jp recon_validate_kzb_control
    jp recon_validate_kzb_leaf
    jp recon_prepare_page2_runtime
    jp recon_free_page2_runtime
    jp recon_backup_split
    jp recon_restore_split

; ---------------------------------------------------------------------------
; Public entry points
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; KSP 1.05 selected-resource semantic-range validation
; ---------------------------------------------------------------------------
; The constrained MSX player reads only the selected track's resource. It does
; not claim exclusive ownership of enclosing resource spans, so exact aliases
; and overlapping views are naturally accepted. These helpers ensure the KZB1
; control table and each compressed leaf remain inside the selected resource.
recon_validate_kzb_control:
    ; KSP 1.00-1.04 compatibility: these readers historically accepted the
    ; selected KZB1 view without KSP 1.05 enclosing-span validation. Some early
    ; KSP 1.04 MoonSound packs (including Dawn of Sorrow v1.1) already shared
    ; physical KZB1 leaves before the rule was formalized in KSP 1.05.
    ld a,(KSP_HEADER+6)
    cp 5
    jr nc,recon_validate_kzb_control_105
    or a
    ret
recon_validate_kzb_control_105:
    ld hl,(MWK_BLOCK_TABLE)
    ld a,(MWK_BLOCK_TABLE+2)
    or a
    jr nz,recon_kzb_range_bad
    ld de,16
    or a
    sbc hl,de
    jr c,recon_kzb_range_bad
    ld hl,(MWK_BLOCK_COUNT)
    ld de,16
    call MUL16X16_24
    ld c,a
    ld de,(MWK_BLOCK_TABLE)
    add hl,de
    ld a,(MWK_BLOCK_TABLE+2)
    adc a,c
    jr c,recon_kzb_range_bad
    ld c,a
    ld a,(RESOURCE_ENTRY+14)
    cp c
    jr c,recon_kzb_range_bad
    jr nz,recon_kzb_range_ok
    ld de,(RESOURCE_ENTRY+12)
    or a
    sbc hl,de
    jr c,recon_kzb_range_ok
    jr nz,recon_kzb_range_bad
recon_kzb_range_ok:
    or a
    ret

recon_validate_kzb_leaf:
    ld a,(KSP_HEADER+6)
    cp 5
    jr nc,recon_validate_kzb_leaf_105
    or a
    ret
recon_validate_kzb_leaf_105:
    ld hl,(IO_BUFFER)
    ld a,(IO_BUFFER+2)
    ld de,(IO_BUFFER+4)
    add hl,de
    ld c,a
    ld a,(IO_BUFFER+6)
    adc a,c
    jr c,recon_kzb_range_bad
    ld c,a
    ld a,(RESOURCE_ENTRY+14)
    cp c
    jr c,recon_kzb_range_bad
    jr nz,recon_kzb_range_ok
    ld de,(RESOURCE_ENTRY+12)
    or a
    sbc hl,de
    jr c,recon_kzb_range_ok
    jr nz,recon_kzb_range_bad
    jr recon_kzb_range_ok
recon_kzb_range_bad:
    scf
    ret

; PAGE2_RUNTIME needs an independently writable copy. Aliasing page 1 and
; page 2 corrupts engines that decompress immutable 4000h tables into 8000h.
recon_prepare_page2_runtime:
    ld a,(ENGINE_P2_SEGMENT_ALLOCATED)
    or a
    jr z,recon_prepare_page2_allocate
    ; INIT may have decompressed or otherwise modified PAGE2_RUNTIME. UI and
    ; callback paths only need to remap the existing segment; copying PAGE1
    ; again would destroy that live runtime state.
    ld a,(ENGINE_P2_SEGMENT)
    call MAP_P2
    or a
    ret
recon_prepare_page2_allocate:
    call MAPPER_ALLOC_USER_PRIMARY
    ret c
    ld (ENGINE_P2_SEGMENT),a
    ld a,1
    ld (ENGINE_P2_SEGMENT_ALLOCATED),a
recon_prepare_page2_copy:
    ld a,(ENGINE_P2_SEGMENT)
    call MAP_P2
    ld hl,0x4000
    ld de,0x8000
    ld bc,0x4000
    ldir
    or a
    ret

recon_free_page2_runtime:
    ld a,(ENGINE_P2_SEGMENT_ALLOCATED)
    or a
    ret z
    call RESTORE_PROCESS_PAGES
    ld a,(ENGINE_P2_SEGMENT)
    call MAPPER_FREE_PRIMARY
    xor a
    ld (ENGINE_P2_SEGMENT_ALLOCATED),a
    ret

recon_apply:
    call recon_validate_page_entry
    jr c,recon_apply_bad
    call recon_prepare_base
    jr c,recon_apply_bad
    call recon_load_map
    jr c,recon_apply_bad
    ld a,(PAGE_ENTRY+2)
    cp 2
    jr z,recon_apply_pbm
    cp 3
    jr nz,recon_apply_bad
    call recon_apply_rmp1
    jr recon_apply_finish
recon_apply_pbm:
    call recon_apply_pbm1
recon_apply_finish:
    push af
    call RESTORE_PROCESS_PAGES
    pop af
    ret
recon_apply_bad:
    call RESTORE_PROCESS_PAGES
    scf
    ret

recon_release:
    call RESTORE_PROCESS_PAGES
    call recon_track_cache_release
    ld a,(recon_map_allocated)
    or a
    jr z,recon_release_done
    ld a,(recon_map_segment)
    call MAPPER_FREE_PRIMARY
    xor a
    ld (recon_map_allocated),a
    ld a,(MAPPER_POOL_COUNT)
    ld (KSPOS_FREE_SEGMENTS),a
recon_release_done:
    call recon_reset_caches
    or a
    ret

; Dynamic page callbacks use the same page-materialization logic. Sparse pages keep
; the original proven sparse decoder; encodings 2 and 3 use recon_apply.
recon_dynamic:
    ld hl,(DYNAMIC_PAGE)
    ld de,(ENGINE_ENTRY+28)
    or a
    sbc hl,de
    jr nc,recon_dynamic_bad
    add hl,de
    ld de,(ENGINE_ENTRY+26)
    add hl,de
    jr c,recon_dynamic_bad
    ; The selected-track preloader retains this track's page-table entries in
    ; page-3 RAM.  A cache hit avoids even the old 24-byte disk read.
    call recon_track_cache_get_page_entry
    jr z,recon_dynamic_page_entry_ready
    ld hl,(DYNAMIC_PAGE)
    ld de,(ENGINE_ENTRY+26)
    add hl,de
    ld de,(KSP_HEADER+0x1E)
    call MUL16X16_24
    ld c,a
    ld de,(KSP_HEADER+0x18)
    add hl,de
    ld a,(KSP_HEADER+0x1A)
    adc a,c
    ld de,PAGE_ENTRY
    ld bc,24
    call READ_AT
    jr nz,recon_dynamic_bad
recon_dynamic_page_entry_ready:
    ld hl,(PAGE_ENTRY)
    ld de,(CURRENT_ENGINE)
    or a
    sbc hl,de
    jr nz,recon_dynamic_bad
    ld a,(PAGE_ENTRY+2)
    or a
    jr z,recon_dynamic_sparse
    cp 2
    jr z,recon_dynamic_mapped
    cp 3
    jr nz,recon_dynamic_bad
recon_dynamic_mapped:
    ld a,1
    ld (DYNAMIC_INSTALL_ACTIVE),a
    call recon_apply
    push af
    xor a
    ld (DYNAMIC_INSTALL_ACTIVE),a
    call PREPARE_ENGINE_PAGE2
    pop af
    ret
recon_dynamic_sparse:
    call recon_validate_sparse_dynamic
    jr c,recon_dynamic_bad
    ld a,(PAGE_ENTRY+4)
    bit 1,a
    jr z,recon_dynamic_sparse_restore
    ; KSP 1.06 MSX-direct page. If its selected-track mapper segment is
    ; available, switch page 1 instead of copying 12-16 KiB during PLAY.
    call recon_dynamic_direct_page
    ret nc
    ; Correctness fallback: a valid direct page can still be copied in full
    ; when preload was unavailable; this may be slower but never changes data.
    jr recon_dynamic_sparse_ready
recon_dynamic_sparse_restore:
    call recon_restore_template_range
    jr c,recon_dynamic_bad
recon_dynamic_sparse_ready:
    ld a,1
    ld (DYNAMIC_INSTALL_ACTIVE),a
    call APPLY_SPARSE_PAGE
    push af
    xor a
    ld (DYNAMIC_INSTALL_ACTIVE),a
    call PREPARE_ENGINE_PAGE2
    pop af
    ret

; Flag bit 1 direct pages are complete materialized 16 KiB engine pages. The
; selected-track preload stores each contiguous 16 KiB payload in one mapper
; segment. Preserve the mutable engine prefix [4000h,replace_start) into the
; target segment, then make that segment the new page 1. The large music-data
; replacement range therefore changes without a frame-sized copy.
; Carry clear: switched directly. Carry set: caller must use full-copy fallback.
recon_dynamic_direct_page:
    ld a,(PAGE_ENTRY+3)
    or a
    jr nz,recon_dynamic_direct_bad
    ld hl,(PAGE_ENTRY+12)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,recon_dynamic_direct_bad
    ld hl,(PAGE_ENTRY+16)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,recon_dynamic_direct_bad

    ; KSP 1.06 direct pages are complete 16 KiB payloads.  When the selected
    ; physical track's page run is contiguous, the ordinary preload cache has
    ; already placed those raw pages in consecutive 16 KiB mapper segments.
    ; Reuse those segments directly instead of allocating duplicate segments.
    ; This keeps the direct profile viable on a 128 KiB mapper.
    ld a,(recon_track_cache_valid)
    or a
    jr z,recon_dynamic_direct_bad
    ld hl,(PAGE_ENTRY+8)
    ld de,(recon_track_cache_base)
    or a
    sbc hl,de
    ld (recon_track_diff),hl
    ld a,(PAGE_ENTRY+10)
    ld b,a
    ld a,(recon_track_cache_base+2)
    ld c,a
    ld a,b
    sbc a,c
    jr c,recon_dynamic_direct_bad
    ld (recon_track_diff+2),a

    ; A direct page must begin on a mapper-segment boundary inside the packed
    ; run.  PAGE_ENTRY.packed/unpacked_size above already prove it occupies
    ; exactly one complete segment.
    ld hl,(recon_track_diff)
    ld a,l
    or a
    jr nz,recon_dynamic_direct_bad
    ld a,h
    and 0x3F
    jr nz,recon_dynamic_direct_bad

    ; Mapper segment index = 24-bit diff >> 14.
    ld a,(recon_track_diff+2)
    add a,a
    add a,a
    ld b,a
    ld a,(recon_track_diff+1)
    rlca
    rlca
    and 3
    or b
    ld b,a
    ld a,(recon_track_cache_allocated)
    cp b
    jr c,recon_dynamic_direct_bad
    jr z,recon_dynamic_direct_bad
    ld a,b
    ld e,a
    ld d,0
    ld hl,recon_track_cache_segments
    add hl,de
    ld a,(hl)
    ld (recon_track_source_segment),a

    ; KSP 1.07 direct-page state window.  KSP 1.06 direct pages preserve the
    ; complete persistent prefix [4000h,replace_start).  KSP 1.07 assigns the
    ; formerly reserved engine-entry tail:
    ;   +38h u16 direct_state_start (inclusive)
    ;   +3Ah u16 direct_state_end   (exclusive)
    ;   +3Ch u32 reserved, zero
    ; A zero/invalid window falls back to the KSP 1.06 full-prefix copy.
    ; This is deliberately declarative: the packer proves which live engine
    ; bytes must survive a mapper page switch; no game-specific addresses live
    ; in KSP1PLAY.
    ld hl,0x4000
    ld (recon_direct_copy_start),hl
    ld hl,(ENGINE_ENTRY+24)
    ld de,0x4000
    or a
    sbc hl,de
    ld (recon_direct_copy_length),hl

    ld a,(KSP_HEADER+6)
    cp 7
    jr c,recon_dynamic_direct_copy_ready

    ; Require 4000h <= state_start < state_end <= replace_start.
    ld hl,(ENGINE_ENTRY+56)
    ld a,h
    or l
    jr z,recon_dynamic_direct_copy_ready
    ld de,0x4000
    or a
    sbc hl,de
    jr c,recon_dynamic_direct_copy_ready
    ld hl,(ENGINE_ENTRY+58)
    ld de,(ENGINE_ENTRY+56)
    or a
    sbc hl,de
    jr c,recon_dynamic_direct_copy_ready
    jr z,recon_dynamic_direct_copy_ready
    push hl                         ; candidate length
    ld hl,(ENGINE_ENTRY+24)
    ld de,(ENGINE_ENTRY+58)
    or a
    sbc hl,de
    pop hl
    jr c,recon_dynamic_direct_copy_ready
    ld (recon_direct_copy_length),hl
    ld hl,(ENGINE_ENTRY+56)
    ld (recon_direct_copy_start),hl

recon_dynamic_direct_copy_ready:
    ld bc,(recon_direct_copy_length)
    ld a,b
    or c
    jr z,recon_dynamic_direct_map
    ld a,(recon_track_source_segment)
    call MAP_P2
    ld hl,(recon_direct_copy_start)
    push hl
    ld de,0x4000
    add hl,de
    ex de,hl                       ; DE = target address in mapped page 2
    pop hl                         ; HL = live source address in page 1
    ld bc,(recon_direct_copy_length)
    ldir
recon_dynamic_direct_map:
    ld a,(recon_track_source_segment)
    call MAP_P1
    call PREPARE_ENGINE_PAGE2
    or a
    ret
recon_dynamic_direct_bad:
    scf
    ret
recon_dynamic_bad:
    xor a
    ld (DYNAMIC_INSTALL_ACTIVE),a
    call PREPARE_ENGINE_PAGE2
    scf
    ret

; ---------------------------------------------------------------------------
; Common page validation/base/map loading
; ---------------------------------------------------------------------------
recon_validate_page_entry:
    ld a,(PAGE_ENTRY+2)
    cp 2
    jr z,recon_validate_encoding_ok
    cp 3
    jr nz,recon_invalid
recon_validate_encoding_ok:
    ld a,(PAGE_ENTRY+3)
    cp 2
    jr nc,recon_invalid
    ld a,(PAGE_ENTRY+5)
    or a
    jr nz,recon_invalid
    ld a,(PAGE_ENTRY+4)
    and 0xFE
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+6)
    ld a,h
    or l
    jr nz,recon_invalid
    ld a,(PAGE_ENTRY+11)
    or a
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+14)
    ld a,h
    or l
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+18)
    ld a,h
    or l
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+16)
    ld de,16
    or a
    sbc hl,de
    jr c,recon_invalid
    add hl,de
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_invalid
    ld a,(PAGE_ENTRY+3)
    or a
    jr nz,recon_validate_packed_nonzero
    ld hl,(PAGE_ENTRY+12)
    ld de,(PAGE_ENTRY+16)
    or a
    sbc hl,de
    jr nz,recon_invalid
recon_validate_packed_nonzero:
    ld hl,(PAGE_ENTRY+12)
    ld a,h
    or l
    jr z,recon_invalid
    or a
    ret
recon_invalid:
    scf
    ret

recon_validate_sparse_dynamic:
    ld a,(PAGE_ENTRY+3)
    cp 2
    jr nc,recon_invalid
    ld a,(PAGE_ENTRY+5)
    or a
    jr nz,recon_invalid
    ld a,(PAGE_ENTRY+4)
    and 0xFD
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+14)
    ld a,h
    or l
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+18)
    ld a,h
    or l
    jr nz,recon_invalid
    ld hl,(PAGE_ENTRY+16)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_invalid
    ld a,(TEMPLATE_CACHE_READY)
    or a
    jr z,recon_invalid
    or a
    ret

recon_prepare_base:
    ld a,(PAGE_ENTRY+4)
    and 1
    jr nz,recon_prepare_zero
    ld a,(DYNAMIC_INSTALL_ACTIVE)
    or a
    jp nz,recon_restore_template_range
    call LOAD_TEMPLATE_PAGE
    ret
recon_prepare_zero:
    ld a,(DYNAMIC_INSTALL_ACTIVE)
    or a
    jr z,recon_zero_full
    ld hl,(ENGINE_ENTRY+24)
    ld de,0x8000
    or a
    sbc hl,de
    jr nc,recon_invalid
    add hl,de
    ex de,hl
    ld hl,0x8000
    or a
    sbc hl,de
    ld b,h
    ld c,l
    ex de,hl
    xor a
    jp recon_fill_zero
recon_zero_full:
    ld hl,0x4000
    ld bc,0x4000
    xor a
    jp recon_fill_zero

; HL destination, BC count, A fill byte.
recon_fill_zero:
    ld d,h
    ld e,l
    ld (hl),a
    inc de
    dec bc
    ld a,b
    or c
    ret z
    ldir
    or a
    ret

recon_restore_template_range:
    ld a,(TEMPLATE_CACHE_READY)
    or a
    jr z,recon_invalid
    ld hl,(ENGINE_ENTRY+24)
    ld de,(ENGINE_ENTRY+12)
    or a
    sbc hl,de
    jr c,recon_invalid
    push hl
    ld a,(TEMPLATE_SEGMENT)
    call MAP_P2
    pop de
    ld hl,0x8000
    add hl,de
    ld de,(ENGINE_ENTRY+24)
    push hl
    ld hl,0x8000
    or a
    sbc hl,de
    ld b,h
    ld c,l
    pop hl
    ldir
    ld a,(ORIGINAL_P2)
    call MAP_P2
    or a
    ret

recon_ensure_map_segment:
    ld a,(recon_map_allocated)
    or a
    ret nz
    call MAPPER_ALLOC_USER_PRIMARY
    ret c
    ld (recon_map_segment),a
    ld a,1
    ld (recon_map_allocated),a
    ld a,(MAPPER_POOL_COUNT)
    ld (KSPOS_FREE_SEGMENTS),a
    or a
    ret

recon_load_map:
    call recon_ensure_map_segment
    ret c
    ld a,(recon_map_segment)
    call MAP_P2
    ld a,(PAGE_ENTRY+3)
    or a
    jr z,recon_load_map_raw
    ld hl,(PAGE_ENTRY+8)
    ld a,(PAGE_ENTRY+10)
    ld de,(PAGE_ENTRY+12)
    ld b,d
    ld c,e
    call STREAM_BEGIN
    ret c
    xor a
    ld (ZX_MODE),a
    ld hl,0x8000
    ld (LINEAR_BASE),hl
    ld hl,(PAGE_ENTRY+16)
    xor a
    call ZX_SET_OUTPUT_SIZE
    call ZX_DECODE_STREAM
    ret
recon_load_map_raw:
    ld hl,(PAGE_ENTRY+8)
    ld a,(PAGE_ENTRY+10)
    ld de,0x8000
    ld bc,(PAGE_ENTRY+16)
    call READ_AT
    ret z
    scf
    ret

recon_map_map:
    ld a,(recon_map_segment)
    jp MAP_P2
recon_map_scratch:
    ld a,(ORIGINAL_P2)
    jp MAP_P2

recon_reset_caches:
    ld hl,0xFFFF
    ld (recon_cached_slab),hl
    ld (recon_cached_resource),hl
    ld (recon_cached_kzb_block),hl
    ret

; ---------------------------------------------------------------------------
; PBM1/PBLK
; ---------------------------------------------------------------------------
recon_apply_pbm1:
    call recon_reset_caches
    call recon_map_map
    ld hl,0x8000
    ld de,recon_header
    ld bc,16
    ldir
    ld hl,recon_header
    ld a,(hl)
    cp 'P'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'B'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'M'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,recon_pbm_bad
    ld hl,(recon_header+4)
    ld de,16
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld hl,(recon_header+0x0A)
    ld de,12
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld hl,(recon_header+0x0C)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_header+0x0E)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_header+8)
    ld (recon_records_left),hl
    ; 16 + count*12 must fit the map payload.
    call recon_count_times_12
    jr c,recon_pbm_bad
    ld de,16
    add hl,de
    jr c,recon_pbm_bad
    ld de,(PAGE_ENTRY+16)
    or a
    sbc hl,de
    jr c,recon_pbm_table_ok
    jr z,recon_pbm_table_ok
    jr recon_pbm_bad
recon_pbm_table_ok:
    ld hl,(recon_header+6)
    call recon_load_resource
    jr c,recon_pbm_bad
    call recon_validate_pblk
    jr c,recon_pbm_bad
    ld hl,0x8010
    ld (recon_map_ptr),hl
    ld hl,0
    ld (recon_previous_end),hl
recon_pbm_loop:
    ld hl,(recon_records_left)
    ld a,h
    or l
    jr z,recon_pbm_done
    call recon_map_map
    ld hl,(recon_map_ptr)
    ld de,recon_record
    ld bc,12
    ldir
    ld (recon_map_ptr),hl
    call recon_validate_pbm_record
    jr c,recon_pbm_bad
    call recon_load_pool_block
    jr c,recon_pbm_bad
    call recon_copy_pool_slice
    jr c,recon_pbm_bad
    ld hl,(recon_records_left)
    dec hl
    ld (recon_records_left),hl
    jr recon_pbm_loop
recon_pbm_done:
    or a
    ret
recon_pbm_bad:
    scf
    ret

recon_count_times_12:
    ; HL count -> HL count*12.
    push hl
    add hl,hl
    jr c,recon_count_bad_pop
    add hl,hl
    jr c,recon_count_bad_pop
    ld d,h
    ld e,l
    pop hl
    add hl,hl
    jr c,recon_count_bad
    add hl,de
    ret nc
recon_count_bad:
    scf
    ret
recon_count_bad_pop:
    pop de
    scf
    ret

recon_validate_pblk:
    ld hl,RESOURCE_ENTRY
    ld a,(hl)
    cp 'P'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'B'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'L'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'K'
    jr nz,recon_pbm_bad
    ld a,(RESOURCE_ENTRY+5)
    or a
    jr nz,recon_pbm_bad
    ld a,(RESOURCE_ENTRY+4)
    and 0xFE
    jr nz,recon_pbm_bad
    ld a,(RESOURCE_ENTRY+6)
    or a
    jr nz,recon_pbm_bad
    ld a,(RESOURCE_ENTRY+7)
    or a
    jr nz,recon_pbm_bad
    ld hl,RESOURCE_ENTRY
    ld de,recon_pool_resource
    ld bc,32
    ldir
    ; Read PBK1 header.
    ld hl,(recon_pool_resource+8)
    ld a,(recon_pool_resource+10)
    ld de,recon_pbk_header
    ld bc,32
    call READ_AT
    jr nz,recon_pbm_bad
    ld hl,recon_pbk_header
    ld a,(hl)
    cp 'P'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'B'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp 'K'
    jr nz,recon_pbm_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+4)
    ld de,32
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+6)
    ld de,8
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+8)
    ld de,16
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+0x0A)
    ld a,h
    or l
    jr z,recon_pbm_bad
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_pbm_bad
    ld hl,(recon_pbk_header+0x12)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+0x1C)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_pbk_header+0x1E)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    or a
    ret

recon_validate_pbm_record:
    ld hl,(recon_record)
    ld (recon_dest),hl
    ld de,(recon_previous_end)
    or a
    sbc hl,de
    jr c,recon_pbm_bad
    ld hl,(recon_record+2)
    ld a,h
    or l
    jr z,recon_pbm_bad
    ld (recon_length),hl
    ld hl,(recon_dest)
    ld de,(recon_length)
    add hl,de
    jr c,recon_pbm_bad
    ld (recon_record_end),hl
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_pbm_bad
    ld hl,(recon_record+0x0A)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ; block index is 24-bit; top byte must be zero for the MSX file profile.
    ld a,(recon_record+7)
    or a
    jr nz,recon_pbm_bad
    ; index < PBK block_count (24-bit).
    ld hl,recon_record+4
    ld de,recon_pbk_header+0x0C
    call recon_compare_u24
    jr nc,recon_pbm_bad
    ; source offset + length <= fixed block size.
    ld hl,(recon_record+8)
    ld de,(recon_length)
    add hl,de
    jr c,recon_pbm_bad
    ld de,(recon_pbk_header+0x0A)
    or a
    sbc hl,de
    jr c,recon_pbm_source_ok
    jr z,recon_pbm_source_ok
    jr recon_pbm_bad
recon_pbm_source_ok:
    ld hl,(recon_record_end)
    ld (recon_previous_end),hl
    call recon_clip_record
    ret

recon_load_pool_block:
    ; descriptor absolute = PBLK + block_table + block_index*8.
    ld a,(recon_record+4)
    ld l,a
    ld a,(recon_record+5)
    ld h,a
    ld a,(recon_record+6)
    ld (recon_rel24+2),a
    ld (recon_rel24),hl
    call recon_shift_rel24_3
    jr c,recon_pbm_bad
    ld hl,(recon_pbk_header+0x14)
    ld a,(recon_pbk_header+0x16)
    call recon_add_to_rel24
    jr c,recon_pbm_bad
    call recon_pool_abs_from_rel
    jr c,recon_pbm_bad
    ld de,recon_block_desc
    ld bc,8
    call READ_AT
    jr nz,recon_pbm_bad
    ld hl,(recon_block_desc+4)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_block_desc+6)
    ld a,h
    or l
    jr nz,recon_pbm_bad
    ld hl,(recon_block_desc)
    ld de,(recon_pbk_header+0x10)
    or a
    sbc hl,de
    jr nc,recon_pbm_bad
    ; Read slab descriptor.
    ld hl,(recon_block_desc)
    add hl,hl
    jr c,recon_pbm_bad
    add hl,hl
    jr c,recon_pbm_bad
    add hl,hl
    jr c,recon_pbm_bad
    add hl,hl
    jr c,recon_pbm_bad
    ld (recon_rel24),hl
    xor a
    ld (recon_rel24+2),a
    ld hl,(recon_pbk_header+0x18)
    ld a,(recon_pbk_header+0x1A)
    call recon_add_to_rel24
    jr c,recon_pbm_bad
    call recon_pool_abs_from_rel
    jr c,recon_pbm_bad
    ld de,recon_slab_desc
    ld bc,16
    call READ_AT
    jr nz,recon_pbm_bad
    ld a,(recon_slab_desc+0x0B)
    or a
    jr nz,recon_pbm_bad
    ld a,(recon_slab_desc+0x0A)
    cp 2
    jr nc,recon_pbm_bad
    ld hl,(recon_slab_desc+8)
    ld a,h
    or l
    jr z,recon_pbm_bad
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_pbm_bad
    ld hl,(recon_block_desc+2)
    ld de,(recon_pbk_header+0x0A)
    add hl,de
    jr c,recon_pbm_bad
    ld de,(recon_slab_desc+8)
    or a
    sbc hl,de
    jr c,recon_pool_block_range_ok
    jr z,recon_pool_block_range_ok
    jr recon_pbm_bad
recon_pool_block_range_ok:
    ; Decode only when this slab is not already in original page-2 RAM.
    ld hl,(recon_block_desc)
    ld de,(recon_cached_slab)
    or a
    sbc hl,de
    ret z
    ld hl,(recon_block_desc)
    ld (recon_cached_slab),hl
    call recon_map_scratch
    ld a,(recon_slab_desc+0x0A)
    or a
    jr z,recon_load_slab_raw
    ld hl,(recon_slab_desc)
    ld a,(recon_slab_desc+2)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    call recon_pool_abs_from_rel
    jr c,recon_pbm_bad
    ld de,(recon_slab_desc+4)
    ld b,d
    ld c,e
    ld a,(recon_slab_desc+6)
    or a
    jr nz,recon_pbm_bad
    call STREAM_BEGIN
    ret c
    xor a
    ld (ZX_MODE),a
    ld hl,0x8000
    ld (LINEAR_BASE),hl
    ld hl,(recon_slab_desc+8)
    xor a
    call ZX_SET_OUTPUT_SIZE
    call ZX_DECODE_STREAM
    ret
recon_load_slab_raw:
    ld hl,(recon_slab_desc+4)
    ld de,(recon_slab_desc+8)
    or a
    sbc hl,de
    jr nz,recon_pbm_bad
    ld a,(recon_slab_desc+6)
    or a
    jr nz,recon_pbm_bad
    ld hl,(recon_slab_desc)
    ld a,(recon_slab_desc+2)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    call recon_pool_abs_from_rel
    jr c,recon_pbm_bad
    ld de,0x8000
    ld bc,(recon_slab_desc+8)
    call READ_AT
    ret z
    scf
    ret

recon_copy_pool_slice:
    ld hl,(recon_length)
    ld a,h
    or l
    ret z
    call recon_map_scratch
    ld hl,(recon_block_desc+2)
    ld de,(recon_record+8)
    add hl,de
    jr c,recon_pbm_bad
    ld de,(recon_source_skip)
    add hl,de
    jr c,recon_pbm_bad
    ld de,0x8000
    add hl,de
    push hl
    ld hl,(recon_dest)
    ld de,(recon_source_skip)
    add hl,de
    ld de,0x4000
    add hl,de
    ex de,hl
    pop hl
    ld bc,(recon_length)
    ldir
    or a
    ret

; ---------------------------------------------------------------------------
; RMP1
; ---------------------------------------------------------------------------
recon_apply_rmp1:
    call recon_reset_caches
    call recon_map_map
    ld hl,0x8000
    ld de,recon_header
    ld bc,16
    ldir
    ld hl,recon_header
    ld a,(hl)
    cp 'R'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp 'M'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp 'P'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,recon_rmp_bad
    ld hl,(recon_header+4)
    ld de,16
    or a
    sbc hl,de
    jr nz,recon_rmp_bad
    ld hl,(recon_header+8)
    ld de,16
    or a
    sbc hl,de
    jr nz,recon_rmp_bad
    ld hl,(recon_header+0x0A)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_header+0x0C)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_header+0x0E)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_header+6)
    ld (recon_records_left),hl
    ; table_end = 16 + count*16.
    add hl,hl
    jr c,recon_rmp_bad
    add hl,hl
    jr c,recon_rmp_bad
    add hl,hl
    jr c,recon_rmp_bad
    add hl,hl
    jr c,recon_rmp_bad
    ld de,16
    add hl,de
    jr c,recon_rmp_bad
    ld (recon_table_end),hl
    ld de,(PAGE_ENTRY+16)
    or a
    sbc hl,de
    jr c,recon_rmp_table_ok
    jr z,recon_rmp_table_ok
    jr recon_rmp_bad
recon_rmp_table_ok:
    ld hl,0x8010
    ld (recon_map_ptr),hl
    ld hl,0
    ld (recon_previous_end),hl
recon_rmp_loop:
    ld hl,(recon_records_left)
    ld a,h
    or l
    jr z,recon_rmp_done
    call recon_map_map
    ld hl,(recon_map_ptr)
    ld de,recon_record
    ld bc,16
    ldir
    ld (recon_map_ptr),hl
    call recon_validate_rmp_record
    jr c,recon_rmp_bad
    ld a,(recon_record+4)
    or a
    jr z,recon_rmp_resource
    cp 1
    jr z,recon_rmp_inline
    cp 2
    jr z,recon_rmp_fill
    jr recon_rmp_bad
recon_rmp_inline:
    call recon_rmp_copy_inline
    jr c,recon_rmp_bad
    jr recon_rmp_next
recon_rmp_fill:
    call recon_rmp_apply_fill
    jr c,recon_rmp_bad
    jr recon_rmp_next
recon_rmp_resource:
    call recon_rmp_copy_resource
    jr c,recon_rmp_bad
recon_rmp_next:
    ld hl,(recon_records_left)
    dec hl
    ld (recon_records_left),hl
    jr recon_rmp_loop
recon_rmp_done:
    or a
    ret
recon_rmp_bad:
    scf
    ret

recon_validate_rmp_record:
    ld a,(recon_record+5)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_record+0x0C)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_record+0x0E)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_record)
    ld (recon_dest),hl
    ld de,(recon_previous_end)
    or a
    sbc hl,de
    jr c,recon_rmp_bad
    ld hl,(recon_record+2)
    ld a,h
    or l
    jr z,recon_rmp_bad
    ld (recon_length),hl
    ld hl,(recon_dest)
    ld de,(recon_length)
    add hl,de
    jr c,recon_rmp_bad
    ld (recon_record_end),hl
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_rmp_bad
    ld hl,(recon_record_end)
    ld (recon_previous_end),hl
    call recon_clip_record
    ret

recon_rmp_copy_inline:
    ld hl,(recon_record+6)
    inc hl
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld a,(recon_record+0x0B)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_record+8)
    ld a,(recon_record+0x0A)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    ; Inline data must begin after the record table and remain in the map.
    ld hl,(recon_rel24)
    ld a,(recon_rel24+2)
    or a
    jr nz,recon_rmp_bad
    ld de,(recon_table_end)
    or a
    sbc hl,de
    jr c,recon_rmp_bad
    ld de,(recon_record+2)
    add hl,de
    jr c,recon_rmp_bad
    ld de,(PAGE_ENTRY+16)
    or a
    sbc hl,de
    jr c,recon_inline_range_ok
    jr z,recon_inline_range_ok
    jr recon_rmp_bad
recon_inline_range_ok:
    ld hl,(recon_length)
    ld a,h
    or l
    ret z
    call recon_map_map
    ld hl,(recon_rel24)
    ld de,(recon_source_skip)
    add hl,de
    jr c,recon_rmp_bad
    ld de,0x8000
    add hl,de
    push hl
    call recon_destination_address
    ex de,hl
    pop hl
    ld bc,(recon_length)
    ldir
    or a
    ret

recon_rmp_apply_fill:
    ld hl,(recon_record+6)
    inc hl
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld a,(recon_record+9)
    ld h,a
    ld a,(recon_record+0x0A)
    or h
    ld h,a
    ld a,(recon_record+0x0B)
    or h
    jr nz,recon_rmp_bad
    ld hl,(recon_length)
    ld a,h
    or l
    ret z
    call recon_destination_address
    ld bc,(recon_length)
    ld a,(recon_record+8)
    jp recon_fill_zero

recon_rmp_copy_resource:
    ld hl,(recon_record+6)
    call recon_load_resource
    jr c,recon_rmp_bad
    ld a,(RESOURCE_ENTRY+5)
    or a
    jr nz,recon_rmp_bad
    ld a,(RESOURCE_ENTRY+4)
    and 0x04
    jr z,recon_rmp_bad
    ld a,(RESOURCE_ENTRY+4)
    and 0xF8
    jr nz,recon_rmp_bad
    ld a,(RESOURCE_ENTRY+6)
    cp 3
    jr nc,recon_rmp_bad
    ld a,(RESOURCE_ENTRY+7)
    or a
    jr nz,recon_rmp_bad
    ld hl,RESOURCE_ENTRY
    ld de,recon_source_resource
    ld bc,32
    ldir
    ; Original logical source range must fit the resource.
    ld a,(recon_record+0x0B)
    or a
    jr nz,recon_rmp_bad
    ld hl,recon_record+8
    ld de,recon_source_resource+16
    call recon_range_u24_u16
    jr c,recon_rmp_bad
    ; Add dynamic clipping to the source offset.
    ld hl,(recon_record+8)
    ld a,(recon_record+0x0A)
    ld (recon_source_offset),hl
    ld (recon_source_offset+2),a
    ld de,(recon_source_skip)
    call recon_add_u16_to_source
    jr c,recon_rmp_bad
    ld hl,(recon_length)
    ld a,h
    or l
    ret z
    ld a,(recon_source_resource+6)
    or a
    jr z,recon_rmp_resource_raw
    cp 1
    jr z,recon_rmp_resource_zx0
    jp recon_rmp_resource_kzb1
recon_rmp_resource_raw:
    ld hl,(recon_source_offset)
    ld a,(recon_source_offset+2)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    call recon_source_abs_from_rel
    jr c,recon_rmp_bad
    push af
    push hl
    call recon_destination_address
    ex de,hl
    pop hl
    pop af
    ld bc,(recon_length)
    call READ_AT
    ret z
    scf
    ret

recon_rmp_resource_zx0:
    ; Whole-object ZX0 is bounded to one 16 KiB scratch page.
    ld a,(recon_source_resource+18)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_source_resource+16)
    ld a,h
    or l
    jr z,recon_rmp_bad
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_rmp_bad
    ld a,(recon_source_resource+14)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_record+6)
    ld de,(recon_cached_resource)
    or a
    sbc hl,de
    jr z,recon_rmp_zx0_cached
    ld hl,(recon_record+6)
    ld (recon_cached_resource),hl
    call recon_map_scratch
    ld hl,(recon_source_resource+8)
    ld a,(recon_source_resource+10)
    ld de,(recon_source_resource+12)
    ld b,d
    ld c,e
    call STREAM_BEGIN
    ret c
    xor a
    ld (ZX_MODE),a
    ld hl,0x8000
    ld (LINEAR_BASE),hl
    ld hl,(recon_source_resource+16)
    xor a
    call ZX_SET_OUTPUT_SIZE
    call ZX_DECODE_STREAM
    ret c
recon_rmp_zx0_cached:
    call recon_map_scratch
    ld hl,(recon_source_offset)
    ld a,(recon_source_offset+2)
    or a
    jr nz,recon_rmp_bad
    ld de,0x8000
    add hl,de
    push hl
    call recon_destination_address
    ex de,hl
    pop hl
    ld bc,(recon_length)
    ldir
    or a
    ret

; KZB1 page source: find and decode only blocks intersecting the requested
; range. The range may cross any number of independently compressed blocks.
recon_rmp_resource_kzb1:
    ld hl,(recon_source_resource+8)
    ld a,(recon_source_resource+10)
    ld de,recon_kzb_header
    ld bc,16
    call READ_AT
    jr nz,recon_rmp_bad
    ld hl,recon_kzb_header
    ld a,(hl)
    cp 'K'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp 'Z'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp 'B'
    jr nz,recon_rmp_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_header+4)
    ld de,16
    or a
    sbc hl,de
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_header+6)
    ld a,h
    or l
    jr z,recon_rmp_bad
    ld (recon_kzb_blocks_left),hl
    ld a,(recon_kzb_header+0x0B)
    or a
    jr nz,recon_rmp_bad
    ld hl,recon_kzb_header+8
    ld de,recon_source_resource+16
    call recon_compare_u24
    jr nz,recon_rmp_bad
    ld a,(recon_kzb_header+0x0F)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_header+0x0C)
    ld a,(recon_kzb_header+0x0E)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    call recon_source_abs_from_rel
    jr c,recon_rmp_bad
    ld (recon_kzb_desc_abs),hl
    ld (recon_kzb_desc_abs+2),a
    ld hl,(recon_source_offset)
    ld a,(recon_source_offset+2)
    ld (recon_skip24),hl
    ld (recon_skip24+2),a
    ld hl,(recon_length)
    ld (recon_copy_left),hl
recon_kzb_loop:
    ld hl,(recon_copy_left)
    ld a,h
    or l
    jr z,recon_kzb_done
    ld hl,(recon_kzb_blocks_left)
    ld a,h
    or l
    jr z,recon_rmp_bad
    ld hl,(recon_kzb_desc_abs)
    ld a,(recon_kzb_desc_abs+2)
    ld de,recon_kzb_desc
    ld bc,16
    call READ_AT
    jr nz,recon_rmp_bad
    call recon_advance_kzb_desc
    ld a,(recon_kzb_desc+0x0B)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_desc+0x0A)
    ld a,h
    or l
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_desc+8)
    ld a,h
    or l
    jr z,recon_rmp_bad
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,recon_rmp_bad
    ; Skip complete blocks until source offset enters this one.
    ld a,(recon_skip24+2)
    or a
    jr nz,recon_kzb_skip_block
    ld hl,(recon_skip24)
    ld de,(recon_kzb_desc+8)
    or a
    sbc hl,de
    jr c,recon_kzb_intersects
    ld (recon_skip24),hl
    jr recon_kzb_next
recon_kzb_skip_block:
    ld hl,(recon_skip24)
    ld de,(recon_kzb_desc+8)
    or a
    sbc hl,de
    ld (recon_skip24),hl
    ld a,(recon_skip24+2)
    sbc a,0
    ld (recon_skip24+2),a
    jr recon_kzb_next
recon_kzb_intersects:
    ; amount = min(copy_left, block_raw - skip).
    ld hl,(recon_kzb_desc+8)
    ld de,(recon_skip24)
    or a
    sbc hl,de
    ld de,(recon_copy_left)
    push hl
    or a
    sbc hl,de
    pop hl
    jr c,recon_kzb_amount_ready
    ex de,hl
recon_kzb_amount_ready:
    ld (recon_chunk),hl
    call recon_decode_kzb_block
    jr c,recon_rmp_bad
    call recon_map_scratch
    ld hl,(recon_skip24)
    ld de,0x8000
    add hl,de
    push hl
    call recon_destination_address_progress
    ex de,hl
    pop hl
    ld bc,(recon_chunk)
    ldir
    ld hl,(recon_copy_left)
    ld de,(recon_chunk)
    or a
    sbc hl,de
    ld (recon_copy_left),hl
    ld hl,0
    ld (recon_skip24),hl
    xor a
    ld (recon_skip24+2),a
recon_kzb_next:
    ld hl,(recon_kzb_blocks_left)
    dec hl
    ld (recon_kzb_blocks_left),hl
    jr recon_kzb_loop
recon_kzb_done:
    or a
    ret

recon_decode_kzb_block:
    call recon_map_scratch
    ld a,(recon_kzb_desc+6)
    or a
    jr nz,recon_rmp_bad
    ld hl,(recon_kzb_desc)
    ld a,(recon_kzb_desc+2)
    ld (recon_rel24),hl
    ld (recon_rel24+2),a
    call recon_source_abs_from_rel
    jr c,recon_rmp_bad
    ld de,(recon_kzb_desc+4)
    ld b,d
    ld c,e
    call STREAM_BEGIN
    ret c
    xor a
    ld (ZX_MODE),a
    ld hl,0x8000
    ld (LINEAR_BASE),hl
    ld hl,(recon_kzb_desc+8)
    xor a
    call ZX_SET_OUTPUT_SIZE
    call ZX_DECODE_STREAM
    ret

recon_advance_kzb_desc:
    ld hl,(recon_kzb_desc_abs)
    ld de,16
    add hl,de
    ld (recon_kzb_desc_abs),hl
    ret nc
    ld a,(recon_kzb_desc_abs+2)
    inc a
    ld (recon_kzb_desc_abs+2),a
    ret

; ---------------------------------------------------------------------------
; Shared helpers
; ---------------------------------------------------------------------------
recon_load_resource:
    ; HL resource index.
    push hl
    ld de,(KSP_HEADER+0x2C)
    or a
    sbc hl,de
    pop hl
    jr nc,recon_resource_bad
    ld de,32
    call MUL16X16_24
    ld c,a
    ld de,(KSP_HEADER+0x28)
    add hl,de
    ld a,(KSP_HEADER+0x2A)
    adc a,c
    ld de,RESOURCE_ENTRY
    ld bc,32
    call READ_AT
    jr nz,recon_resource_bad
    ld a,(RESOURCE_ENTRY+11)
    or a
    jr nz,recon_resource_bad
    ld a,(RESOURCE_ENTRY+15)
    or a
    jr nz,recon_resource_bad
    ld a,(RESOURCE_ENTRY+19)
    or a
    jr nz,recon_resource_bad
    or a
    ret
recon_resource_bad:
    scf
    ret

; Clip destination and source for dynamic replace_start. Original record
; fields remain intact for structural validation.
recon_clip_record:
    ld hl,0
    ld (recon_source_skip),hl
    ld a,(DYNAMIC_INSTALL_ACTIVE)
    or a
    ret z
    ld hl,(recon_dest)
    ld de,0x4000
    add hl,de
    ld de,(ENGINE_ENTRY+24)
    or a
    sbc hl,de
    jr nc,recon_clip_after_start
    ; Record starts before replace_start. If it ends there too, skip it.
    ld hl,(recon_record_end)
    ld de,0x4000
    add hl,de
    ld de,(ENGINE_ENTRY+24)
    or a
    sbc hl,de
    jr c,recon_clip_all
    jr z,recon_clip_all
    ; skip = replace_start - absolute destination.
    ld hl,(ENGINE_ENTRY+24)
    ld de,0x4000
    or a
    sbc hl,de
    ld de,(recon_dest)
    or a
    sbc hl,de
    ld (recon_source_skip),hl
    ld de,(recon_length)
    ex de,hl
    or a
    sbc hl,de
    ld (recon_length),hl
recon_clip_after_start:
    or a
    ret
recon_clip_all:
    ld hl,0
    ld (recon_length),hl
    or a
    ret

recon_destination_address:
    ld hl,(recon_dest)
    ld de,(recon_source_skip)
    add hl,de
    ld de,0x4000
    add hl,de
    ret

; Destination after bytes already copied from the current clipped record.
recon_destination_address_progress:
    call recon_destination_address
    ld de,(recon_length)
    push hl
    ld hl,(recon_copy_left)
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    pop hl
    add hl,de
    ret

; Compare unsigned 24-bit [HL] with [DE]. Flags as subtraction left-right.
recon_compare_u24:
    push hl
    push de
    inc hl
    inc hl
    inc de
    inc de
    ld a,(hl)
    ld b,a
    ld a,(de)
    ld c,a
    ld a,b
    cp c
    jr nz,recon_compare_done
    pop de
    pop hl
    push hl
    push de
    inc hl
    inc de
    ld a,(hl)
    ld b,a
    ld a,(de)
    ld c,a
    ld a,b
    cp c
    jr nz,recon_compare_done
    pop de
    pop hl
    push hl
    push de
    ld a,(hl)
    ld b,a
    ld a,(de)
    ld c,a
    ld a,b
    cp c
recon_compare_done:
    pop de
    pop hl
    ret

; Validate [HL] source offset + u16 at record+2 <= 24-bit [DE].
recon_range_u24_u16:
    push hl
    ld a,(hl)
    ld (recon_tmp24),a
    inc hl
    ld a,(hl)
    ld (recon_tmp24+1),a
    inc hl
    ld a,(hl)
    ld (recon_tmp24+2),a
    pop hl
    ld hl,(recon_tmp24)
    ld bc,(recon_record+2)
    add hl,bc
    ld (recon_tmp24),hl
    ld a,(recon_tmp24+2)
    adc a,0
    ld (recon_tmp24+2),a
    ld hl,recon_tmp24
    call recon_compare_u24
    jr c,recon_range_ok
    jr z,recon_range_ok
    scf
    ret
recon_range_ok:
    or a
    ret

recon_add_u16_to_source:
    ld hl,(recon_source_offset)
    add hl,de
    ld (recon_source_offset),hl
    ret nc
    ld a,(recon_source_offset+2)
    inc a
    ld (recon_source_offset+2),a
    ret nz
    scf
    ret

; rel24 <<= 3.
recon_shift_rel24_3:
    ld b,3
recon_shift_rel24_loop:
    ld hl,(recon_rel24)
    add hl,hl
    ld (recon_rel24),hl
    ld a,(recon_rel24+2)
    adc a,a
    ld (recon_rel24+2),a
    jr c,recon_shift_rel24_bad
    djnz recon_shift_rel24_loop
    or a
    ret
recon_shift_rel24_bad:
    scf
    ret

; Add A:HL to rel24.
recon_add_to_rel24:
    ld de,(recon_rel24)
    add hl,de
    ld (recon_rel24),hl
    ld e,a
    ld a,(recon_rel24+2)
    adc a,e
    ld (recon_rel24+2),a
    ret c
    or a
    ret

recon_pool_abs_from_rel:
    ld hl,(recon_rel24)
    ld de,(recon_pool_resource+8)
    add hl,de
    ld a,(recon_rel24+2)
    ld e,a
    ld a,(recon_pool_resource+10)
    adc a,e
    ret

recon_source_abs_from_rel:
    ld hl,(recon_rel24)
    ld de,(recon_source_resource+8)
    add hl,de
    ld a,(recon_rel24+2)
    ld e,a
    ld a,(recon_source_resource+10)
    adc a,e
    ret

; ---------------------------------------------------------------------------
; Retired HPOL next-cold-slab cache ABI
; ---------------------------------------------------------------------------
; v0.22.6 leaves these two entry points as harmless stubs so older local
; instrumentation can still call the overlay jump table. Measurements showed
; that synchronous next-slab prefetch merely moved blocking I/O earlier and
; did not improve normal sequential track changes.
recon_cold_stream_begin:
    scf
    ret

recon_cold_prefetch_next:
    or a
    ret

; ---------------------------------------------------------------------------
; Specialized ZX0 mode dispatch
; ---------------------------------------------------------------------------
; The generic decoder chooses RAM, VRAM or mapper handlers once per object.
; Removing two mode tests from every literal and match byte is especially
; valuable for the large HPOL hot and warm pools.
recon_zx_select:
    ld a,(ZX_MODE)
    or a
    jr z,recon_zx_linear
    cp 1
    jr z,recon_zx_warm
    ld hl,ZX_WRITE_HOT
    ld de,ZX_READ_HOT
    jr recon_zx_patch
recon_zx_warm:
    ld hl,ZX_WRITE_WARM
    ld de,ZX_READ_WARM
    jr recon_zx_patch
recon_zx_linear:
    ld hl,ZX_WRITE_LINEAR
    ld de,ZX_READ_LINEAR
recon_zx_patch:
    ld (ZX_WRITE_DISPATCH+1),hl
    ex de,hl
    ld (ZX_READ_DISPATCH+1),hl
    ret

; ---------------------------------------------------------------------------
; Selected-track packed-page preload cache (KSP 1.03 optimization)
; ---------------------------------------------------------------------------
; The optimizer used by large KSP 1.03 packs may place every packed page of a
; physical track in one contiguous file run and every track's pages in one
; contiguous page-table run.  This routine validates that property rather than
; assuming it.  When valid, the packed bytes are copied into mapper segments
; before INIT.  READ_AT then serves the whole run from mapper RAM, so dynamic
; page callbacks never touch the disk while music is playing.
;
; Unsupported/non-contiguous layouts simply keep the normal disk-backed path.
; Once a valid range has been identified, allocation or I/O failure is fatal:
; silently falling back would reintroduce periodic floppy reads.

RECON_TRACK_CACHE_MAX equ 12
RECON_TRACK_PAGE_MAX  equ 32
RECON_TRACK_CHUNK     equ 0x0400

recon_preload_track:
    call RESTORE_PROCESS_PAGES
    call recon_track_cache_release

    ; The optimization is intended for minor version 3 and later dynamic
    ; engines.  Older packages retain their proven v0.22.6 behavior.
    ld a,(KSP_HEADER+6)
    cp 3
    jr c,recon_preload_not_applicable
    ld a,(ENGINE_ENTRY)
    and 1
    jr z,recon_preload_not_applicable

    ld hl,(CURRENT_PAGE)
    ld (recon_track_start_page),hl
    ld de,(ENGINE_ENTRY+26)      ; engine first_page
    or a
    sbc hl,de
    jr c,recon_preload_not_applicable

    ; Default end is the owning engine's exclusive page limit.
    ld hl,(ENGINE_ENTRY+26)
    ld de,(ENGINE_ENTRY+28)      ; engine page_count
    add hl,de
    jr c,recon_preload_not_applicable
    ld (recon_track_end_page),hl

    ; If the next physical track belongs to the same engine and starts later,
    ; its first page is the exclusive end of this track's page run.
    ld hl,(IMPLEMENTATION_TRACK)
    inc hl
    push hl
    ld de,(KSP_HEADER+0x24)
    or a
    sbc hl,de
    pop hl
    jr nc,recon_preload_end_ready
    ld de,(KSP_HEADER+0x26)
    call MUL16X16_24
    ld c,a
    ld de,(KSP_HEADER+0x20)
    add hl,de
    ld a,(KSP_HEADER+0x22)
    adc a,c
    ld de,IO_BUFFER
    ld bc,32
    call READ_AT
    jr nz,recon_preload_io_bad
    ld hl,(IO_BUFFER)
    ld (recon_track_candidate_end),hl
    ld de,(CURRENT_PAGE)
    or a
    sbc hl,de
    jr c,recon_preload_end_ready
    jr z,recon_preload_end_ready
    ld hl,(recon_track_candidate_end)
    push hl
    ld de,(recon_track_end_page)
    or a
    sbc hl,de
    pop hl
    jr c,recon_preload_candidate_in_range
    jr z,recon_preload_candidate_in_range
    jr recon_preload_end_ready
recon_preload_candidate_in_range:
    push hl
    call recon_track_read_page_entry
    pop hl
    jr c,recon_preload_io_bad
    ld de,(IO_BUFFER+32)
    push hl
    ld hl,(CURRENT_ENGINE)
    or a
    sbc hl,de
    pop hl
    jr nz,recon_preload_end_ready
    ld (recon_track_end_page),hl

recon_preload_end_ready:
    ld hl,(recon_track_start_page)
    ld de,(recon_track_end_page)
    or a
    sbc hl,de
    jr nc,recon_preload_not_applicable
    ; Cache a bounded per-track page table in the overlay itself.
    ld hl,(recon_track_end_page)
    ld de,(recon_track_start_page)
    or a
    sbc hl,de
    ld a,h
    or a
    jr nz,recon_preload_not_applicable
    ld a,l
    or a
    jr z,recon_preload_not_applicable
    cp RECON_TRACK_PAGE_MAX+1
    jr nc,recon_preload_not_applicable
    ld (recon_track_page_count),a
    ld hl,recon_track_page_entries
    ld (recon_track_page_table_ptr),hl
    ld hl,(recon_track_start_page)
    ld (recon_track_scan_page),hl
    xor a
    ld (recon_track_have_base),a

recon_preload_scan_loop:
    ld hl,(recon_track_scan_page)
    ld de,(recon_track_end_page)
    or a
    sbc hl,de
    jr z,recon_preload_scan_done
    jr nc,recon_preload_not_applicable
    ld hl,(recon_track_scan_page)
    call recon_track_read_page_entry
    jr c,recon_preload_io_bad

    ; Every page in the run must belong to the selected engine and use a
    ; normal page payload with a supported 24-bit offset / 16-bit packed size.
    ld hl,(IO_BUFFER+32)
    ld de,(CURRENT_ENGINE)
    or a
    sbc hl,de
    jr nz,recon_preload_not_applicable
    ld a,(IO_BUFFER+34)          ; encoding
    cp 5
    jr nc,recon_preload_not_applicable
    ld a,(IO_BUFFER+43)          ; payload offset high byte 3
    or a
    jr nz,recon_preload_not_applicable
    ld a,(IO_BUFFER+46)          ; packed size high word
    or a
    jr nz,recon_preload_not_applicable
    ld a,(IO_BUFFER+47)
    or a
    jr nz,recon_preload_not_applicable
    ld hl,(IO_BUFFER+44)
    ld a,h
    or l
    jr z,recon_preload_not_applicable

    ld hl,IO_BUFFER+32
    ld de,(recon_track_page_table_ptr)
    ld bc,24
    ldir
    ld (recon_track_page_table_ptr),de

    ld a,(recon_track_have_base)
    or a
    jr nz,recon_preload_check_contiguous
    ld hl,(IO_BUFFER+40)
    ld (recon_track_cache_base),hl
    ld (recon_track_expected),hl
    ld a,(IO_BUFFER+42)
    ld (recon_track_cache_base+2),a
    ld (recon_track_expected+2),a
    ld a,1
    ld (recon_track_have_base),a
    jr recon_preload_add_packed

recon_preload_check_contiguous:
    ld hl,(IO_BUFFER+40)
    ld de,(recon_track_expected)
    or a
    sbc hl,de
    jr nz,recon_preload_not_applicable
    ld a,(IO_BUFFER+42)
    ld b,a
    ld a,(recon_track_expected+2)
    cp b
    jr nz,recon_preload_not_applicable

recon_preload_add_packed:
    ld hl,(recon_track_expected)
    ld de,(IO_BUFFER+44)
    add hl,de
    ld (recon_track_expected),hl
    ld a,(recon_track_expected+2)
    adc a,0
    ld (recon_track_expected+2),a
    ld hl,(recon_track_scan_page)
    inc hl
    ld (recon_track_scan_page),hl
    jr recon_preload_scan_loop

recon_preload_scan_done:
    ld a,(recon_track_have_base)
    or a
    jr z,recon_preload_not_applicable

    ; size = expected_end - cache_base
    ld hl,(recon_track_expected)
    ld de,(recon_track_cache_base)
    or a
    sbc hl,de
    ld (recon_track_cache_size),hl
    ld a,(recon_track_expected+2)
    ld b,a
    ld a,(recon_track_cache_base+2)
    ld c,a
    ld a,b
    sbc a,c
    jr c,recon_preload_not_applicable
    ld (recon_track_cache_size+2),a
    ld b,a
    ld a,h
    or l
    or b
    jr z,recon_preload_not_applicable

    ; Count 16 KiB mapper segments needed by the packed run.
    ld hl,(recon_track_cache_size)
    ld (recon_track_remaining),hl
    ld a,(recon_track_cache_size+2)
    ld (recon_track_remaining+2),a
    xor a
    ld (recon_track_cache_count),a
recon_preload_count_loop:
    ld hl,(recon_track_remaining)
    ld a,(recon_track_remaining+2)
    or h
    or l
    jr z,recon_preload_allocate
    ld a,(recon_track_cache_count)
    cp RECON_TRACK_CACHE_MAX
    jr nc,recon_preload_not_applicable
    inc a
    ld (recon_track_cache_count),a
    ld a,(recon_track_remaining+2)
    or a
    jr nz,recon_preload_count_sub_full
    ld hl,(recon_track_remaining)
    ld de,0x4000
    or a
    sbc hl,de
    jr c,recon_preload_count_zero
    ld (recon_track_remaining),hl
    jr recon_preload_count_loop
recon_preload_count_sub_full:
    ld hl,(recon_track_remaining)
    ld de,0x4000
    or a
    sbc hl,de
    ld (recon_track_remaining),hl
    ld a,(recon_track_remaining+2)
    sbc a,0
    ld (recon_track_remaining+2),a
    jr recon_preload_count_loop
recon_preload_count_zero:
    xor a
    ld (recon_track_remaining),a
    ld (recon_track_remaining+1),a
    ld (recon_track_remaining+2),a
    jr recon_preload_count_loop

recon_preload_allocate:
    xor a
    ld (recon_track_cache_allocated),a
    ld a,(recon_track_cache_count)
    ld b,a
    ld hl,recon_track_cache_segments
recon_preload_allocate_loop:
    ld a,b
    or a
    jr z,recon_preload_copy_begin
    push hl
    push bc
    call MAPPER_ALLOC_USER_PRIMARY
    pop bc
    pop hl
    jr c,recon_preload_memory_bad
    ld (hl),a
    inc hl
    ld a,(recon_track_cache_allocated)
    inc a
    ld (recon_track_cache_allocated),a
    djnz recon_preload_allocate_loop

recon_preload_copy_begin:
    ld hl,(recon_track_cache_base)
    ld (recon_track_file_off),hl
    ld a,(recon_track_cache_base+2)
    ld (recon_track_file_off+2),a
    ld hl,(recon_track_cache_size)
    ld (recon_track_remaining),hl
    ld a,(recon_track_cache_size+2)
    ld (recon_track_remaining+2),a
    xor a
    ld (recon_track_segment_index),a
    ld (recon_cache_valid),a       ; direct reads invalidate 1 KiB window

recon_preload_segment_loop:
    ld hl,(recon_track_remaining)
    ld a,(recon_track_remaining+2)
    or h
    or l
    jr z,recon_preload_copy_done
    ld a,(recon_track_segment_index)
    ld e,a
    ld d,0
    ld hl,recon_track_cache_segments
    add hl,de
    ld a,(hl)
    call MAP_P2

    ; Segment byte count is min(remaining, 16 KiB).
    ld a,(recon_track_remaining+2)
    or a
    jr nz,recon_preload_segment_full
    ld hl,(recon_track_remaining)
    ld de,0x4000
    or a
    sbc hl,de
    jr nc,recon_preload_segment_full
    add hl,de
    jr recon_preload_segment_count_ready
recon_preload_segment_full:
    ld hl,0x4000
recon_preload_segment_count_ready:
    ld (recon_track_segment_left),hl
    ld hl,0x8000
    ld (recon_track_segment_dest),hl

recon_preload_chunk_loop:
    ld hl,(recon_track_segment_left)
    ld a,h
    or l
    jr z,recon_preload_next_segment
    ld de,RECON_TRACK_CHUNK
    or a
    sbc hl,de
    jr nc,recon_preload_chunk_full
    add hl,de
    jr recon_preload_chunk_ready
recon_preload_chunk_full:
    ld hl,RECON_TRACK_CHUNK
recon_preload_chunk_ready:
    ld (recon_track_chunk_count),hl
    ld hl,1
    ld (FILE_FCB+14),hl
    ld hl,(recon_track_file_off)
    ld (FILE_FCB+33),hl
    ld a,(recon_track_file_off+2)
    ld (FILE_FCB+35),a
    xor a
    ld (FILE_FCB+36),a
    ld de,(recon_track_segment_dest)
    ld bc,(recon_track_chunk_count)
    call FCB_READ_CURRENT
    jr nz,recon_preload_io_bad_release

    ld hl,(recon_track_file_off)
    ld de,(recon_track_chunk_count)
    add hl,de
    ld (recon_track_file_off),hl
    ld a,(recon_track_file_off+2)
    adc a,0
    ld (recon_track_file_off+2),a
    ld hl,(recon_track_segment_dest)
    ld de,(recon_track_chunk_count)
    add hl,de
    ld (recon_track_segment_dest),hl
    ld hl,(recon_track_segment_left)
    ld de,(recon_track_chunk_count)
    or a
    sbc hl,de
    ld (recon_track_segment_left),hl
    ld hl,(recon_track_remaining)
    ld de,(recon_track_chunk_count)
    or a
    sbc hl,de
    ld (recon_track_remaining),hl
    ld a,(recon_track_remaining+2)
    sbc a,0
    ld (recon_track_remaining+2),a
    jr recon_preload_chunk_loop

recon_preload_next_segment:
    ld a,(recon_track_segment_index)
    inc a
    ld (recon_track_segment_index),a
    jr recon_preload_segment_loop

recon_preload_copy_done:
    call RESTORE_PROCESS_PAGES
    ld a,1
    ld (recon_track_cache_valid),a
    ld a,(MAPPER_POOL_COUNT)
    ld (KSPOS_FREE_SEGMENTS),a
    call recon_direct_preload
    ret

recon_preload_memory_bad:
    call recon_track_cache_release
    call RESTORE_PROCESS_PAGES
    scf
    ret
recon_preload_io_bad_release:
    call recon_track_cache_release
recon_preload_io_bad:
    call RESTORE_PROCESS_PAGES
    scf
    ret
recon_preload_not_applicable:
    call RESTORE_PROCESS_PAGES
    call recon_direct_preload
    ret

; KSP 1.06 direct materialized pages may be outside the ordinary physical-track
; page run. For small MSX-safe packs the complete KSP is already cached in
; VRAM, so preload each consecutive direct engine page into one mapper segment
; before INIT. No disk/ZX0/full-page copy is then needed during PLAY.
recon_direct_preload:
    ; No extra mapper allocation is required.  Direct pages that conform to
    ; the MSX profile are already part of the selected track's contiguous raw
    ; payload run and are mapped directly from recon_track_cache_segments.
    ; If that preload is unavailable, the runtime keeps the correctness
    ; fallback and materializes the page normally.
    xor a
    ld (recon_direct_count),a
    or a
    ret

; HL global page index. Read its 24-byte page entry into IO_BUFFER+32.
recon_track_read_page_entry:
    ld de,(KSP_HEADER+0x1E)
    call MUL16X16_24
    ld c,a
    ld de,(KSP_HEADER+0x18)
    add hl,de
    ld a,(KSP_HEADER+0x1A)
    adc a,c
    ld de,IO_BUFFER+32
    ld bc,24
    call READ_AT
    jr nz,recon_track_read_page_bad
    or a
    ret
recon_track_read_page_bad:
    scf
    ret

recon_track_cache_get_page_entry:
    ld a,(recon_track_cache_valid)
    or a
    jr z,recon_track_page_miss
    ld hl,(DYNAMIC_PAGE)
    ld de,(ENGINE_ENTRY+26)
    add hl,de
    ld de,(recon_track_start_page)
    or a
    sbc hl,de
    jr c,recon_track_page_miss
    ld a,h
    or a
    jr nz,recon_track_page_miss
    ld b,a
    ld a,(recon_track_page_count)
    cp l
    jr c,recon_track_page_miss
    jr z,recon_track_page_miss
    ; offset = local index * 24 = *16 + *8
    ld h,0
    add hl,hl
    add hl,hl
    add hl,hl
    push hl
    add hl,hl
    pop de
    add hl,de
    ld de,recon_track_page_entries
    add hl,de
    ld de,PAGE_ENTRY
    ld bc,24
    ldir
    xor a
    ret
recon_track_page_miss:
    ld a,1
    or a
    ret

recon_track_cache_release:
    ld a,(recon_track_cache_allocated)
    ld b,a
    ld hl,recon_track_cache_segments
recon_track_cache_release_loop:
    ld a,b
    or a
    jr z,recon_track_cache_release_done
    ld a,(hl)
    inc hl
    push hl
    push bc
    call MAPPER_FREE_PRIMARY
    pop bc
    pop hl
    djnz recon_track_cache_release_loop
recon_track_cache_release_done:
    xor a
    ld (recon_track_cache_valid),a
    ld (recon_track_cache_allocated),a
    ld (recon_track_cache_count),a
    ld (recon_direct_count),a
    ld a,(MAPPER_POOL_COUNT)
    ld (KSPOS_FREE_SEGMENTS),a
    ret

; Return Z after satisfying the entire READ_AT request from mapper RAM.
; Return NZ without changing caller state when the request is outside the
; selected-track cache.
recon_track_cache_try_read:
    ld (recon_track_read_dest),de
    ld (recon_track_read_left),bc
    ld a,(recon_track_cache_valid)
    or a
    jr z,recon_track_cache_miss
    ld hl,(TMP_OFFSET_LO)
    ld de,(recon_track_cache_base)
    or a
    sbc hl,de
    ld (recon_track_diff),hl
    ld a,(TMP_OFFSET_HI)
    ld b,a
    ld a,(recon_track_cache_base+2)
    ld c,a
    ld a,b
    sbc a,c
    jr c,recon_track_cache_miss
    ld (recon_track_diff+2),a

    ; Require diff + request_count <= cache_size.
    ld bc,(recon_track_read_left)
    ld hl,(recon_track_diff)
    add hl,bc
    ld (recon_track_request_end),hl
    ld a,(recon_track_diff+2)
    adc a,0
    ld (recon_track_request_end+2),a
    ld b,a
    ld a,(recon_track_cache_size+2)
    cp b
    jr c,recon_track_cache_miss
    jr nz,recon_track_cache_range_ok
    ld hl,(recon_track_cache_size)
    ld de,(recon_track_request_end)
    or a
    sbc hl,de
    jr c,recon_track_cache_miss

recon_track_cache_range_ok:
    ld a,(MAPPED_P1)
    ld (recon_track_saved_p1),a
    ld a,(MAPPED_P2)
    ld (recon_track_saved_p2),a

recon_track_cache_copy_loop:
    ld hl,(recon_track_read_left)
    ld a,h
    or l
    jr z,recon_track_cache_copy_done

    ; Mapper segment index = 24-bit offset >> 14.
    ld a,(recon_track_diff+2)
    add a,a
    add a,a
    ld b,a
    ld a,(recon_track_diff+1)
    rlca
    rlca
    and 3
    or b
    ld (recon_track_segment_index),a
    ld b,a
    ld a,(recon_track_cache_allocated)
    cp b
    jr c,recon_track_cache_copy_bad
    jr z,recon_track_cache_copy_bad
    ld a,b
    ld e,a
    ld d,0
    ld hl,recon_track_cache_segments
    add hl,de
    ld a,(hl)
    ld (recon_track_source_segment),a

    ; If the destination lies in page 1, map the source in page 2. Otherwise
    ; use page 1, leaving page-2 destinations and page-0 buffers untouched.
    ld hl,(recon_track_read_dest)
    ld a,h
    cp 0x40
    jr c,recon_track_source_page1
    cp 0x80
    jr nc,recon_track_source_page1
    ld a,(recon_track_source_segment)
    call MAP_P2
    ld hl,0x8000
    jr recon_track_source_base_ready
recon_track_source_page1:
    ld a,(recon_track_source_segment)
    call MAP_P1
    ld hl,0x4000
recon_track_source_base_ready:
    ld de,(recon_track_diff)
    ld a,d
    and 0x3F
    ld d,a
    add hl,de
    ld (recon_track_source_ptr),hl

    ; copy_count = min(bytes_left, 0x4000 - segment_offset)
    ld hl,0x4000
    or a
    sbc hl,de
    ld de,(recon_track_read_left)
    push hl
    or a
    sbc hl,de
    pop hl
    jr c,recon_track_copy_count_ready
    ld h,d
    ld l,e
recon_track_copy_count_ready:
    ld (recon_track_copy_count),hl
    ld bc,(recon_track_copy_count)
    ld hl,(recon_track_source_ptr)
    ld de,(recon_track_read_dest)
    ldir
    ld (recon_track_read_dest),de

    ld hl,(recon_track_diff)
    ld de,(recon_track_copy_count)
    add hl,de
    ld (recon_track_diff),hl
    ld a,(recon_track_diff+2)
    adc a,0
    ld (recon_track_diff+2),a
    ld hl,(recon_track_read_left)
    ld de,(recon_track_copy_count)
    or a
    sbc hl,de
    ld (recon_track_read_left),hl
    jr recon_track_cache_copy_loop

recon_track_cache_copy_done:
    call recon_track_cache_restore_maps
    ; Advance TMP_OFFSET to the byte following the request.
    ld hl,(recon_track_cache_base)
    ld de,(recon_track_diff)
    add hl,de
    ld (TMP_OFFSET_LO),hl
    ld a,(recon_track_cache_base+2)
    ld c,a
    ld a,(recon_track_diff+2)
    adc a,c
    ld (TMP_OFFSET_HI),a
    xor a
    ret

recon_track_cache_copy_bad:
    call recon_track_cache_restore_maps
recon_track_cache_miss:
    ld de,(recon_track_read_dest)
    ld bc,(recon_track_read_left)
    ld a,1
    or a
    ret

recon_track_cache_restore_maps:
    ld a,(recon_track_saved_p1)
    call MAP_P1
    ld a,(recon_track_saved_p2)
    jp MAP_P2

; ---------------------------------------------------------------------------
; 1 KiB package read-ahead cache
; ---------------------------------------------------------------------------
; The original KSPOS page-3 segment is visible for every filesystem call and
; is hidden only while an engine owns PAGE3_WORKRAM. D600h-D9FFh therefore
; provides a 1024-byte read-ahead window without another mapper segment.
; Larger DOS1 random-block transfers were rejected after openMSX testing on
; the Philips NMS 8250 DiskROM because they could stall at FAT boundaries.
; Keep the read-ahead window after the complete overlay image.  v0.22.7
; grew the overlay past D600h, so the old fixed buffer overwrote both code and
; selected-track preload state during the first KSP header read on real MSX.
; The current overlay ends at DC1Fh. Keep the cache in DC20h-DFFFh;
; E000h is used as a DiskROM/BIOS stack on some machines.
RECON_DISK_BUFFER      equ 0xDC20
RECON_DISK_BUFFER_SIZE equ 0x03E0

recon_cache_invalidate:
    xor a
    ld (recon_cache_valid),a
    ret

; Read BC bytes at TMP_OFFSET_HI:TMP_OFFSET_LO into DE. Requests larger than
; the cache are split automatically. Return Z on success, NZ on failure.
recon_disk_read_cached:
    call recon_track_cache_try_read
    ret z
    ; KSPOS DiskROM implementations may use a private stack immediately below
    ; E000h.  A fixed page-3 read-ahead window can therefore collide with the
    ; DiskROM even when it no longer overlaps this overlay.  Before playback,
    ; use the proven DOS1 random-block path directly.  Once selected-track
    ; preload is valid, recon_track_cache_try_read serves all dynamic requests
    ; from mapper RAM and this path is never reached during playback.
    ld (recon_cache_dest),de
    ld (recon_cache_left),bc
    ld hl,(TMP_OFFSET_LO)
    ld (recon_cache_req_off),hl
    ld a,(TMP_OFFSET_HI)
    ld (recon_cache_req_off+2),a
    jp recon_cache_direct_fallback

; Legacy read-ahead implementation retained for source compatibility/model
; coverage, but intentionally unreachable on KSPOS real-hardware builds.
; The old 1 KiB read-ahead implementation was intentionally unreachable on
; KSPOS and has been removed. Selected-track mapper preload is the playback
; cache; all other reads use the direct DOS1 fallback below.

recon_cache_direct_fallback:
    xor a
    ld (recon_cache_valid),a
    ld hl,1
    ld (FILE_FCB+14),hl
    ld hl,(recon_cache_req_off)
    ld (FILE_FCB+33),hl
    ld a,(recon_cache_req_off+2)
    ld (FILE_FCB+35),a
    xor a
    ld (FILE_FCB+36),a
    ld de,(recon_cache_dest)
    ld bc,(recon_cache_left)
    call FCB_READ_CURRENT
    jr nz,recon_cache_read_error
    ld hl,(recon_cache_req_off)
    ld de,(recon_cache_left)
    add hl,de
    ld (recon_cache_req_off),hl
    ld (TMP_OFFSET_LO),hl
    ld a,(recon_cache_req_off+2)
    adc a,0
    ld (recon_cache_req_off+2),a
    ld (TMP_OFFSET_HI),a
    xor a
    ret

recon_cache_read_error:
    xor a
    ld (recon_cache_valid),a
    ld a,1
    or a
    ret

; ---------------------------------------------------------------------------
; Persistent overlay state and scratch buffers
; ---------------------------------------------------------------------------
recon_map_allocated: db 0
recon_map_segment: db 0
recon_records_left: dw 0
recon_map_ptr: dw 0
recon_previous_end: dw 0
recon_dest: dw 0
recon_length: dw 0
recon_record_end: dw 0
recon_source_skip: dw 0
recon_table_end: dw 0
recon_cached_slab: dw 0xFFFF
recon_cached_resource: dw 0xFFFF
recon_cached_kzb_block: dw 0xFFFF
recon_kzb_blocks_left: dw 0
recon_kzb_desc_abs: db 0,0,0
recon_skip24: db 0,0,0
recon_copy_left: dw 0
recon_chunk: dw 0
recon_source_offset: db 0,0,0
recon_rel24: db 0,0,0
recon_tmp24: db 0,0,0
recon_header: ds 16,0
recon_record: ds 16,0
recon_pool_resource: ds 32,0
recon_source_resource: ds 32,0
recon_pbk_header: ds 32,0
recon_block_desc: ds 8,0
recon_slab_desc: ds 16,0
recon_kzb_header: ds 16,0
recon_kzb_desc: ds 16,0

recon_cache_valid: db 0
recon_cache_req_off: db 0,0,0
recon_cache_dest: dw 0
recon_cache_left: dw 0
recon_direct_count: db 0
recon_direct_base_index: db 0
recon_direct_first_page: dw 0
recon_direct_copy_start: dw 0
recon_direct_copy_length: dw 0

; Selected-track packed payload cache state.
recon_track_cache_valid: db 0
recon_track_cache_count: db 0
recon_track_cache_allocated: db 0
recon_track_cache_segments: ds RECON_TRACK_CACHE_MAX,0
recon_track_cache_base: db 0,0,0
recon_track_cache_size: db 0,0,0
recon_track_start_page: dw 0
recon_track_end_page: dw 0
recon_track_candidate_end: dw 0
recon_track_scan_page: dw 0
recon_track_have_base: db 0
recon_track_page_count: db 0
recon_track_page_table_ptr: dw 0
recon_track_page_entries: ds RECON_TRACK_PAGE_MAX*24,0
recon_track_expected: db 0,0,0
recon_track_remaining: db 0,0,0
recon_track_file_off: db 0,0,0
recon_track_segment_index: db 0
recon_track_segment_left: dw 0
recon_track_segment_dest: dw 0
recon_track_chunk_count: dw 0
recon_track_diff: db 0,0,0
recon_track_request_end: db 0,0,0
recon_track_read_dest: dw 0
recon_track_read_left: dw 0
recon_track_saved_p1: db 0
recon_track_saved_p2: db 0
recon_track_source_segment: db 0
recon_track_source_ptr: dw 0
recon_track_copy_count: dw 0




; ---------------------------------------------------------------------------
; Durable LOG5 split-tail backup.
; 6500h..67FFh is outside the 112x66-byte track-title cache (ends 64E0h),
; below the menu overlay backup at 6A00h and below HVAR at 7400h.
; The music warm cache starts at 8000h, so playback never touches this copy.
; ---------------------------------------------------------------------------
RECON_SPLIT_RAM  equ 0x6E00
RECON_SPLIT_VRAM equ 0x64E0
RECON_SPLIT_SIZE equ 0x051A

recon_backup_split:
    call VDP_IRQ_BEGIN
    ld hl,RECON_SPLIT_VRAM
    xor a
    call VRAM_SET_WRITE_ADDRESS
    ld hl,RECON_SPLIT_RAM
    ld bc,RECON_SPLIT_SIZE
recon_backup_split_loop:
    ld a,(hl)
    out (PORT_VDP_DATA),a
    inc hl
    dec bc
    ld a,b
    or c
    jr nz,recon_backup_split_loop
    jp VDP_IRQ_END

recon_restore_split:
    call VDP_IRQ_BEGIN
    ld hl,RECON_SPLIT_VRAM
    xor a
    call VRAM_SET_READ_ADDRESS
    ld hl,RECON_SPLIT_RAM
    ld bc,RECON_SPLIT_SIZE
recon_restore_split_loop:
    in a,(PORT_VDP_DATA)
    ld (hl),a
    inc hl
    dec bc
    ld a,b
    or c
    jr nz,recon_restore_split_loop
    jp VDP_IRQ_END

recon_overlay_end:
