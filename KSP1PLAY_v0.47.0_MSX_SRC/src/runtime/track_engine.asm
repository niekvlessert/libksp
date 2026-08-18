; Track selection, track descriptors, page setup and engine preparation.
;
; The public UI selects a logical track. This module resolves that selection to
; the package implementation, prepares required pages and installs track state.

select_track:
	push hl
	ld de,(ksp_track_count)
	or a
	sbc hl,de
	pop hl
	jp nc,select_track_bad
	ld (scc_slot_b+2),hl
	call ui_load_hvar_overlay
	ret c
	ld hl,(scc_slot_b+2)
	call KSPMENU_JUMP_OPEN_BROWSER
	ret
load_track_context:
	push hl
	ld de,(ksp_track_count)
	or a
	sbc hl,de
	pop hl
	jp nc,select_track_bad
	ld (IMPLEMENTATION_TRACK),hl
	ld de,(ksp_track_entry_size)
	call mul16x16_24
	ld c,a
	ld de,(ksp_track_table_offset_lo)
	add hl,de
	ld a,(ksp_track_table_offset_hi)
	adc a,c
	ld de,track_entry
	ld bc,KSP_FIXED_TRACK_ENTRY_BYTES
	call read_at
	jp nz,select_track_bad
	ld a,(track_flags_hi)
	or a
	jp nz,select_track_bad
	ld a,(track_flags)
	and 0f0h
	jp nz,select_track_bad
	ld hl,(track_entry)
	ld (current_page),hl
	ld hl,(track_song_id)
	ld (current_song_id),hl
	ld hl,(current_page)
	push hl
	ld de,(ksp_page_count)
	or a
	sbc hl,de
	pop hl
	jp nc,select_track_bad
	ld de,(ksp_page_entry_size)
	call mul16x16_24
	ld c,a
	ld de,(ksp_page_table_offset_lo)
	add hl,de
	ld a,(ksp_page_table_offset_hi)
	adc a,c
	ld de,page_entry
	ld bc,KSP_MIN_PAGE_ENTRY_BYTES
	call read_at
	jp nz,select_track_bad
	ld hl,(page_entry)
	call load_engine_index
	jp c,select_track_bad
	call validate_engine_profile
	jp c,select_track_bad
	ld a,(page_encoding)
	cp 000h
	jp z,select_sparse_page
	cp 001h
	jp z,select_complete_page
	cp 002h
	jp z,select_reconstruction_page
	cp 003h
	jp z,select_reconstruction_page
	cp 004h
	jp nz,select_track_bad
	ld hl,(page_flags)
	ld a,h
	or l
	jp nz,select_track_bad
	ld a,(page_payload_compression)
	or a
	jp nz,select_track_bad
	ld hl,(page_payload_offset_lo)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_packed_size_lo)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_lo)
	ld a,h
	or l
	jp nz,select_track_bad
	or a
	ret
select_reconstruction_page:
	call page_runtime_available
	jp z,select_track_bad
	ld hl,(page_flags)
	ld a,h
	or l
	and 0feh
	jp nz,select_track_bad
	ld a,(page_payload_compression)
	cp 002h
	jp nc,select_track_bad
	ld hl,(page_packed_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_lo)
	ld de,00010h
	or a
	sbc hl,de
	jp c,select_track_bad
	add hl,de
	ld de,PAGE_16K_BYTES_PLUS_ONE
	or a
	sbc hl,de
	jp nc,select_track_bad
	or a
	ret
select_sparse_page:
	ld a,(page_flags_hi)
	or a
	jp nz,select_track_bad
	ld a,(page_flags)
	and 0fdh
	jp nz,select_track_bad
	ld a,(page_payload_compression)
	cp 002h
	jp nc,select_track_bad
	ld hl,(page_packed_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_lo)
	ld de,PAGE_16K_BYTES_PLUS_ONE
	or a
	sbc hl,de
	jp nc,select_track_bad
	or a
	ret
select_complete_page:
	ld hl,(page_flags)
	ld a,h
	or l
	jp nz,select_track_bad
	ld a,(page_payload_compression)
	cp 002h
	jp nc,select_track_bad
	ld hl,(page_packed_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_lo)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,select_track_bad
	ld hl,(page_unpacked_size_hi)
	ld a,h
	or l
	jp nz,select_track_bad
	or a
	ret
select_track_bad:
	scf
	ret
