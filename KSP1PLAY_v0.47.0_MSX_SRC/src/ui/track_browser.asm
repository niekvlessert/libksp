; track browser.asm - KSP1PLAY v0.47.0

previous_track:
	di
	nop
	nop
	nop		; executable handoff spacing; preserve unless the path is re-timed
	call restore_process_pages
	call save_interrupt_hook
	call ui_load_hvar_overlay
	ret c
	ld hl,(scc_slot_b+2)
	call KSPMENU_ENTRY_REDRAW_LIST
	ret c
	ld (scc_slot_b+2),hl
	jp ui_install_selected_track
ui_track_menu:
	call ui_restore_text2_mode_only
	xor a
	ld (ui_playback_active),a
	ld (ui_metadata_mode),a
	ld hl,(scc_slot_b+2)
	ld de,(ksp_track_count)
	push hl
	or a
	sbc hl,de
	pop hl
	jp c,ui_track_menu_index_ok
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld (scc_slot_b+2),hl
ui_track_menu_index_ok:
	ld hl,INVALID_WORD
	call ui_draw_track_overview
	call ui_capture_keys
ui_track_menu_wait:
	ei
	halt
	di
	call ui_service_view_redraw
	call ui_poll_action
	or a
	jp z,ui_track_menu_wait
	cp 001h
	jp z,ui_track_menu_cancel_select
	cp 002h
	jp z,ui_track_menu_maybe_choose
	cp 003h
	jp z,ui_track_menu_up
	cp 004h
	jp z,ui_track_menu_down
	cp 005h
	jp z,ui_track_menu_left
	cp 006h
	jp z,ui_track_menu_right
	cp ACTION_CODE_SHOW_METADATA
	jp z,ui_track_menu_show_meta
	cp ACTION_CODE_SHOW_TRACKS
	jp z,ui_track_menu_show_tracks
	cp ACTION_CODE_HELP
	jp z,ui_track_menu_wait
	jp ui_track_menu_wait
ui_track_menu_maybe_choose:
	ld a,(ui_metadata_mode)
	or a
	jp z,ui_track_menu_choose
	jp ui_track_menu_wait
ui_track_menu_up:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_track_menu_wait
	call UI_P3_CALL_CURSOR_UP
	jp ui_track_menu_wait
ui_track_menu_down:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_track_menu_wait
	call UI_P3_CALL_CURSOR_DOWN
	jp ui_track_menu_wait
ui_track_menu_left:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_track_menu_meta_prev
	call ui_track_page_prev
	jp ui_track_menu_wait
ui_track_menu_meta_prev:
	call ui_metadata_page_prev
	jp ui_track_menu_wait
ui_track_menu_right:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_track_menu_meta_next
	call ui_track_page_next
	jp ui_track_menu_wait
ui_track_menu_meta_next:
	call ui_metadata_page_next
	jp ui_track_menu_wait
ui_track_menu_show_meta:
	call ui_switch_to_metadata_view
	jp ui_track_menu_wait
ui_track_menu_show_tracks:
	call ui_enter_track_view
	jp ui_track_menu_wait
ui_track_menu_choose:
	or a
	ret
ui_track_menu_cancel_select:
	scf
	ret
ui_draw_track_overview:
	call restore_process_pages
	call ui_screen5_init
	call ui_draw_frame
	call ui_draw_common_header
	call ui_load_track_page_indices
	ld a,003h
	ld b,011h
	call ui_draw_track_rows
	call ui_build_track_select_line
	ld a,015h
	ld b,00fh
	ld hl,ui_line_buffer
	call ui_text_line
	ld a,016h
	ld b,007h
	ld hl,ui_track_select_footer
	call ui_text_line
	ret
ui_redraw_track_heading:
	call ui_build_track_select_line
	ld a,015h
	ld b,00fh
	ld hl,ui_line_buffer
	jp ui_text_line
ui_redraw_track_selection:
	push hl
	call ui_redraw_track_heading
	pop hl
	ld b,007h
	call ui_find_cached_track_index
	ld hl,(scc_slot_b+2)
	ld b,00fh
	jp ui_find_cached_track_index
	call ui_redraw_track_heading
	call ui_load_track_page_indices
	ld a,003h
	ld b,011h
	jp ui_draw_track_rows
