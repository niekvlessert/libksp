; Track/metadata paging and playback-time presentation.

ui_enter_metadata_view:
	ld a,001h
	ld (ui_metadata_mode),a
	call ui_draw_metadata_page_header
	ld a,(ui_playback_active)
	or a
	jp z,ui_meta_selector_footer
	call ui_draw_help_hint
	jp ui_metadata_enter_done
ui_meta_selector_footer:
	ld a,016h
	ld b,007h
	ld hl,ui_meta_select_footer
	call ui_text_line
ui_metadata_enter_done:
	xor a
	ld (ui_incremental_row),a
	ret
ui_metadata_redraw:
	call ui_draw_metadata_page_header
	jp ui_metadata_enter_done
ui_enter_track_view:
	xor a
	ld (ui_metadata_mode),a
	ld a,(ui_playback_active)
	or a
	jp z,ui_draw_track_overview
	call ui_draw_selected_track_title
	call ui_draw_help_hint
	call ui_draw_playback_time
	xor a
	ld (ui_incremental_row),a
	ret
ui_toggle_metadata_track_view:
	ld a,(ui_metadata_mode)
	or a
	jp z,ui_toggle_to_tracks
	call ui_draw_metadata_page_header
	call ui_draw_help_hint
	xor a
	ld (ui_incremental_row),a
	jp ui_draw_playback_time
ui_toggle_to_tracks:
	jp ui_enter_track_view
ui_metadata_page_prev:
	ld a,(ui_meta_scroll)
	or a
	ret z
	sub UI_TRACK_ROWS_PER_PAGE
	jp nc,ui_metadata_prev_clamped
	xor a
ui_metadata_prev_clamped:
	ld (ui_meta_scroll),a
	jp ui_metadata_redraw
ui_metadata_page_next:
	ld a,(ui_meta_scroll)
	add a,UI_TRACK_ROWS_PER_PAGE
	ld b,a
	ld a,(ui_meta_count)
	cp b
	ret c
	ret z
	ld a,b
	ld (ui_meta_scroll),a
	jp ui_metadata_redraw
ui_draw_metadata_page_header:
	ld hl,ui_line_buffer
	ld (hl),04dh
	inc hl
	ld (hl),045h
	inc hl
	ld (hl),054h
	inc hl
	ld (hl),041h
	inc hl
	ld (hl),020h
	inc hl
	ld (hl),050h
	inc hl
	ld (hl),041h
	inc hl
	ld (hl),047h
	inc hl
	ld (hl),045h
	inc hl
	ld (hl),020h
	inc hl
	ld a,(ui_meta_scroll)
	ld b,031h
ui_meta_page_current_loop:
	cp 011h
	jp c,ui_meta_page_current_done
	sub UI_TRACK_ROWS_PER_PAGE
	inc b
	jp ui_meta_page_current_loop
ui_meta_page_current_done:
	ld (hl),b
	inc hl
	ld (hl),02fh
	inc hl
	ld a,(ui_meta_count)
	or a
	jp nz,ui_meta_page_total_nonzero
	ld b,030h
	jp ui_meta_page_total_done
ui_meta_page_total_nonzero:
	dec a
	ld b,031h
ui_meta_page_total_loop:
	cp 011h
	jp c,ui_meta_page_total_done
	sub UI_TRACK_ROWS_PER_PAGE
	inc b
	jp ui_meta_page_total_loop
ui_meta_page_total_done:
	ld (hl),b
	inc hl
	xor a
	ld (hl),a
	ld a,015h
	ld b,003h
	ld c,04ah
	ld hl,ui_line_buffer
	jp ui_write_field
ui_track_page_prev:
	ld a,(ui_track_page_ordinal)
	or a
	ret z
	sub UI_TRACK_ROWS_PER_PAGE
	jp nc,ui_track_page_apply
	xor a
	jp ui_track_page_apply
ui_track_page_next:
	ld a,(ui_track_page_ordinal)
	add a,UI_TRACK_ROWS_PER_PAGE

	ld b,a
	ld hl,ui_track_count
	cp (hl)
	ret nc
	ld a,b
ui_track_page_apply:
	ld (ui_track_page_ordinal),a
	call ui_load_track_page_indices
	ld hl,(TRACK_CACHE_INDICES)
	ld (scc_slot_b+2),hl
	xor a
	ld (ui_cursor_row),a
	call ui_redraw_track_heading
	ld a,(ui_playback_active)
	or a
	jp z,ui_track_page_draw_rows
	xor a
	ld (ui_incremental_row),a
	ret
ui_track_page_draw_rows:
	ld a,003h
	ld b,011h
	jp ui_draw_track_rows
ui_help_action:
	ld a,(ui_incremental_row)
	inc a
	jp z,ui_help_cycle_close
	xor a
ui_help_cycle_loop:
	push af
	call ui_draw_cached_help_row_resident
	pop af
	inc a
	cp 007h
	jp nz,ui_help_cycle_loop
	ld a,0ffh
	ld (ui_incremental_row),a
	ret
ui_help_cycle_close:
	jp ui_toggle_metadata_track_view
ui_draw_help_hint:
	ld a,016h
	ld b,046h
	ld c,006h
	ld hl,ui_play_help
	jp ui_write_field