mul16x16_24:
	ld (mul_multiplicand),hl
	xor a
	ld (mul_multiplicand+2),a
	ld (mul_multiplier),de
	ld hl,00000h
	ld (mul_result),hl
	ld (mul_result+2),a
	ld b,010h
mul24_loop:
	ld hl,(mul_multiplier)
	bit 0,l
	jp z,mul24_no_add
	ld hl,(mul_result)
	ld de,(mul_multiplicand)
	add hl,de
	ld (mul_result),hl
	ld a,(mul_result+2)
	ld c,a
	ld a,(mul_multiplicand+2)
	adc a,c
	ld (mul_result+2),a
mul24_no_add:
	ld hl,(mul_multiplicand)
	add hl,hl
	ld (mul_multiplicand),hl
	ld a,(mul_multiplicand+2)
	adc a,a
	ld (mul_multiplicand+2),a
	ld hl,(mul_multiplier)
	srl h
	rr l
	ld (mul_multiplier),hl
	djnz mul24_loop
	ld hl,(mul_result)
	ld a,(mul_result+2)
	ret
mul16_real:
	ld b,h
	ld c,l
	ld hl,00000h
mul16_real_loop:
	ld a,b
	or c
	ret z
	add hl,de
	dec bc
	jp mul16_real_loop
install_current_track:
	di
	call stop_and_mute
	call restore_process_pages
	call upload_current_mwk
	jp c,install_bad
	ld a,(page_encoding)
	cp 001h
	jp z,install_complete
	cp 002h
	jp z,install_materialized_page
	cp 003h
	jp z,install_materialized_page
	ld a,001h
	ld (decode_stage),a
	call load_template_page
	jp c,install_bad
	ld a,(page_encoding)
	or a
	jp z,install_sparse
	cp 004h
	jp nz,install_bad
	ld a,(hybrid_ready)
	or a
	jp z,install_bad
	ld a,004h
	ld (decode_stage),a
	call apply_hybrid_page
	jp c,install_bad
	jp install_start_engine
install_materialized_page:
	ld a,005h
	ld (decode_stage),a
	call RECON_ENTRY_APPLY
	jp c,install_bad
	jp install_start_engine
install_sparse:
	ld a,002h
	ld (decode_stage),a
	call apply_sparse_page
	jp c,install_bad
	jp install_start_engine
install_complete:
	ld a,003h
	ld (decode_stage),a
	call load_complete_page
	jp c,install_bad
install_start_engine:
	call patch_engine_gateways
	jp c,install_bad
	ld a,(mapper_pool_count)
	ld (KSPOS_FREE_SEGMENTS),a
	call kspos_sync_gateway
	call kspos_verify_engine_memory
	jp c,install_bad
	call free_mwk_segment
	call initialize_page3_workram_segment
	call prepare_engine_page2_for_install
	jp c,install_bad
	call ui_init_track_engine
	jp c,install_bad
	ld a,001h
	ld (engine_running),a
	ei
	or a
	ret
install_bad:
	call restore_process_pages
	scf
	ret

; Rewrite the selected engine's hardware gateway call sites so SCC/SCC+/dual-SCC
; accesses go through the currently detected physical slot configuration.
patch_engine_gateways:
	xor a
	ld (gateway_patch_flags),a
	ld hl,(engine_replace_start)
	ld de,(engine_page_load_address)
	or a
	sbc hl,de
	jp c,patch_gateways_bad
	ld b,h
	ld c,l
	ld hl,(engine_page_load_address)
patch_gateways_loop:
	ld a,b
	or c
	jp z,patch_gateways_validate
	ld a,(hl)
	cp 0cdh
	jp z,patch_gateways_opcode
	cp 0c3h
	jp nz,patch_gateways_next
patch_gateways_opcode:
	ld a,b
	or a
	jp nz,patch_gateways_have_operand
	ld a,c
	cp 003h
	jp c,patch_gateways_validate
patch_gateways_have_operand:
	inc hl
	ld e,(hl)
	inc hl
	ld d,(hl)
	push hl
	push bc
	ld a,(dynamic_profile)
	or a
	jp z,patch_gateways_dual
	push de
	ld hl,(engine_dynamic_gateway)
	or a
	sbc hl,de
	pop de
	jp nz,patch_gateways_dual
	pop bc
	pop hl
	ld (hl),020h
	dec hl
	ld (hl),000h
	ld a,(gateway_patch_flags)
	or 001h
	ld (gateway_patch_flags),a
	inc hl
	jp patch_gateways_consumed