ui_find_cached_track_index:
	ex de,hl
	ld hl,TRACK_CACHE_INDICES
	xor a
ui_draw_track_index_scan:
	push af
	ld a,(hl)
	inc hl
	ld c,(hl)
	inc hl
	cp e
	jp nz,ui_draw_track_index_next
	ld a,c
	cp d
	jp z,ui_draw_track_index_found
ui_draw_track_index_next:
	pop af
	inc a
	cp 011h
	jp c,ui_draw_track_index_scan
	ret
ui_draw_track_index_found:
	pop af
	jp ui_draw_full_track_row
ui_draw_player_track_index:
	jp ui_find_cached_track_index
ui_build_track_select_line:
	call ui_line_clear
	ld hl,ui_track_label
	call ui_line_append_string
	ld hl,(scc_slot_b+2)
	inc hl
	call ui_line_append_u16
	ld hl,ui_track_separator
	call ui_line_append_string
	ld hl,(ui_track_count)
	call ui_line_append_u16
	call ui_line_terminate
	ret
ui_load_track_page_indices:
	xor a
	ld (ui_draw_index),a
ui_load_track_page_indices_loop:
	ld a,(ui_draw_index)
	ld c,a
	ld a,(ui_track_page_ordinal)
	add a,c
	ld c,a
	ld hl,ui_track_count
	cp (hl)
	jp nc,ui_load_track_index_empty
	call ui_track_cache_vram_address
	call vdp_irq_begin
	xor a
	call vram_set_read_address
	in a,(PORT_VDP_DATA)
	ld e,a
	push af
	pop af
	in a,(PORT_VDP_DATA)
	ld d,a
	jp ui_finish_visible_track_map_read
	db 0		; fixed layout byte after the jump
ui_load_track_index_empty:
	ld de,INVALID_WORD
ui_load_track_index_store:
	ld a,(ui_draw_index)
	add a,a
	ld l,a
	ld h,000h
	ld bc,TRACK_CACHE_INDICES
	add hl,bc
	ld (hl),e
	inc hl
	ld (hl),d
	ld a,(ui_draw_index)
	inc a
	ld (ui_draw_index),a
	cp 011h
	jp c,ui_load_track_page_indices_loop
	ld hl,(TRACK_CACHE_INDICES)
	ld (ui_track_top),hl
	ret
ui_track_cache_vram_address:
	ld l,a
	ld h,000h
	add hl,hl
	push hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	pop de
	add hl,de
	ld de,UI_TRACK_CACHE_VRAM_BASE
	add hl,de
	ret
ui_load_track_row_cache:
	ld (ui_draw_index),a
	ld c,a
	ld a,(ui_track_page_ordinal)
	add a,c
	ld c,a
	ld hl,ui_track_count
	cp (hl)
	jp nc,ui_read_full_track_empty
	call ui_track_cache_vram_address
	inc hl
	inc hl
	call vdp_irq_begin
	xor a
	call vram_set_read_address
	ld de,ui_line_buffer
	ld b,040h
ui_read_full_track_chars:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	djnz ui_read_full_track_chars
	call vdp_irq_end
	xor a
	ld (ui_line_buffer+64),a
	ret
ui_read_full_track_empty:
	jp ui_line_fill_spaces
ui_menu:
	call ui_scan_files
	call menu_ovl_refresh
	xor a
	ld (ui_menu_selected),a
	ld (ui_menu_top),a
	call ui_restore_text2_mode_only
	call ui_draw_game_browser
	call ui_capture_keys
ui_menu_wait_action:
	call wait_vblank
	call ui_poll_action
	or a
	jp z,ui_menu_wait_action
	cp 001h
	jp z,ui_menu_cancel
	cp 002h
	jp z,ui_menu_choose
	cp 003h
	jp z,ui_menu_up
	cp 004h
	jp z,ui_menu_down
	cp 005h
	jp z,ui_menu_left
	cp 006h
	jp z,ui_menu_right
	jp ui_menu_wait_action
ui_menu_up:
	call ui_menu_move_up_dynamic
	jp ui_menu_wait_action
