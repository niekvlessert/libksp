; TEXT 2 setup, line formatting and frame rendering.

ui_enable_text80:
	call restore_process_pages
	ld a,050h
	ld (BIOS_LINL40),a
	push ix
	push iy
	ld ix,BIOS_INITXT
	call call_main_bios
	pop iy
	pop ix
	ld a,050h
	ld (BIOS_LINLEN),a
	ld a,018h
	ld (BIOS_CRTCNT),a
	xor a
	ld (BIOS_CSRX),a
	ld (BIOS_CSRY),a
	inc a
	ld (ui_text80_mode),a
	call ui_restore_text2_mode_only
	jp ui_text80_clear
ui_restore_text2_mode_only:
	ld a,001h
	ld (ui_text80_mode),a
	di
	ld a,004h
	ld c,000h
	call ui_write_vdp_register
	ld a,070h
	ld c,001h
	call ui_write_vdp_register
	ld a,003h
	ld c,002h
	call ui_write_vdp_register
	ld a,027h
	ld c,003h
	call ui_write_vdp_register
	ld a,002h
	ld c,004h
	call ui_write_vdp_register
	ld a,0f0h
	ld c,007h
	call ui_write_vdp_register
	xor a
	ld c,00ah
	call ui_write_vdp_register
	xor a
	ld c,00bh
	call ui_write_vdp_register
	xor a
	ld c,00dh
	call ui_write_vdp_register
	xor a
	ld c,00eh
	call ui_write_vdp_register
	ei
	ret
ui_text80_clear:
	call vdp_irq_begin
	ld hl,ENGINE_DIRECT_CALL_PATCH
	xor a
	call vram_set_write_address
	ld bc,UI_TEXT80_NAME_TABLE_BYTES
	ld d,020h
ui_text80_clear_loop:
	ld a,d
	out (PORT_VDP_DATA),a
	dec bc
	ld a,b
	or c
	jp nz,ui_text80_clear_loop
	ld hl,MENU_GFX_SIZE
	xor a
	call vram_set_write_address
	ld b,0f0h
	xor a
ui_text80_blink_loop:
	out (PORT_VDP_DATA),a
	djnz ui_text80_blink_loop
	jp vdp_irq_end
ui_text80_render:
	ld de,ui_line_buffer
	ld b,040h
ui_text80_copy:
	ld a,(hl)
	or a
	jp z,ui_text80_pad
	cp 020h
	jp c,ui_text80_pad
	cp 080h
	jp c,ui_text80_store
	ld a,03fh
ui_text80_store:
	ld (de),a
	inc hl
	inc de
	djnz ui_text80_copy
	jp ui_text80_write
ui_text80_pad:
	ld a,020h
ui_text80_pad_loop:
	ld (de),a
	inc de
	djnz ui_text80_pad_loop
ui_text80_write:
	ld a,(ui_text_row)
	ld l,a
	ld h,000h
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld d,h
	ld e,l
	add hl,hl
	add hl,hl
	add hl,de
	ld de,00008h
	add hl,de
	call vdp_irq_begin
	xor a
	call vram_set_write_address
	ld hl,ui_line_buffer
	ld b,040h
ui_text80_write_loop:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	djnz ui_text80_write_loop
	jp vdp_irq_end
ui_prepare_game_title:
	call vdp_irq_begin
	ld hl,decode_stage
	xor a
	call vram_set_read_address
	ld de,ui_string_buffer
	ld b,040h
ui_title_meta_read:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	djnz ui_title_meta_read
	call vdp_irq_end
	xor a
	ld (ui_string_buffer+63),a
	ld hl,ui_string_buffer
	ld b,00ch
ui_title_find_colon:
	ld a,(hl)
	or a
	jp z,ui_title_use_filename
	cp 03ah
	jp z,ui_title_after_colon
	inc hl
	djnz ui_title_find_colon
	jp ui_title_use_filename
ui_title_after_colon:
	inc hl
ui_title_skip_space:
	ld a,(hl)
	cp 020h
	jp nz,ui_title_store
	inc hl
	jp ui_title_skip_space
