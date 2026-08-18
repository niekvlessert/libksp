; game intro.asm - KSP1PLAY v0.47.0

ui_page3_zero_if_declared:
	ld a,(engine_entry)
	and 020h
	ret z
	ld a,(page3_workram_profile)
	or a
	ret z
	di
	ld a,(engine_p3_segment)
	out (PORT_MAPPER_P3),a
	xor a
	ld hl,KSPOS_RT_KSPOS_DISK_CALL
	ld (hl),a
	ld de,KSPOS_RT_KSPOS_DISK_CALL+1
	ld bc,PAGE_16K_CLEAR_BYTES_AFTER_0
	ldir
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ret
ui_init_track_engine:
	call ui_page3_zero_if_declared
	call prepare_opl4_init
	call call_init
	ld a,(engine_required_hardware)
	and 00eh
	cp 002h
	jp nz,ui_init_track_engine_finish
	call map_scc_page2
	ld a,03fh
	ld (SCC_ENABLE_REG),a
ui_init_track_engine_finish:
	jp prepare_engine_page2
ui_game_intro:
	call ui_restore_text2_mode_only
	xor a
	ld (ui_playback_active),a
	ld (ui_metadata_mode),a
	call ui_screen5_init
	call ui_draw_game_intro_frame
	call ui_draw_common_header
	call ui_load_hvar_overlay
	jp c,ui_game_intro_draw_footer
	call KSPMENU_SETUP_FROM_R2
ui_game_intro_draw_footer:
	ld a,016h
	ld b,01ah
	ld c,01ch
	ld hl,ui_intro_footer
	call ui_write_field
	call SERVICE_RT_SERVICE_GAME_INTRO_SPLIT
	jp nc,ui_game_intro_dispatch_action
	call ui_capture_keys
ui_game_intro_wait_action:
	ei
	halt
	di
	call ui_poll_action
	or a
	jp z,ui_game_intro_wait_action
ui_game_intro_dispatch_action:
	cp 001h
	jp z,ui_game_intro_cancel
	cp 002h
	jp z,ui_game_intro_ok
	cp ACTION_CODE_SHOW_TRACKS
	jp z,ui_game_intro_tracks
	cp ACTION_CODE_SHOW_METADATA
	jp z,ui_game_intro_meta
	jp ui_game_intro_wait_action
ui_game_intro_tracks:
	jp ui_track_menu
ui_game_intro_meta:
	call ui_enter_metadata_view
	call ui_capture_keys
	jp ui_track_menu_wait
ui_game_intro_ok:
	or a
	ret
ui_game_intro_cancel:
	scf
	ret
ui_draw_cached_metadata_row_impl:
	push af
	ld c,a
	ld a,(ui_meta_scroll)
	add a,c
	ld c,a
	ld a,(ui_meta_count)
	cp c
	jp z,ui_draw_meta_blank
	jp c,ui_draw_meta_blank
ui_draw_cached_meta_source:
	ld a,c
	ld l,a
	ld h,000h
	add hl,hl
	push hl
	add hl,hl
	add hl,hl
	push hl
	add hl,hl
	add hl,hl
	add hl,hl
	pop de
	add hl,de
	pop de
	add hl,de
	ld de,META_CACHE_VRAM_BASE
	add hl,de
	call vdp_irq_begin
	xor a
	call vram_set_read_address
	ld de,ui_line_buffer
	ld b,04ah
ui_draw_meta_read_loop:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	djnz ui_draw_meta_read_loop
	call vdp_irq_end
	ld hl,ui_line_buffer
	jp ui_draw_meta_write
ui_draw_meta_blank:
	call ui_line_clear
	ld hl,ui_line_buffer
ui_draw_meta_write:
	pop af
	add a,003h
	ld b,003h
	ld c,04ah
	jp ui_write_field
ui_draw_cached_help_row_resident:
	add a,003h
	push af
	add a,096h
	ld c,a
	jp ui_draw_cached_meta_source
ui_draw_game_intro_frame:
	xor a
	ld bc,UI_FRAME_OUTER_GLYPHS
; HPOL_POSITION_CACHE begins here. Package preparation temporarily reuses the
; stopped-state UI address range as scratch RAM; never use that cache while this
; presentation code is executing.
hpol_position_cache:
	call ui_draw_hline
	ld a,001h
	ld b,000h
	ld c,016h
	call ui_write_char
	ld a,001h
	ld b,04fh
	ld c,016h
	call ui_write_char
	ld a,002h
	ld bc,UI_FRAME_BOTTOM_GLYPHS
	jp ui_draw_hline
	ds 3,0		; fixed layout gap
ui_switch_to_metadata_view:
	ld a,(ui_cursor_row)
	add a,003h
	push af
	ld b,002h
	ld c,020h
	call ui_write_char
	pop af
	ld b,04bh
	ld c,020h
	call ui_write_char
	jp ui_enter_metadata_view
prepare_engine_page2_for_install:
	ld a,(engine_p2_segment_allocated)
	or a
	jp z,prepare_engine_page2
	jp RECON_PREPARE_PAGE2_COPY
ui_finish_visible_track_map_read:
	call vdp_irq_end
	jp ui_load_track_index_store
ui_show_loading_track_message:
	ld a,(ui_playback_active)
	or a
	ret z
	ld a,(ui_metadata_mode)
	or a
	ret nz
	ld a,015h
	ld b,003h
	ld c,049h
	ld hl,ui_loading_track_text
	jp ui_write_field
	ds 2,0		; fixed layout gap before text data
ui_loading_track_text:
	db "LOADING TRACK...                                                         ",0
	ds 342,0		; 368a-37df zero-filled reserved/data bytes (compact NOP run)
hpol_map_row_cache:
	ds 512,0		; 37e0-39df zero-filled reserved/data bytes (compact NOP run)
capture_secondary_slot_state:
	rlca
	rlca
	and 003h
	ld e,a
	ld d,000h
	ld hl,BIOS_EXPTBL
	add hl,de
	bit 7,(hl)
	ld a,001h
	ret z
	ld a,(SECONDARY_SLOT_REGISTER)
	cpl
	ld (probe_base_byte),a
	ld a,081h
	ret
	ds 6,0		; fixed layout gap

; Verify that the hardware selected by the KSP/HVAR view is actually available
; (including dual-SCC slot separation and OPL4 requirements).
