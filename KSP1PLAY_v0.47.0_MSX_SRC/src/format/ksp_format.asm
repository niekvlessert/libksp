; KSP container validation and descriptor loading.

; validate_header
; Input: KSP header is loaded in ksp_header.
; Output: CF=0 supported KSP header; CF=1 format/profile rejection.
validate_header:
	ld hl,ksp_header
	ld a,(hl)
	cp 04bh
	jp nz,header_bad
	inc hl
	ld a,(hl)
	cp 053h
	jp nz,header_bad
	inc hl
	ld a,(hl)
	cp 050h
	jp nz,header_bad
	inc hl
	ld a,(hl)
	cp 031h
	jp nz,header_bad
	ld hl,(ksp_header_size)
	ld de,KSP_DECLARED_HEADER_BYTES
	or a
	sbc hl,de
	jp nz,header_bad
	ld hl,(ksp_version_minor)
	ld a,h
	or a
	jp nz,header_bad
	ld a,l
	cp KSP_SUPPORTED_MINOR_LIMIT
	jp nc,header_bad
	ld hl,(ksp_engine_count)
	ld a,h
	or l
	jp z,header_bad
	ld hl,(ksp_engine_entry_size)
	ld de,KSP_FIXED_ENGINE_ENTRY_BYTES
	or a
	sbc hl,de
	jp c,header_bad
	ld hl,(ksp_page_entry_size)
	ld de,KSP_MIN_PAGE_ENTRY_BYTES
	or a
	sbc hl,de
	jp c,header_bad
	ld hl,(ksp_track_entry_size)
	ld de,KSP_FIXED_TRACK_ENTRY_BYTES
	or a
	sbc hl,de
	jp c,header_bad
	ld hl,(ksp_resource_entry_size)
	ld de,KSP_FIXED_TRACK_ENTRY_BYTES
	or a
	sbc hl,de
	jp c,header_bad
	or a
	ret
header_bad:
	scf
	ret
load_engine_zero:
	ld hl,ENGINE_DIRECT_CALL_PATCH
load_engine_index:
	push hl
	ld de,(ksp_engine_count)
	or a
	sbc hl,de
	pop hl
	jp nc,load_engine_bad
	ld (CURRENT_ENGINE),hl
	ld de,(ksp_engine_entry_size)
	call mul16x16_24
	ld c,a
	ld de,(ksp_engine_table_offset_lo)
	add hl,de
	ld a,(ksp_engine_table_offset_hi)
	adc a,c
	ld de,engine_entry
	ld bc,KSP_FIXED_ENGINE_ENTRY_BYTES
	call read_at
	jp nz,load_engine_bad
	or a
	ret
load_engine_bad:
	scf
	ret
validate_engine_profile:
	xor a
	ld (dynamic_profile),a
	ld (page2_runtime_profile),a
	ld (page3_workram_profile),a
	ld hl,(engine_flags_hi)
	ld a,h
	or l
	jp nz,engine_profile_bad
	ld hl,(engine_entry)
	ld a,h
	or a
	jp nz,engine_profile_bad
	ld a,l
	and 0c2h
	jp nz,engine_profile_bad
	ld a,l
	and 038h
	jp z,engine_minor_flags_ok
	ld a,(ksp_version_minor)
	or a
	jp z,engine_profile_bad
engine_minor_flags_ok:
	ld a,l
	and 008h
	jp z,engine_page2_flag_done
	ld a,001h
	ld (page2_runtime_profile),a
engine_page2_flag_done:
	ld a,l
	and 010h
	jp z,engine_page3_flag_done
	ld a,001h
	ld (page3_workram_profile),a
engine_page3_flag_done:
	ld a,l
	and 001h
	ld (dynamic_profile),a
	ld a,(engine_required_hardware)
	and 0a0h
	jp nz,engine_profile_bad
	ld a,(engine_required_hardware_byte1)
	or a
	jp nz,engine_profile_bad
	ld hl,(engine_required_hardware_hi)
	ld a,h
	or l
	jp nz,engine_profile_bad
	ld a,(page2_runtime_profile)
	or a
	jp z,engine_page2_hardware_ok
	ld a,(engine_required_hardware)
	and 00eh
	jp nz,engine_profile_bad
engine_page2_hardware_ok:
	ld a,(engine_required_hardware)
	and 00ch
	cp 00ch
	jp z,engine_profile_bad
	ld hl,(engine_abi_version)
	ld de,KSP_ENGINE_ABI_VERSION
	or a
	sbc hl,de
	jp nz,engine_profile_bad
	ld hl,(engine_play_frequency)
	ld de,KSP_ENGINE_TICK_50HZ
	or a
	sbc hl,de
	jp z,engine_tick_ok
	add hl,de
	ld de,KSP_ENGINE_TICK_60HZ
	or a
	sbc hl,de
	jp nz,engine_profile_bad