ui_title_use_filename:
	ld hl,filename
ui_title_store:
	push hl
	call vdp_irq_begin
	ld hl,UI_GAME_TITLE_VRAM
	xor a
	call vram_set_write_address
	pop hl
	ld b,030h
	ld c,000h
ui_title_store_loop:
	ld a,c
	or a
	jp nz,ui_title_store_zero
	ld a,(hl)
	or a
	jp nz,ui_title_store_char
	inc c
ui_title_store_zero:
	xor a
	out (PORT_VDP_DATA),a
	djnz ui_title_store_loop
	jp vdp_irq_end
ui_title_store_char:
	out (PORT_VDP_DATA),a
	inc hl
	djnz ui_title_store_loop
	jp vdp_irq_end
	ret
ui_player_header:
ui_header_brand:
	; Literal title text.
	db "-->KSP1Play<--",0
ui_text80_mode:
	db 0
ui_loop_enabled:
	db 0
install_runtime_images:
	ld hl,recon_overlay_image
	ld de,RECON_ENTRY_APPLY
	ld bc,RECON_OVERLAY_MAX
	ldir
	ld hl,ui_p3_helper_image
	ld de,UI_P3_CALL_CURSOR_UP
	ld bc,000a4h
	ldir
	ld hl,service_overlay_head_image
	ld de,SERVICE_OVL_UPLOAD_MWK
	ld bc,SERVICE_OVERLAY_HEAD_MAX
	ldir
	ld hl,service_overlay_tail_image
	ld de,SERVICE_RT_SERVICE_GAME_INTRO_SPLIT
	ld bc,SERVICE_TAIL_COPY_BYTES
	ldir
	jp RECON_ENTRY_BACKUP_SPLIT
ui_finish_player_screen:
	call ui_draw_selected_track_title
	call ui_draw_help_hint
	jp ui_draw_playback_time
ui_reset_package_state:
	xor a
	ld (file_open),a
	ld (hot_segment_count),a
	ld (hot_needed_count),a
	ld (space_previous+2),a
	ld (engine_running),a
	ld (hybrid_ready),a
	ld (file_cache_ready),a
	ld (template_cache_ready),a
	ld (template_segment_allocated),a
	ld (engine_p3_segment_allocated),a
	ld (hpol_map_allocated),a
	ld (mwk_segment_allocated),a
	ld (dynamic_profile),a
	ld (page2_runtime_profile),a
	ld (page3_workram_profile),a
	ld (dynamic_install_active),a
	ld (gateway_patch_flags),a
	ld (refresh_saved),a
	ld (stream_source),a
	ld (stream_vdp_guard),a
	ld (current_page),a
	ld (current_page+1),a
	ld (current_song_id),a
	ld (current_song_id+1),a
	ld a,0ffh
	ld (hot_write_mapped),a
	ld (hot_read_mapped),a
	ld hl,INVALID_WORD
	xor a
	ld (ui_loop_enabled),a
	ld (ui_audio_muted),a
	ld (ui_cursor_row),a
	ld (ui_track_page_ordinal),a
	ld (ui_base_seconds),a
	ld (ui_base_seconds+1),a
	ld a,002h
	ld (ui_loop_count),a
	ret
pager_prev:
	ld a,(ui_menu_top)
	or a
	ret z
	ld b,a
	call ui_tracks_per_page
	ld c,a
	ld a,b
	sub c
	jp ui_menu_page_store
ui_menu_page_next_dynamic:
	call ui_tracks_per_page
	ld b,a
	ld a,(ui_menu_top)
	add a,b
	ld b,a
	ld a,(ui_file_count)
	cp b
	ret z
	ret c
	ld a,b
ui_menu_page_store:
	ld (ui_menu_top),a
	ld (ui_menu_selected),a
	jp ui_draw_menu_rows
; ui_begin_track_change
; Stops playback, updates selection, installs the new track, then returns to playback UI.
ui_begin_track_change:
	call ui_show_loading_track_message
	jp stop_and_mute