ui_menu_down:
	ld a,(ui_menu_selected)
	inc a
	ld b,a
	ld a,(ui_file_count)
	cp b
	jp z,ui_menu_wait_action
	call ui_tracks_per_page
	ld c,a
	ld a,(ui_menu_top)
	add a,c
	cp b
	jp z,ui_menu_wait_action
	ld a,b
	call ui_menu_store_selection
	jp ui_menu_wait_action
ui_menu_left:
	call pager_prev
	jp ui_menu_wait_action
ui_menu_right:
	call ui_menu_page_next_dynamic
	jp ui_menu_wait_action
ui_menu_choose:
	ld a,(ui_file_count)
	or a
	jp z,ui_menu_wait_action
	ld a,(ui_menu_selected)
	call ui_filename_slot_address
	ld de,filename
	ld b,00dh
ui_menu_copy_name:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	or a
	jp z,ui_menu_name_done
	djnz ui_menu_copy_name
	xor a
	ld (de),a
ui_menu_name_done:
	or a
	ret
ui_menu_cancel:
	scf
	ret
ui_scan_files:
	xor a
	ld (ui_file_count),a
	ld hl,ui_fib
	ld de,ui_fib+1
	ld bc,00024h
	ld (hl),000h
	ldir
	ld hl,ui_fib+1
	ld b,008h
	ld a,03fh
ui_scan_wild_name:
	ld (hl),a
	inc hl
	djnz ui_scan_wild_name
	ld (hl),04bh
	inc hl
	ld (hl),053h
	inc hl
	ld (hl),050h
	ld de,io_buffer
	ld c,01ah
	call BDOS
	ld de,ui_fib
	ld c,011h
	call BDOS
	or a
	jp nz,ui_scan_done
ui_scan_store:
	ld a,(ui_file_count)
	cp 028h
	jp nc,ui_scan_done
	push af
	call ui_filename_slot_address
	ex de,hl
	ld hl,io_buffer+001h
	ld b,008h
ui_scan_copy_base:
	ld a,(hl)
	inc hl
	cp 020h
	jp z,ui_scan_skip_base_tail
	ld (de),a
	inc de
	djnz ui_scan_copy_base
	jp ui_scan_add_dot
ui_scan_skip_base_tail:
	dec b
	jp z,ui_scan_add_dot
ui_scan_skip_base_tail_advance:
	inc hl
	djnz ui_scan_skip_base_tail_advance
ui_scan_add_dot:
	ld a,02eh
	ld (de),a
	inc de
	ld hl,legacy_menu_help
	ld bc,00003h
	ldir
	xor a
	ld (de),a
	pop af
	inc a
	ld (ui_file_count),a
	ld c,012h
	call BDOS
	or a
	jp z,ui_scan_store
ui_scan_done:
	ret
ui_filename_slot_address:
	ld e,a
	ld d,000h
	ld h,d
	ld l,e
	add hl,hl
	add hl,hl
	push hl
	add hl,hl
	pop de
	add hl,de
	ld e,a
	ld d,000h
	add hl,de
	ld de,ui_file_names
	add hl,de
	ret
	ret
ui_draw_game_browser:
	call ui_screen5_init
	call ui_draw_frame
	call ui_draw_menu_header
	call ui_draw_menu_rows
	ld a,016h
	ld b,007h
	ld hl,legacy_menu_help_short
	jp ui_text_line
ui_draw_menu_rows:
	xor a
	ld (ui_draw_index),a
ui_draw_menu_rows_loop:
	ld a,(ui_draw_index)
	ld c,a
	ld a,(ui_menu_top)
	add a,c
	ld c,a
	ld a,(ui_file_count)
	cp c
	jp z,ui_draw_menu_row_empty
	jp c,ui_draw_menu_row_empty
	ld a,c
	jp ui_draw_menu_row_fetch
ui_draw_menu_row_empty:
	ld a,0ffh
	ld c,a
ui_draw_menu_row_fetch:
	call menu_ovl_get_line
	ld a,c
	cp 0ffh
	jp z,ui_draw_menu_row_ready
	ld a,(ui_menu_selected)
	cp c
	jp nz,ui_draw_menu_row_ready
	ld a,03eh
	ld (ui_string_buffer+1),a
	ld a,03ch
	ld (ui_string_buffer+62),a