patch_gateways_dual:
	ld a,d
	cp 0d9h
	jp nz,patch_gateways_no_match
	ld a,e
	cp 000h
	jp z,patch_gateway_a
	cp 004h
	jp z,patch_gateway_b_or_a
	cp 008h
	jp z,patch_gateway_ram
patch_gateways_no_match:
	pop bc
	pop hl
	jp patch_gateways_consumed
patch_gateway_a:
	ld de,dual_scc_select_a
	ld a,002h
	jp patch_gateway_store
patch_gateway_b_or_a:
	ld a,(engine_required_hardware)
	and 008h
	jp nz,patch_gateway_b
	ld de,dual_scc_select_a
	ld a,004h
	jp patch_gateway_store
patch_gateway_b:
	ld de,dual_scc_select_b
	ld a,004h
	jp patch_gateway_store
patch_gateway_ram:
	ld de,dual_scc_restore_ram
	ld a,008h
patch_gateway_store:
	pop bc
	pop hl
	ld (hl),d
	dec hl
	ld (hl),e
	ld e,a
	ld a,(gateway_patch_flags)
	or e
	ld (gateway_patch_flags),a
	inc hl
patch_gateways_consumed:
	inc hl
	dec bc
	dec bc
	dec bc
	jp patch_gateways_loop
patch_gateways_next:
	inc hl
	dec bc
	jp patch_gateways_loop
patch_gateways_validate:
	ld a,(dynamic_profile)
	or a
	jp z,patch_gateways_validate_dual
	ld a,(gateway_patch_flags)
	and 001h
	jp z,patch_gateways_bad
patch_gateways_validate_dual:
	ld a,(engine_required_hardware)
	and 008h
	jp z,patch_gateways_ok
	ld a,(gateway_patch_flags)
	and 00eh
	cp 00eh
	jp nz,patch_gateways_bad
patch_gateways_ok:
	or a
	ret
patch_gateways_bad:
	scf
	ret
load_template_page:
	ld a,(template_cache_ready)
	or a
	jp z,decode_template_page
	ld a,(template_segment)
	call map_p2
	ld hl,CPU_PAGE2_BASE
	ld de,CPU_PAGE1_BASE
	ld bc,PAGE_16K_BYTES
	ldir
	ld a,(original_p2)
	call map_p2
	or a
	ret
decode_template_page:
	ld a,(template_compression)
	or a
	jp z,load_template_raw
	ld hl,(engine_template_offset_lo)
	ld a,(engine_template_offset_hi)
	ld de,(engine_template_packed_size_lo)
	ld b,d
	ld c,e
	call stream_begin
	ret c
	xor a
	ld (zx_mode),a
	ld hl,CPU_PAGE1_BASE
	ld (linear_base),hl
	ld hl,PAGE_16K_BYTES
	xor a
	call zx_set_output_size
	jp zx_decode_stream
load_template_raw:
	ld hl,(engine_template_offset_lo)
	ld a,(engine_template_offset_hi)
	ld de,CPU_PAGE1_BASE
	ld bc,PAGE_16K_BYTES
	call read_at
	jp nz,load_template_bad
	or a
	ret
load_template_bad:
	scf
	ret
load_complete_page:
	ld a,(page_payload_compression)
	or a
	jp z,load_complete_raw
	call begin_page_payload_stream
	ret c
	xor a
	ld (zx_mode),a
	ld hl,CPU_PAGE1_BASE
	ld (linear_base),hl
	ld hl,PAGE_16K_BYTES
	xor a
	call zx_set_output_size
	jp zx_decode_stream
load_complete_raw:
	ld hl,(page_packed_size_lo)
	ld de,PAGE_16K_BYTES
	or a
	sbc hl,de
	jp nz,load_complete_bad
	ld hl,(page_payload_offset_lo)
	ld a,(page_payload_offset_hi)
	ld de,CPU_PAGE1_BASE
	ld bc,PAGE_16K_BYTES
	call read_at
	jp nz,load_complete_bad
	or a
	ret
load_complete_bad:
	scf
	ret
begin_page_payload_stream:
	ld hl,(page_payload_offset_lo)
	ld a,(page_payload_offset_hi)
	ld de,(page_packed_size_lo)
	ld b,d
	ld c,e
	jp stream_begin
apply_sparse_page:
	ld hl,(page_unpacked_size_lo)
	ld a,h
	or l
	ret z
	ld a,(page_flags)
	bit 1,a
	jp z,apply_sparse_payload
	jp sparse_apply_dynamic_range_raw
