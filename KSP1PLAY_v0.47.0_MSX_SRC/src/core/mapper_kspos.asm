; Memory-mapper management and KSPOS gateway configuration.

; get_mapper_api
; Output: CF=0 mapper API ready; CF=1 mapper unavailable.
; Side effects: initializes mapper call vectors and process-page state.
get_mapper_api:
	di
	in a,(PORT_MAPPER_P1)
	ld (probe_original_p1),a
	ld e,a
	ld b,004h
mapper_probe_loop:
	ld a,e
	add a,b
	ld d,a
	out (PORT_MAPPER_P1),a
	ld a,(CPU_PAGE1_BASE)
	cpl
	ld (probe_marker),a
	ld a,e
	out (PORT_MAPPER_P1),a
	ld a,(CPU_PAGE1_BASE)
	ld (probe_base_byte),a
	ld a,(probe_marker)
	ld (CPU_PAGE1_BASE),a
	ld a,d
	out (PORT_MAPPER_P1),a
	ld a,(CPU_PAGE1_BASE)
	ld c,a
	ld a,e
	out (PORT_MAPPER_P1),a
	ld a,(probe_base_byte)
	ld (CPU_PAGE1_BASE),a
	ld a,c
mapper_probe_compare_marker:
	ld c,a
	ld a,(probe_marker)
	cp c
	jp z,mapper_probe_found
	sla b
	jp nz,mapper_probe_loop
	ld a,0ffh
	jp mapper_probe_ready
mapper_probe_found:
	ld a,b
	dec a
mapper_probe_ready:
	ld (mapper_segment_mask),a
	ld a,(probe_original_p1)
	out (PORT_MAPPER_P1),a
	ei
	ld a,(mapper_segment_mask)
	cp 007h
	jp c,get_mapper_fail
	or a
	ret
get_mapper_fail:
	scf
	ret

; Snapshot mapper pages and the primary-slot register before any KSP engine is
; installed. These values are the authoritative restore target on stop/error.
capture_original_pages:
	in a,(PORT_MAPPER_P0)
	ld (original_p0),a
	in a,(PORT_MAPPER_P1)
	ld (original_p1),a
	ld (mapped_p1),a
	in a,(PORT_MAPPER_P2)
	ld (original_p2),a
	ld (mapped_p2),a
	in a,(PORT_MAPPER_P3)
	ld (original_p3),a
	in a,(PORT_PPI_A)
	ld (original_a8),a
	call capture_secondary_slot_state
	ld (space_previous+1),a
	call mapper_build_pool
	ret
kspos_sync_gateway:
	ld a,(KSPOS_FLAGS)
	and 080h
	ret z
	call restore_process_pages
	ld a,(KSPOS_RUNTIME_P0)
	call map_p2
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld de,KSPMENU_ENTRY_VDP_SETUP
	ld bc,KSPOS_GATEWAY_COPY_BYTES
	ldir
	ld a,(original_p2)
	call map_p2
	ret
kspos_configure_engine_runtime:
	ld a,(KSPOS_FLAGS)
	and 080h
	ret z
	ld a,080h
	ld b,a
	ld a,(dynamic_profile)
	or a
	jp nz,kspos_engine_compatibility
	ld a,(engine_required_hardware)
	and 008h
	jp nz,kspos_engine_compatibility
	ld a,b
	or 040h
	ld b,a
	ld a,(page3_workram_profile)
	or a
	jp z,kspos_engine_page3_done
	ld a,b
	or 001h
	ld b,a
kspos_engine_page3_done:
	ld a,(engine_required_hardware)
	and 00eh
	jp z,kspos_engine_scc_done
	ld a,b
	or 002h
	ld b,a
kspos_engine_scc_done:
	ld hl,001ffh
	ld (KSPOS_RANGE0_END),hl
	jp kspos_engine_ranges
kspos_engine_compatibility:
	ld hl,PAGE_16K_LAST_OFFSET
	ld (KSPOS_RANGE0_END),hl
kspos_engine_ranges:
	ld a,b
	ld (KSPOS_FLAGS),a
	ld hl,(engine_init_address)
	ld (KSPOS_TARGET_INIT),hl
	ld hl,(engine_play_address)
	ld (KSPOS_TARGET_PLAY),hl
	ld hl,(engine_stop_address)
	ld (KSPOS_TARGET_STOP),hl
	ld a,(original_p3)
	ld (KSPOS_ENGINE_P3),a
	ld a,(page3_workram_profile)
	or a
	jp z,kspos_engine_p3_ready
	ld a,(engine_p3_segment)
	ld (KSPOS_ENGINE_P3),a
kspos_engine_p3_ready:
	ld a,(mapper_pool_count)
	ld (KSPOS_FREE_SEGMENTS),a
	ld a,(KSPOS_FLAGS)
	and 002h
	jp z,kspos_engine_no_scc_range
	ld a,002h
	ld (KSPOS_UNAVAILABLE_COUNT),a
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	ld (KSPOS_RANGE1_START),hl
	ld hl,SCCPLUS_MODE_REG+1
	ld (KSPOS_RANGE1_END),hl
	jp kspos_sync_gateway
kspos_engine_no_scc_range:
	ld a,001h
	ld (KSPOS_UNAVAILABLE_COUNT),a
	ld hl,INVALID_WORD
	ld (KSPOS_RANGE1_START),hl
	ld (KSPOS_RANGE1_END),hl
	jp kspos_sync_gateway
