; package loader.asm - KSP1PLAY v0.47.0

ui_load_pack:
	ei
	xor a
	ld (ui_error_code),a
	ld (space_previous+2),a
	ld (engine_running),a
	ld (hybrid_ready),a
	ld (file_cache_ready),a
	ld (template_cache_ready),a
	ld (refresh_saved),a
	ld (HVAR_PRESENT),a
	ld (ui_meta_state),a
	ld (ui_meta_scroll),a
	ld (ui_meta_count),a
	ld (ui_meta_length),a
	ld (ui_meta_length+1),a
	ld hl,INVALID_WORD
	ld (PREPARED_ENGINE),hl
	call fcb_open_current
	jp c,ui_load_file_bad
	xor a
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld de,ksp_header
	ld bc,00050h
	call read_at
	jp nz,ui_load_file_bad
	call validate_header
	jp c,ui_load_format_bad
	ld hl,(ksp_track_count)
	ld a,h
	or l
	jp z,ui_load_track_bad
	call ui_load_hvar_overlay
	jp c,ui_load_memory_bad
	call KSPMENU_ENTRY_VDP_SETUP
	jp c,ui_load_format_bad
	call KSPMENU_SETUP_FROM_R1_OPERAND
	call KSPMENU_JUMP_RESTORE_PLAYER_UI
	ld hl,(VISIBLE_TRACK_COUNT)
	ld a,h
	or l
	jp z,ui_load_track_bad
	ld hl,(ksp_default_track)
	call ui_load_hvar_overlay
	jp c,ui_load_memory_bad
	call MENU_SETUP_VDP
	jp c,ui_load_track_bad
	ld (scc_slot_b+2),hl
	call select_track
	jp c,ui_load_profile_bad
	ld a,(menu_launch)
	or a
	ret nz
	call ui_install_selected_track
	ret
ui_load_prepare_fail:
	ld a,(hardware_error_code)
	or a
	jp nz,ui_load_hardware_bad
	jp ui_load_memory_bad

; Materialize the selected engine/profile into mapper RAM and prepare sparse or
; runtime resources before any INIT/PLAY call is allowed.
ui_prepare_selected_engine:
	ld hl,(CURRENT_ENGINE)
	ld de,(PREPARED_ENGINE)
	or a
	sbc hl,de
	ld a,(space_previous+2)
	jp nz,ui_prepare_engine_new
	or a
	ret nz
ui_prepare_engine_new:
	call release_engine_resources
	call validate_engine_profile
	jp c,ui_prepare_profile_bad
	call validate_required_hardware
	jp c,ui_prepare_hardware_bad
	call allocate_page3_workram_segment
	jp c,ui_prepare_memory_bad
	call configure_engine_refresh
	call find_hpol_resource
	jp c,ui_prepare_sparse
	call load_hpl_header
	jp c,ui_prepare_profile_bad
	call hpol_map_reset
	jp c,ui_prepare_memory_bad
	call allocate_hot_segments
	jp c,ui_prepare_memory_bad
	ld a,004h
	ld (decode_stage),a
	call preload_hybrid_pool
	jp c,ui_prepare_decode_bad
	ld a,001h
	ld (hybrid_ready),a
	jp ui_prepare_ready
ui_prepare_sparse:
	call preload_file_cache
	call allocate_template_segment
	jp c,ui_prepare_memory_bad
	ld a,001h
	ld (decode_stage),a
	call preload_template_page
	jp c,ui_prepare_decode_bad
ui_prepare_ready:
	ld a,001h
	ld (space_previous+2),a
	ld hl,(CURRENT_ENGINE)
	ld (PREPARED_ENGINE),hl
	or a
	ret
ui_prepare_profile_bad:
	xor a
	ld (hardware_error_code),a
	scf
	ret
ui_prepare_hardware_bad:
	scf
	ret
ui_prepare_memory_bad:
	xor a
	ld (hardware_error_code),a
	scf
	ret
ui_prepare_decode_bad:
	xor a
	ld (hardware_error_code),a
	scf
	ret

; Install/restart the selected track using the already prepared package data.
; UI feedback may run around this operation, never inside an engine PLAY callback.
ui_install_selected_track:
	call ui_begin_track_change
	ld hl,(scc_slot_b+2)
	call select_track
	jp c,ui_load_track_bad
	call ui_prepare_selected_engine
	jp c,ui_load_prepare_fail
	call page_runtime_available
	jp z,ui_track_preload_done
	call RECON_ENTRY_PRELOAD_TRACK
	jp c,ui_load_memory_bad
ui_track_preload_done:
	ld hl,(scc_slot_b+2)
	ld (ui_track_index),hl
	call ui_read_track_title
	ld hl,ui_line_buffer
	ld de,ui_file_names
	ld bc,00041h
	ldir
	call ui_load_hvar_overlay
	jp c,ui_load_memory_bad
	call KSPMENU_SETUP_FROM_R7
	call install_current_track
	jp c,ui_load_decode_bad
	ld hl,(scc_slot_b+2)
	ld (ui_previous_track),hl
	or a
	ret
ui_load_file_bad:
	ld a,001h
	jp ui_load_fail
ui_load_format_bad:
	ld a,002h
	jp ui_load_fail
ui_load_profile_bad:
	ld a,003h
	jp ui_load_fail
ui_load_hardware_bad:
	ld a,004h
	jp ui_load_fail
ui_load_memory_bad:
	ld a,005h
	jp ui_load_fail
ui_load_track_bad:
	ld a,006h
	jp ui_load_fail
ui_load_decode_bad:
	ld a,007h
ui_load_fail:
	ld (ui_error_code),a
	scf
	ret
hpol_map_reset:
	xor a
	ld (hpol_map_allocated),a
	ret
hpol_map_release:
	ld a,(hpol_map_allocated)
	or a
	ret z
	ld a,(hpol_map_segment)
	call mapper_free_primary
	xor a
	ld (hpol_map_allocated),a
	ret