apply_sparse_payload:
	ld a,(page_payload_compression)
	or a
	jp z,load_sparse_raw
	call begin_page_payload_stream
	ret c
	xor a
	ld (zx_mode),a
	ld hl,CPU_PAGE2_BASE
	ld (linear_base),hl
	ld hl,(page_unpacked_size_lo)
	xor a
	call zx_set_output_size
	call zx_decode_stream
	ret c
	jp apply_sparse_records
load_sparse_raw:
	ld hl,(page_packed_size_lo)
	ld de,(page_unpacked_size_lo)
	or a
	sbc hl,de
	jp nz,sparse_bad
	ld hl,(page_payload_offset_lo)
	ld a,(page_payload_offset_hi)
	ld de,CPU_PAGE2_BASE
	ld bc,(page_unpacked_size_lo)
	call read_at
	jp nz,sparse_bad
apply_sparse_records:
	ld hl,CPU_PAGE2_BASE
	ld (overlay_ptr),hl
	ld hl,(page_unpacked_size_lo)
	ld (overlay_remaining),hl
	ld hl,00000h
	ld (overlay_previous_end),hl
sparse_record_loop:
	ld hl,(overlay_remaining)
	ld a,h
	or l
	jp z,sparse_done
	ld de,00004h
	or a
	sbc hl,de
	jp c,sparse_bad
	ld (overlay_remaining),hl
	ld hl,(overlay_ptr)
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld c,(hl)
	inc hl
	ld b,(hl)
	inc hl
	ld (overlay_ptr),hl
	ld (overlay_offset),de
	ld (overlay_length),bc
	ld a,b
	or c
	jp z,sparse_bad
	ld hl,(overlay_offset)
	ld de,(overlay_previous_end)
	or a
	sbc hl,de
	jp c,sparse_bad
	ld hl,(overlay_offset)
	ld de,(overlay_length)
	add hl,de
	jp c,sparse_bad
	ld (overlay_end),hl
	ld de,(engine_page_size)
	inc de
	or a
	sbc hl,de
	jp nc,sparse_bad
	ld hl,(overlay_remaining)
	ld bc,(overlay_length)
	or a
	sbc hl,bc
	jp c,sparse_bad
	ld (overlay_remaining),hl
	ld a,(dynamic_install_active)
	or a
	jp z,sparse_dynamic_range_ok
	ld hl,(overlay_offset)
	ld de,(engine_page_load_address)
	add hl,de
	ld de,(engine_replace_start)
	or a
	sbc hl,de
	jp c,sparse_bad
sparse_dynamic_range_ok:
	ld hl,(overlay_ptr)
	push hl
	ld de,(overlay_offset)
	ld hl,CPU_PAGE1_BASE
	add hl,de
	ex de,hl
	pop hl
	ld bc,(overlay_length)
	ldir
	ld (overlay_ptr),hl
	ld hl,(overlay_end)
	ld (overlay_previous_end),hl
	jp sparse_record_loop
sparse_done:
	or a
	ret
sparse_bad:
	scf
	ret
apply_hybrid_page:
	ld hl,(current_page)
	ld de,(hpl_position_count)
	call mul16_real
	add hl,hl
	push hl
	ld hl,(hpl_warm_raw)
	ld a,(hpl_warm_raw+2)
	ld de,CPU_PAGE2_BASE
	add hl,de
	adc a,000h
	pop de
	add hl,de
	adc a,000h
	call vram_set_read_address
	ld de,hpol_map_row_cache
	ld bc,(hpl_position_count)
	sla c
	rl b
apply_hybrid_map_read:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	dec bc
	ld a,b
	or c
	jp nz,apply_hybrid_map_read
	ld hl,hpol_map_row_cache
	ld (current_map_ptr),hl
	ld hl,hpol_position_cache
	ld (current_pos_ptr),hl
	ld bc,(hpl_position_count)
apply_page_loop:
	ld a,b
	or c
	ret z
	push bc
	ld hl,(current_pos_ptr)
	ld e,(hl)
	inc hl
	ld d,(hl)
	inc hl
	ld (current_pos_ptr),hl
	ld hl,(current_map_ptr)
	ld c,(hl)
	inc hl
	ld b,(hl)
	inc hl
	ld (current_map_ptr),hl
	push de
	push bc
	call copy_global_block
	pop bc
	pop de
	pop bc
	ret c
	dec bc
	jp apply_page_loop