engine_tick_ok:
	ld hl,(engine_page_load_address)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,engine_profile_bad
	ld hl,(engine_page_size)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,engine_profile_bad
	ld hl,(engine_init_address)
	ld a,h
	cp 040h
	jp c,engine_profile_bad
	cp 080h
	jp nc,engine_profile_bad
	ld hl,(engine_play_address)
	ld a,h
	cp 040h
	jp c,engine_profile_bad
	cp 080h
	jp nc,engine_profile_bad
	ld a,(dynamic_profile)
	or a
	jp z,engine_no_dynamic
	ld hl,(engine_dynamic_gateway)
	ld a,h
	or l
	jp z,engine_profile_bad
	ld hl,(engine_replace_start)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp c,engine_profile_bad
	ld hl,(engine_replace_start)
	ld de,KSPMENU_ENTRY_VDP_SETUP
	or a
	sbc hl,de
	jp nc,engine_profile_bad
	jp engine_dynamic_valid
engine_no_dynamic:
	ld hl,(engine_dynamic_gateway)
	ld a,h
	or l
	jp nz,engine_profile_bad
engine_dynamic_valid:
	ld a,(engine_bank_count)
	or a
	jp nz,engine_profile_bad
	ld a,(engine_bank_width)
	or a
	jp nz,engine_profile_bad
	ld a,(engine_template_compression)
	cp 002h
	jp nc,engine_profile_bad
	ld (template_compression),a
	ld a,(engine_template_offset_top)
	or a
	jp nz,engine_profile_bad
	ld hl,(engine_template_packed_size_hi)
	ld a,h
	or l
	jp nz,engine_profile_bad
	ld hl,(engine_template_unpacked_size_lo)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,engine_profile_bad
	ld hl,(engine_template_unpacked_size_hi)
	ld a,h
	or l
	jp nz,engine_profile_bad
	ld a,(template_compression)
	or a
	jp nz,engine_template_ok
	ld hl,(engine_template_packed_size_lo)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,engine_profile_bad
engine_template_ok:
	or a
	ret
engine_profile_bad:
	scf
	ret
find_hpol_resource:
	ld hl,(ksp_resource_count)
	ld (resource_count),hl
	ld hl,(ksp_resource_table_offset_lo)
	ld a,(ksp_resource_table_offset_hi)
	ld (resource_cursor_lo),hl
	ld (resource_cursor_hi),a
	xor a
	ld (resource_index),a
	ld (resource_index+1),a
find_hpol_loop:
	ld hl,(resource_count)
	ld a,h
	or l
	jp z,find_hpol_bad
	ld hl,(resource_cursor_lo)
	ld a,(resource_cursor_hi)
	ld de,resource_entry
	ld bc,00020h
	call read_at
	jp nz,find_hpol_bad
	ld hl,resource_entry
	ld a,(hl)
	cp 048h
	jp nz,find_hpol_next
	inc hl
	ld a,(hl)
	cp 050h
	jp nz,find_hpol_next
	inc hl
	ld a,(hl)
	cp 04fh
	jp nz,find_hpol_next
	inc hl
	ld a,(hl)
	cp 04ch
	jp nz,find_hpol_next
	ld hl,(resource_payload_offset_lo)
	ld a,(resource_payload_offset_hi)
	ld (hpol_offset_lo),hl
	ld (hpol_offset_hi),a
	ld hl,(resource_packed_size_lo)
	ld a,(resource_packed_size_hi)
	ld (hpol_size_lo),hl
	ld (hpol_size_hi),a
	or a
	ret
find_hpol_next:
	ld hl,(resource_cursor_lo)
	ld de,KSP_FIXED_TRACK_ENTRY_BYTES
	add hl,de
	ld (resource_cursor_lo),hl
	jp nc,find_hpol_no_carry
	ld a,(resource_cursor_hi)
	inc a
	ld (resource_cursor_hi),a
find_hpol_no_carry:
	ld hl,(resource_count)
	dec hl
	ld (resource_count),hl
	ld hl,(resource_index)
	inc hl
	ld (resource_index),hl
	jp find_hpol_loop
find_hpol_bad:
	scf
	ret