ui_service_view_redraw:
	ld a,(ui_incremental_row)
	cp 011h
	ret nc
	push af
	ld a,(ui_metadata_mode)
	or a
	jp z,ui_incremental_draw_track_row
	pop af
	push af
	call ui_draw_cached_metadata_row
	jp ui_incremental_row_done
ui_incremental_draw_track_row:
	pop af
	push af
	call ui_draw_full_track_row
ui_incremental_row_done:
	pop af
	inc a
	ld (ui_incremental_row),a
	ret
ui_draw_cached_metadata_row:
	jp ui_draw_cached_metadata_row_impl
ui_draw_playback_time:
	call ui_build_playback_time_line
	ld hl,ui_line_buffer+5
	ld a,015h
	ld b,03fh
	ld c,00dh
	jp ui_write_field
ui_poll_playback_action:
	call playback_time_tick
	ld a,(ui_auto_advance_pending)
	or a
	jp z,ui_poll_playback_keys
	xor a
	ld (ui_auto_advance_pending),a
	ld a,00eh
	ret
ui_poll_playback_keys:
	jp ui_poll_action
playback_time_reset:
	xor a
	ld (playback_frame_counter),a
	ld (playback_elapsed_seconds_live),a
	ld (playback_elapsed_seconds_live+1),a
	ld (ui_auto_advance_pending),a
	ret
playback_time_tick:
	ld a,(ui_audio_muted)
	or a
	ret nz
	ld a,(playback_frame_counter)
	inc a
	ld b,a
	ld a,(engine_play_frequency)
	cp b
	jp z,playback_second_elapsed
	ld a,b
	ld (playback_frame_counter),a
	ret
playback_second_elapsed:
	xor a
	ld (playback_frame_counter),a
	ld hl,(playback_elapsed_seconds_live)
	inc hl
	ld (playback_elapsed_seconds_live),hl
	call playback_check_auto_advance
	jp ui_draw_playback_time
playback_check_auto_advance:
	ld a,(ui_loop_enabled)
	or a
	ret nz
	ld a,(ui_total_time_valid)
	or a
	ret z
	ld a,(track_flags)
	and 008h
	ret nz
	ld hl,(playback_elapsed_seconds_live)
	ld de,(ui_total_seconds)
	or a
	sbc hl,de
	ret c
	ld a,001h
	ld (ui_auto_advance_pending),a
	ret
ui_metadata_mode:                 db 0
ui_playback_active:               db 0
playback_frame_counter:           db 0
playback_elapsed_seconds_live:    dw 0
ui_track_count:                   dw 0
ui_meta_state:                    db 0
ui_meta_scroll:                   db 0
ui_meta_count:                    db 0
ui_meta_length:                   dw 0
ui_incremental_row:               db 0
ui_base_seconds:                  dw 0
ui_total_seconds:                 dw 0
ui_total_time_valid:              db 0
ui_auto_advance_pending:          db 0
ui_cursor_row:                    db 0
ui_loop_count:                    db 2
ui_audio_muted:                   db 0
ui_help_arrows:
ui_track_select_footer:  db "ARROWS SELECT/PAGE ENTER  "
ui_play_help:            db "H HELP",0
ui_meta_select_footer:   db "L/R PAGE T TRACKS",0
ui_build_playback_time_line:
	call ui_line_clear
	ld hl,ui_time_prefix
	call ui_line_append_string
	ld hl,(playback_elapsed_seconds_live)
	call ui_line_append_mmss
	ld hl,ui_time_separator
	call ui_line_append_string
	ld a,(ui_loop_enabled)
	or a
	jp nz,ui_time_unknown_total
	ld a,(ui_total_time_valid)
	or a
	jp z,ui_time_unknown_total
	ld hl,(ui_total_seconds)
ui_time_have_total:
	call ui_line_append_mmss
	jp ui_line_terminate
ui_time_unknown_total:
	ld hl,ui_time_unknown
	call ui_line_append_string
ui_time_line_done:
	jp ui_line_terminate
ui_line_append_mmss:
	ld de,ENGINE_DIRECT_CALL_PATCH
ui_mmss_div60_loop:
	ld bc,0003ch
	or a
	sbc hl,bc
	jp c,ui_mmss_div60_done
	inc de
	jp ui_mmss_div60_loop
ui_mmss_div60_done:
	add hl,bc
	push hl
	ex de,hl
	ld a,h
	or a
	jp nz,ui_mmss_minutes_wide
	ld a,l
ui_mmss_minutes_check_width:
	cp 00ah
	jp nc,ui_mmss_minutes_wide
	ld a,030h
	call ui_line_append_char
ui_mmss_minutes_wide:
	call ui_line_append_u16
	ld a,03ah
	call ui_line_append_char
	pop hl
	ld a,h
	or a
	jp nz,ui_mmss_seconds_wide
	ld a,l
	cp 00ah
	jp nc,ui_mmss_seconds_wide
	ld a,030h
	call ui_line_append_char
ui_mmss_seconds_wide:
	jp ui_line_append_u16
ui_time_prefix:     db "TIME ",0
ui_time_separator:  db " / ",0
ui_time_unknown:    db "--:--",0