copy_global_block:
	ld hl,(hpl_hot_count)
	or a
	sbc hl,bc
	jp c,block_not_hot
	jp z,block_not_hot
	call copy_hot_block
	ret
block_not_hot:
	ld hl,(hpl_hot_count)
	ld a,c
	sub l
	ld c,a
	ld a,b
	sbc a,h
	ld b,a
	ld hl,(hpl_warm_count)
	or a
	sbc hl,bc
	jp c,block_not_warm
	jp z,block_not_warm
	call copy_warm_block
	ret
block_not_warm:
	ld hl,(hpl_warm_count)
	ld a,c
	sub l
	ld c,a
	ld a,b
	sbc a,h
	ld b,a
	call copy_cold_block
	ret
copy_hot_block:
	push de
	ld h,b
	ld l,c
	call shift_block_offset
	or a
	jp nz,copy_hot_bad
	push hl
	ld a,h
	and 0c0h
	rlca
	rlca
	ld c,a
	ld b,000h
	ld hl,hot_segments
	add hl,bc
	ld a,(hl)
	call map_p2
	pop hl
	ld a,h
	and 03fh
	or 080h
	ld h,a
	pop de
	ld a,d
	and 03fh
	or 040h
	ld d,a
	ld bc,(hpl_block_size)
	ldir
	or a
	ret
copy_hot_bad:
	pop de
	scf
	ret
copy_warm_block:
	push de
	ld h,b
	ld l,c
	call shift_block_offset
	ld de,CPU_PAGE2_BASE
	add hl,de
	adc a,000h
	call vram_set_read_address
	pop de
	ld hl,CPU_PAGE1_BASE
	add hl,de
	ex de,hl
	ld bc,(hpl_block_size)
copy_warm_loop:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	dec bc
	ld a,b
	or c
	jp nz,copy_warm_loop
	or a
	ret
copy_cold_block:
	push de
	ld a,00eh
	ld d,a
	ld a,(hpl_block_shift)
	ld e,a
	ld a,d
	sub e
	jp c,cold_bad
	ld (cold_div_shift),a
	ld h,b
	ld l,c
cold_div_loop:
	ld a,(cold_div_shift)
	or a
	jp z,cold_div_done
	srl h
	rr l
	dec a
	ld (cold_div_shift),a
	jp cold_div_loop
cold_div_done:
	ld de,(cold_cached_slab)
	or a
	sbc hl,de
	jp z,cold_cache_ready
	add hl,de
	push bc
	call load_cold_slab
	pop bc
	jp c,cold_bad
cold_cache_ready:
	ld h,b
	ld l,c
	call shift_block_offset
	ld a,h
	and 03fh
	or 080h
	ld h,a
	pop de
	ld a,d
	and 03fh
	or 040h
	ld d,a
	ld bc,(hpl_block_size)
	ldir
	or a
	ret
cold_bad:
	pop de
	scf
	ret
load_cold_slab:
	ld (cold_cached_slab),hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,(hpl_cold_table_off)
	add hl,de
	ld a,(hpl_cold_table_off+2)
	adc a,000h
	ld de,(hpol_offset_lo)
	add hl,de
	ld c,a
	ld a,(hpol_offset_hi)
	adc a,c
	ld de,resource_entry
	ld bc,00010h
	call read_at
	jp nz,load_cold_bad
	ld a,(resource_payload_offset_hi)
	cp 001h
	jp nz,load_cold_bad
	ld hl,(resource_payload_offset_lo)
	ld de,PAGE_16K_BYTES_PLUS_ONE
	or a
	sbc hl,de
	jp nc,load_cold_bad
	ld hl,(resource_entry)
	ld a,(resource_fourcc_hi)
	ld de,(hpol_offset_lo)
	add hl,de
	ld c,a
	ld a,(hpol_offset_hi)
	adc a,c
	ld de,(resource_flags)
	ld b,d
	ld c,e
	call stream_begin
	jp c,load_cold_bad
	ld a,(original_p2)
	call map_p2
	xor a
	ld (zx_mode),a
	ld hl,CPU_PAGE2_BASE
	ld (linear_base),hl
	ld hl,(resource_payload_offset_lo)
	xor a
	call zx_set_output_size
	call zx_decode_stream
	jp c,load_cold_bad
	or a
	ret
load_cold_bad:
	scf
	ret
shift_block_offset:
	xor a
	ld b,a
	ld a,(hpl_block_shift)
	ld b,a
	xor a
shift_block_loop:
	add hl,hl
	adc a,a
	djnz shift_block_loop
	ret