load_hpl_header:
	ld hl,(hpol_offset_lo)
	ld a,(hpol_offset_hi)
	ld de,hpl_header
	ld bc,00060h
	call read_at
	jp nz,hpl_bad
	ld hl,hpl_header
	ld a,(hl)
	cp 048h
	jp nz,hpl_bad
	inc hl
	ld a,(hl)
	cp 050h
	jp nz,hpl_bad
	inc hl
	ld a,(hl)
	cp 04ch
	jp nz,hpl_bad
	inc hl
	ld a,(hl)
	cp 031h
	jp nz,hpl_bad
	ld hl,(hpl_header_size)
	ld de,00060h
	or a
	sbc hl,de
	jp nz,hpl_bad
	ld hl,(hpl_version)
	ld de,KSP_ENGINE_ABI_VERSION
	or a
	sbc hl,de
	jp nz,hpl_bad
	ld hl,(hpl_header_block_size)
	ld (hpl_block_size),hl
	ld a,h
	or a
	jp nz,hpl_bad
	ld a,l
	cp 040h
	jp c,hpl_bad
	cp 040h
	jp z,hpl_bs64
	cp 080h
	jp z,hpl_bs128
	jp hpl_check_256
hpl_bs64:
	ld a,006h
	jp hpl_shift_ready
hpl_bs128:
	ld a,007h
	jp hpl_shift_ready
hpl_check_256:
	ld hl,(hpl_block_size)
	ld de,HPL_BLOCK_256_BYTES
	or a
	sbc hl,de
	jp z,hpl_bs256
	ld hl,(hpl_block_size)
	ld de,IO_BUFFER_SIZE
	or a
	sbc hl,de
	jp nz,hpl_bad
	ld a,009h
	jp hpl_shift_ready
hpl_bs256:
	ld a,008h
hpl_shift_ready:
	ld (hpl_block_shift),a
	ld hl,(hpl_header_position_count)
	ld (hpl_position_count),hl
	add hl,hl
	ld de,IO_BUFFER_SIZE
	or a
	sbc hl,de
	jp nc,hpl_bad
	ld hl,(hpl_page_count)
	ld de,(ksp_page_count)
	or a
	sbc hl,de
	jp nz,hpl_bad
	ld hl,(hpl_hot_block_count)
	ld (hpl_hot_count),hl
	ld hl,(hpl_warm_block_count)
	ld (hpl_warm_count),hl
	ld hl,(hpl_cold_block_count)
	ld (hpl_cold_count),hl
	ld hl,(hpl_cold_slab_count)
	ld (hpl_slab_count),hl
	ld hl,(hpl_flags)
	ld a,h
	or l
	jp nz,hpl_bad
	ld hl,(hpl_position_table_offset_lo)
	ld a,(hpl_position_table_offset_hi)
	ld (hpl_positions_off),hl
	ld (hpl_positions_off+2),a
	ld hl,(hpl_map_stream_offset_lo)
	ld a,(hpl_map_stream_offset_hi)
	ld (hpl_maps_off),hl
	ld (hpl_maps_off+2),a
	ld hl,(hpl_map_packed_size_lo)
	ld a,(hpl_map_packed_size_hi)
	ld (hpl_maps_packed),hl
	ld (hpl_maps_packed+2),a
	ld hl,(hpl_map_raw_size_lo)
	ld a,(hpl_map_raw_size_hi)
	ld (hpl_maps_raw),hl
	ld (hpl_maps_raw+2),a
	ld hl,(hpl_hot_stream_offset_lo)
	ld a,(hpl_hot_stream_offset_hi)
	ld (hpl_hot_off),hl
	ld (hpl_hot_off+2),a
	ld hl,(hpl_hot_packed_size_lo)
	ld a,(hpl_hot_packed_size_hi)
	ld (hpl_hot_packed),hl
	ld (hpl_hot_packed+2),a
	ld hl,(hpl_hot_raw_size_lo)
	ld a,(hpl_hot_raw_size_hi)
	ld (hpl_hot_raw),hl
	ld (hpl_hot_raw+2),a
	ld hl,(hpl_warm_stream_offset_lo)
	ld a,(hpl_warm_stream_offset_hi)
	ld (hpl_warm_off),hl
	ld (hpl_warm_off+2),a
	ld hl,(hpl_warm_packed_size_lo)
	ld a,(hpl_warm_packed_size_hi)
	ld (hpl_warm_packed),hl
	ld (hpl_warm_packed+2),a
	ld hl,(hpl_warm_raw_size_lo)
	ld a,(hpl_warm_raw_size_hi)
	ld (hpl_warm_raw),hl
	ld (hpl_warm_raw+2),a
	ld hl,(hpl_cold_slab_table_offset_lo)
	ld a,(hpl_cold_slab_table_offset_hi)
	ld (hpl_cold_table_off),hl
	ld (hpl_cold_table_off+2),a
	ld a,(hpl_maps_raw+2)
	or a
	jp nz,hpl_bad
	ld hl,(hpl_maps_raw)
	ld de,PAGE_16K_BYTES_PLUS_ONE
	or a
	sbc hl,de
	jp nc,hpl_bad
	ld a,(hpl_maps_packed+2)
	or a
	jp nz,hpl_bad
	ld a,(hpl_hot_packed+2)
	or a
	jp nz,hpl_bad
	ld a,(hpl_warm_packed+2)
	or a
	jp nz,hpl_bad
	ld a,(hpl_hot_raw+2)
	or a
	jp nz,hpl_bad
	ld hl,(hpl_hot_raw)
	ld de,HPL_HOT_RAM_LIMIT_EXCLUSIVE
	or a
	sbc hl,de
	jp nc,hpl_bad
	ld a,(hpl_warm_raw+2)
	or a
	jp z,hpl_warm_ok
	cp 001h
	jp nz,hpl_bad
	ld hl,(hpl_warm_raw)
	ld de,HPL_WARM_VRAM_LIMIT_EXCLUSIVE
	or a
	sbc hl,de
	jp nc,hpl_bad
