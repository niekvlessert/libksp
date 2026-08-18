; ui state.asm - KSP1PLAY v0.47.0

ui_file_count:           db 0
ui_menu_selected:        db 0
ui_menu_top:             db 0
ui_draw_index:           db 0
ui_draw_row:             db 0
ui_track_index:          dw 0
ui_track_top:            dw 0
ui_track_page_ordinal:   db 0
ui_previous_track:       dw 0
ui_previous_top:         dw 0
ui_text_row:             db 0
ui_menu_overlay_segment: db 0ffh
ui_line_pos:             db 0
ui_keys3_now:            db 0
ui_keys4_now:            db 0
ui_keys5_now:            db 0
ui_keys7_now:            db 0
ui_keys8_now:            db 0
ui_keys3_prev:           db 0
ui_keys4_prev:           db 0
ui_keys5_prev:           db 0
ui_keys7_prev:           db 0
ui_keys8_prev:           db 0
ui_num_buffer:           ds 6,0
ui_line_buffer:          ds 65,0
ui_string_buffer:        ds 65,0
ui_track_entry:          ds 32,0
ui_fib:                  ds 64,0
ui_file_names:
	ds 801,0		; 3053-3373 zero-filled reserved/data bytes (compact NOP run)
ui_view:
	db 0
ui_screen_context:
	db 0
ui_frame_in_second:
	db 0
ui_elapsed_seconds:
	db 0
	db 0
ui_visible_track_count_cache:
	db 0
	db 0
	db 0
	db 0
	db 0
	db 0
	db 0
ui_fast_module_end:
	ds 20,0		; 3380-3393 zero-filled reserved/data bytes (compact NOP run)
; Legacy resident UI/error string table. The runtime source originally
; interpreted these ASCII bytes as Z80 opcodes; these are literal data.
legacy_menu_title:
	db "KSPOS PLAY 0.45.3 ",0
legacy_menu_select_title:
	db "SELECT A GAME",0
legacy_menu_no_ksp_files:
	db "NO KSP FILES FOUND",0
legacy_menu_help:
	db "KSP"
legacy_menu_help_short:
	db "UP/DOWN SELECT  LEFT/RIGHT PAGE  ENTER OPEN  ESC EXIT",0
ui_track_label:
	db "TRACK ",0
ui_track_separator:
	db "/",0
ui_hardware_label:
	db "Hardware: ",0
ui_hw_psg:
	db "PSG ",0
ui_hw_scc:
	db "SCC ",0
ui_hw_sccplus:
	db "SCC+ ",0
ui_hw_dual_scc:
	db "DUAL-SCC ",0
ui_hw_fmpac:
	db "FMPAC ",0
ui_hw_opl4:
	db "OPL4 ",0
ui_hw_at:
	db " @ ",0
ui_hw_hz:
	db "HZ",0
ui_error_playback:
	db "PLAYBACK ERROR",0
ui_error_file:
	db "FILE ERROR",0
ui_error_invalid_ksp:
	db "INVALID KSP",0
ui_error_unsupported_profile:
	db "UNSUPPORTED PROFILE",0
ui_error_hardware_not_found:
	db "HARDWARE NOT FOUND",0
ui_error_out_of_memory:
	db "OUT OF MEMORY",0
ui_error_invalid_track:
	db "INVALID TRACK",0
ui_error_decode_failed:
	db "DECODE FAILED",0
ui_press_key_text:
	db "PRESS KEY",0
ui_intro_footer:
	db "ENTER PLAY T TRACKS M META",0