kspos_verify_engine_memory:
	ld a,(KSPOS_FLAGS)
	and 040h
	ret z
	ld a,(KSPOS_PLAYER_P0)
recon_split_size:
	ld b,a
	ld a,(KSPOS_RUNTIME_P0)
	cp b
	jp z,kspos_verify_bad
	ld a,(KSPOS_FLAGS)
	and 001h
	ret z
	ld a,(KSPOS_ENGINE_P3)
	cp b
	jp z,kspos_verify_bad
	ld b,a
	ld a,(KSPOS_RUNTIME_P0)
	cp b
	jp z,kspos_verify_bad
	or a
	ret
kspos_verify_bad:
	scf
	ret
mapper_build_pool:
	xor a
	ld (mapper_pool_count),a
	ld a,(mapper_segment_mask)
	ld b,a
mapper_pool_scan:
	ld a,b
	call mapper_segment_is_process
	jp z,mapper_pool_next
	ld a,(mapper_pool_count)
	cp 00ch
	ret nc
	ld e,a
	ld d,000h
	ld hl,mapper_pool
	add hl,de
	ld (hl),b
	inc a
	ld (mapper_pool_count),a
mapper_pool_next:
	ld a,b
	or a
	ret z
	dec b
	jp mapper_pool_scan
mapper_segment_is_process:
	ld a,(mapper_segment_mask)
	ld c,a
	ld a,(original_p0)
	and c
	cp b
	ret z
	ld a,(original_p1)
	and c
	cp b
	ret z
	ld a,(original_p2)
	and c
	cp b
	ret z
	ld a,(original_p3)
	and c
	cp b
	ret
mapper_alloc_user_primary:
	ld a,(mapper_pool_count)
	or a
	jp z,mapper_alloc_failed
	dec a
	ld (mapper_pool_count),a
	ld e,a
	ld d,000h
	ld hl,mapper_pool
	add hl,de
	ld a,(hl)
	or a
	ret
mapper_alloc_failed:
	xor a
	scf
	ret
mapper_free_primary:
	ld b,a
	ld a,(mapper_pool_count)
	cp 00ch
	ret nc
	ld e,a
	ld d,000h
	ld hl,mapper_pool
	add hl,de
	ld (hl),b
	inc a
	ld (mapper_pool_count),a
	or a
	ret
map_p1:
	ld (mapped_p1),a
	out (PORT_MAPPER_P1),a
	ret
map_p2:
	ld (mapped_p2),a
	out (PORT_MAPPER_P2),a
	ret
restore_process_pages:
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ld a,(original_a8)
	out (PORT_PPI_A),a
	call restore_secondary_slot_state
	ld a,(original_p1)
	call map_p1
	ld a,(original_p2)
	call map_p2
	ret
map_scc_page2:
	ld a,(scc_slot)
map_primary_slot_page2:
	push bc
	push de
	push hl
	ld h,080h
	call BIOS_ENASLT
	pop hl
	pop de
	pop bc
	ret
	ds 3,0		; fixed layout gap

; Allocate the mapper segments that hold preloaded HOT data. Playback must use
; these RAM-backed segments; normal PLAY callbacks must never depend on disk I/O.
allocate_hot_segments:
	ld hl,(hpl_hot_raw)
	ld a,(hpl_hot_raw+2)
	or a
	jp nz,alloc_hot_bad
	ld de,PAGE_16K_LAST_OFFSET
	add hl,de
	ld a,h
	and 0c0h
	rlca
	rlca
	cp 004h
	jp nc,alloc_hot_bad
	ld (hot_needed_count),a
	xor a

	ld (hot_segment_count),a
	ld a,(hot_needed_count)
	ld b,a
	ld hl,hot_segments
alloc_hot_loop:
	ld a,b
	or a
	jp z,alloc_hot_done
	push hl
	push bc
	call mapper_alloc_user_primary
	pop bc
	pop hl
	jp c,alloc_hot_bad
	ld (hl),a
	inc hl
	ld a,(hot_segment_count)
	inc a
	ld (hot_segment_count),a
	djnz alloc_hot_loop
alloc_hot_done:
	or a
	ret
alloc_hot_bad:
	scf
	ret
free_hot_segments:
	ld a,(hot_segment_count)
	ld b,a
	ld hl,hot_segments
free_hot_loop:
	ld a,b
	or a
	ret z
	ld a,(hl)
	inc hl
	push hl
	push bc
	call mapper_free_primary
	pop bc
	pop hl
	djnz free_hot_loop
	ret
cleanup:
	di
	call stop_and_mute
	call release_engine_resources
	call fcb_close_current
	call ui_reset_package_state
	ei
	ret
release_engine_resources:
	call restore_refresh_rate
	call page_runtime_available
	call nz,RECON_ENTRY_RELEASE
	ld a,(space_previous+1)
	or a
	jp z,release_engine_done
	ld a,(original_a8)
	out (PORT_PPI_A),a
	call restore_process_pages
	call free_hot_segments
	call free_template_segment
	call RECON_ENTRY_FREE_PAGE2
	call free_page3_workram_segment
	call free_mwk_segment
	call hpol_map_release
	call restore_process_pages
release_engine_done:
	xor a
	ld (space_previous+2),a
	ld (engine_running),a
	ld (hybrid_ready),a
	ld (file_cache_ready),a
	ld (template_cache_ready),a
	ld (refresh_saved),a
	ld hl,INVALID_WORD
	ld (PREPARED_ENGINE),hl
	ret