ui_draw_menu_row_ready:
	ld a,(ui_draw_index)
	add a,003h
	ld b,00fh
	ld hl,ui_string_buffer
	call ui_text_line
	ld a,(ui_draw_index)
	inc a
	ld (ui_draw_index),a
	cp 011h
	jp c,ui_draw_menu_rows_loop
	ret
ui_redraw_track_page:
	call restore_process_pages
	call ui_load_track_page_indices
	call ui_screen5_init
	call ui_draw_frame
	call ui_draw_common_header
	ld a,003h
	ld b,011h
	call ui_draw_track_rows
	jp ui_finish_player_screen
ui_draw_selected_track_title:
	ld hl,ui_file_names
	ld a,020h
	ld (hl),a
	push hl
	ld a,015h
	ld b,003h
	ld c,03ah
	call ui_write_field
	pop hl
	ld (hl),020h
	ret
ui_draw_track_rows:
	ld (ui_draw_row),a
	xor a
	ld (ui_draw_index),a
ui_draw_cached_tracks_loop:
	push bc
	ld a,(ui_draw_index)
	call ui_draw_full_track_row
	ld a,(ui_draw_index)
	inc a
	ld (ui_draw_index),a
	ld a,(ui_draw_row)
	inc a
	ld (ui_draw_row),a
	pop bc
	djnz ui_draw_cached_tracks_loop
	ld a,011h
	ld (ui_incremental_row),a
	ret
ui_draw_full_track_row:
	push af
	call ui_load_track_row_cache
	pop af
	ld c,a
	add a,003h
	push bc
	ld b,003h
	ld c,04ah
	ld hl,ui_line_buffer
	call ui_write_field
	pop bc
	ld a,c
	add a,003h
	ld b,002h
	ld c,020h
	call ui_write_char
	ld a,(ui_draw_index)
	add a,a
	ld l,a
	ld h,000h
	ld de,TRACK_CACHE_INDICES
	add hl,de
	ld e,(hl)
	inc hl
	ld d,(hl)
	ld hl,(scc_slot_b+2)
	or a
	sbc hl,de
	ret nz
	ld a,(ui_draw_index)
	ld (ui_cursor_row),a
	add a,003h
	ld b,002h
	ld c,03eh
	call ui_write_char
	ld a,(ui_draw_index)
	add a,003h
	ld b,04bh
	ld c,03ch
	jp ui_write_char
ui_read_track_title:
	call ui_line_clear
	ld a,020h
	call ui_line_append_char
	ld hl,(ui_track_index)
	call ui_line_append_u16
	ld a,020h
	call ui_line_append_char
	ld hl,(ui_track_index)
	ld de,(ksp_track_entry_size)
	call mul16x16_24
	ld c,a
	ld de,(ksp_track_table_offset_lo)
	add hl,de
	ld a,(ksp_track_table_offset_hi)
	adc a,c
	ld de,ui_track_entry
	ld bc,00020h
	call read_at
	jp nz,ui_track_title_done
	ld hl,(ui_track_entry+12)
	ld a,(ui_track_entry+14)
	call ui_read_ksp_string
	ld hl,ui_string_buffer
ui_track_append_title:
	ld a,(hl)
	or a
	jp z,ui_track_title_done
	call ui_line_append_char
	inc hl
	jp ui_track_append_title
ui_track_title_done:
	ld a,(ui_line_pos)
	ld e,a
	ld d,000h
	ld hl,ui_line_buffer
	add hl,de
	xor a
	ld (hl),a
	ret
ui_read_ksp_string:
	ld c,a
	ld de,(ksp_string_table_offset_lo)
	add hl,de
	ld a,(ksp_string_table_offset_hi)
	adc a,c
	ld de,ui_string_buffer
	ld bc,00040h
	call read_at
	jp nz,ui_string_empty
	ld hl,ui_string_buffer
	ld b,03fh
ui_string_sanitize:
	ld a,(hl)
	or a
	ret z
	cp 020h
	jp nc,ui_string_printable
	xor a
	ld (hl),a
	ret
ui_string_printable:
	cp 080h
	jp c,ui_string_next
	ld (hl),03fh
ui_string_next:
	inc hl
	djnz ui_string_sanitize
	xor a
	ld (hl),a
	ret
ui_string_empty:
	xor a
	ld (ui_string_buffer),a
	ret
