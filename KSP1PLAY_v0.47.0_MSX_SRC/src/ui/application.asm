; Top-level stopped-state UI and playback interaction loop.
;
; Owns the transition between the package browser, game presentation, track
; playback and error/exit paths. Package parsing itself lives in package_loader.

; Entry: no register contract. Uses global player/UI state.
; Exit:  normally remains in the application loop; BDOS exit is the terminal path.
ui_application:
	xor a
	ld (BIOS_CLIKSW),a
	call ui_enable_text80
	call menu_overlay_entry
	call SERVICE_COMPAT_ENTRY_6CB6
	ld a,(filename)
	or a
	jp z,ui_menu_loop
	call ui_release_menu_overlay
	xor a
	ld (menu_launch),a
	call ui_load_pack
	jp c,ui_load_error
	jp ui_play_screen
ui_menu_loop:
	call ui_prepare_menu_overlay
	jp c,ui_menu_overlay_error
	call ui_menu
	jp c,ui_final_exit
	call ui_release_menu_overlay
	ld a,001h
	ld (menu_launch),a
	call ui_load_pack
	jp c,ui_load_error
	call RECON_ENTRY_RESTORE_SPLIT
	call save_interrupt_hook
	call ui_enable_text80
	call ui_prepare_game_title
	call ui_game_intro
	jp c,ui_track_menu_cancel
	call UI_PRELOAD_IMG5_GALLERY
	call ui_install_selected_track
	jp c,ui_load_error
	jp ui_play_screen
ui_menu_overlay_error:
	ld a,005h
	jp ui_load_error_code
ui_track_menu_cancel:
	call cleanup
	call ui_clear_bios_keyboard_buffer
	call save_interrupt_hook
	call ui_restore_text2_mode_only
	jp ui_menu_loop
ui_play_screen:
	ld a,001h
	ld (ui_playback_active),a
	xor a
	ld (ui_metadata_mode),a
	call playback_time_reset
	call ui_restore_text2_mode_only
	call ui_redraw_track_page
	call ui_capture_keys
	call prepare_engine_page2
	jp c,ui_runtime_error
ui_play_loop:
	call wait_vblank_without_keyclick
	ld a,(ui_audio_muted)
	or a
	call z,call_play
	call ui_service_view_redraw
	call ui_poll_playback_action
	cp ACTION_CODE_BACK
	jp z,ui_back_to_menu
	cp ACTION_CODE_ENTER
	jp z,ui_play_enter_action
	cp ACTION_CODE_UP
	jp z,ui_play_up_action
	cp ACTION_CODE_DOWN
	jp z,ui_play_down_action
	cp ACTION_CODE_LEFT
	jp z,ui_play_left_action
	cp ACTION_CODE_RIGHT
	jp z,ui_play_right_action
	cp ACTION_CODE_PAUSE
	jp z,ui_play_pause_action
	cp ACTION_CODE_LOOP_TOGGLE
	jp z,ui_loop_toggle
	cp ACTION_CODE_SHOW_METADATA
	jp z,ui_play_show_metadata
	cp ACTION_CODE_SHOW_TRACKS
	jp z,ui_play_show_tracks
	cp ACTION_CODE_SHOW_IMAGES
	jp z,UI_IMAGES_DISPATCH_ENTRY
	cp ACTION_CODE_LOOP_COUNT
	jp z,ui_loop_count_next
	cp ACTION_CODE_HELP
	jp nz,ui_play_not_help
	call ui_help_action
	jp ui_play_loop
ui_play_not_help:
	cp ACTION_CODE_NEXT_TRACK
	jp z,ui_next_action
	cp ACTION_CODE_PREVIOUS_TRACK
	jp z,ui_previous_action
	jp ui_play_loop
ui_play_pause_action:
	call UI_P3_CALL_PAUSE_TOGGLE
	jp ui_play_loop
ui_loop_toggle:
	ld a,(ui_loop_enabled)
	xor 001h
	ld (ui_loop_enabled),a
	call ui_draw_help_hint
	call ui_draw_playback_time
	jp ui_play_loop
ui_loop_count_next:
	ld a,(ui_loop_count)
	inc a
	cp 00bh
	jp c,ui_loop_count_store
	ld a,001h
ui_loop_count_store:
	ld (ui_loop_count),a
	xor a
	ld (ui_loop_enabled),a
	call ui_recompute_track_total
	call ui_draw_help_hint
	call ui_draw_playback_time
	jp ui_play_loop
ui_play_show_metadata:
	call ui_switch_to_metadata_view
	jp ui_play_loop
ui_play_show_tracks:
	call ui_enter_track_view
	jp ui_play_loop
ui_play_up_action:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_play_loop
	call UI_P3_CALL_CURSOR_UP
	jp ui_play_loop
ui_play_down_action:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_play_loop
	call UI_P3_CALL_CURSOR_DOWN
	jp ui_play_loop
ui_play_left_action:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_play_meta_prev
	call ui_track_page_prev
	jp ui_play_loop
ui_play_meta_prev:
	call ui_metadata_page_prev
	jp ui_play_loop
ui_play_right_action:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_play_meta_next
	call ui_track_page_next
	jp ui_play_loop
ui_play_meta_next:
	call ui_metadata_page_next
	jp ui_play_loop
ui_play_enter_action:
	ld a,(ui_metadata_mode)
	or a
	jp nz,ui_play_loop
	xor a
	ld (ui_audio_muted),a
	call ui_install_selected_track
	jp c,ui_runtime_error
	call playback_time_reset
	call ui_toggle_metadata_track_view
	jp ui_play_loop
ui_next_action:
	xor a
	ld (ui_audio_muted),a
	ld hl,(ui_previous_track)
	ld (scc_slot_b+2),hl
	call next_track
	jp c,ui_runtime_error
	call playback_time_reset
	call ui_toggle_metadata_track_view
	jp ui_play_loop
ui_previous_action:
	xor a
	ld (ui_audio_muted),a
	ld hl,(ui_previous_track)
	ld (scc_slot_b+2),hl
	call previous_track
	jp c,ui_runtime_error
	call playback_time_reset
	call ui_toggle_metadata_track_view
	jp ui_play_loop
ui_back_to_menu:
	call cleanup
	call ui_clear_bios_keyboard_buffer
	call save_interrupt_hook
	call ui_restore_text2_mode_only
	jp ui_menu_loop
ui_runtime_error:
	ld a,007h
	jp ui_load_error_code
ui_load_error:
	ld a,(ui_error_code)
ui_load_error_code:
	push af
	call cleanup
	call ui_clear_bios_keyboard_buffer
	call save_interrupt_hook
	call ui_enable_text80
	pop af
	call ui_show_error
	jp ui_menu_loop
ui_final_exit:
	call ui_release_menu_overlay
	call cleanup
	call ui_clear_bios_keyboard_buffer
	call ui_restore_text2_screen
	call save_interrupt_hook
	xor a
	ld (space_previous+1),a
	ld c,000h
	call BDOS
	ret

; Open and validate the selected KSP package, prepare its selected hardware
; variant and caches, and return a classified UI error on failure.