hpl_warm_ok:
	ld hl,(hpl_warm_raw)
	ld a,(hpl_warm_raw+2)
	ld de,(hpl_maps_raw)
	add hl,de
	adc a,000h
	or a
	jp z,hpl_vram_fit
	cp 001h
	jp nz,hpl_bad
	ld de,HPL_WARM_VRAM_LIMIT_EXCLUSIVE
	or a
	sbc hl,de
	jp nc,hpl_bad
hpl_vram_fit:
	or a
	ret
hpl_bad:
	scf
	ret
preload_hybrid_pool:
	call make_abs_positions_offset
	ld de,hpol_position_cache
	ld hl,(hpl_position_count)
	add hl,hl
	ld b,h
	ld c,l
	ld hl,(abs_offset_lo)
	ld a,(abs_offset_hi)
	call read_at
	jp nz,preload_bad
	call make_abs_maps_offset
	ld hl,(abs_offset_lo)
	ld a,(abs_offset_hi)
	ld de,(hpl_maps_packed)
	ld b,d
	ld c,e
	call stream_begin
	jp c,preload_bad
	ld hl,(hpl_warm_raw)
	ld a,(hpl_warm_raw+2)
	ld de,KSPMENU_ENTRY_VDP_SETUP
	add hl,de
	adc a,000h
	call vram_set_write_address
	ld a,001h
	ld (zx_mode),a
	ld hl,(hpl_maps_raw)
	ld a,(hpl_maps_raw+2)
	call zx_set_output_size
	call zx_decode_stream
	jp c,preload_bad
	call restore_process_pages
	call restore_process_pages
	call make_abs_warm_offset
	ld hl,(abs_offset_lo)
	ld a,(abs_offset_hi)
	ld de,(hpl_warm_packed)
	ld b,d
	ld c,e
	call stream_begin
	jp c,preload_bad
	ld a,001h
	ld (zx_mode),a
	call vram_set_warm_base_write
	ld hl,(hpl_warm_raw)
	ld a,(hpl_warm_raw+2)
	call zx_set_output_size
	call zx_decode_stream
	jp c,preload_bad
	call make_abs_hot_offset
	ld hl,(abs_offset_lo)
	ld a,(abs_offset_hi)
	ld de,(hpl_hot_packed)
	ld b,d
	ld c,e
	call stream_begin
	jp c,preload_bad
	ld a,002h
	ld (zx_mode),a
	ld a,0ffh
	ld (hot_write_mapped),a
	ld (hot_read_mapped),a
	ld hl,(hpl_hot_raw)
	ld a,(hpl_hot_raw+2)
	call zx_set_output_size
	call zx_decode_stream
	jp c,preload_bad
	call restore_process_pages
	or a
	ret
preload_bad:
	call restore_process_pages
	scf
	ret
make_abs_positions_offset:
	ld hl,hpl_positions_off
	jp make_hpol_abs
make_abs_maps_offset:
	ld hl,hpl_maps_off
	jp make_hpol_abs
make_abs_hot_offset:
	ld hl,hpl_hot_off
	jp make_hpol_abs
make_abs_warm_offset:
	ld hl,hpl_warm_off
make_hpol_abs:
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld c,(hl)
	ld hl,(hpol_offset_lo)
	add hl,de
	ld (abs_offset_lo),hl
	ld a,(hpol_offset_hi)
	adc a,c
	ld (abs_offset_hi),a
	ret

; Resolve a logical/visible track to its prepared physical track description.
; HVAR/variant selection has already established the package view used here.
