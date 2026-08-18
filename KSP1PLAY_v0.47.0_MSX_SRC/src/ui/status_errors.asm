; status errors.asm - KSP1PLAY v0.47.0

ui_build_hardware_line:
	call ui_line_clear
	ld hl,ui_hardware_label
	call ui_line_append_string
	ld a,(engine_required_hardware)
	bit 0,a
	call nz,ui_append_psg
	ld a,(engine_required_hardware)
	bit 3,a
	jp z,ui_hw_single_scc
	ld hl,ui_hw_dual_scc
	call ui_line_append_string
	jp ui_hw_after_scc
ui_hw_single_scc:
	bit 2,a
	jp z,ui_hw_normal_scc
	ld hl,ui_hw_sccplus
	call ui_line_append_string
	jp ui_hw_after_scc
ui_hw_normal_scc:
	bit 1,a
	jp z,ui_hw_after_scc
	ld hl,ui_hw_scc
	call ui_line_append_string
ui_hw_after_scc:
	ld a,(engine_required_hardware)
	bit 4,a
	call nz,ui_append_fmpac
	ld a,(engine_required_hardware)
	bit 6,a
	call nz,ui_append_opl4
	ld hl,ui_hw_at
	call ui_line_append_string
	ld hl,(engine_play_frequency)
	call ui_line_append_u16
	ld hl,ui_hw_hz
	call ui_line_append_string
	call ui_line_terminate
	ret
ui_append_psg:
	ld hl,ui_hw_psg
	jp ui_line_append_string
ui_append_fmpac:
	ld hl,ui_hw_fmpac
	jp ui_line_append_string
ui_append_opl4:
	ld hl,ui_hw_opl4
	jp ui_line_append_string
ui_load_hvar_overlay:
	call restore_process_pages
	call vdp_irq_begin
	ld hl,HVAR_OVERLAY_VRAM
	xor a
	call vram_set_read_address
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	ld bc,HVAR_OVERLAY_MAX
ui_load_hvar_overlay_loop:
	in a,(PORT_VDP_DATA)
	ld (hl),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,ui_load_hvar_overlay_loop
	jp vdp_irq_end
div10_u16:
	ld de,0000ah
	ld bc,ENGINE_DIRECT_CALL_PATCH
div10_loop:
	or a
	sbc hl,de
	jp c,div10_done
	inc bc
	jp div10_loop
div10_done:
	add hl,de
	ld a,l
	ld h,b
	ld l,c
	ret
ui_show_error:
	ld (ui_error_code),a
	call ui_screen5_init
	ld a,005h
	ld b,008h
	ld hl,ui_error_playback
	call ui_text_line
	ld a,(ui_error_code)
	cp 001h
	ld hl,ui_error_file
	jp z,ui_error_draw
	cp 002h
	ld hl,ui_error_invalid_ksp
	jp z,ui_error_draw
	cp 003h
	ld hl,ui_error_unsupported_profile
	jp z,ui_error_draw
	cp 004h
	ld hl,ui_error_hardware_not_found
	jp z,ui_error_draw
	cp 005h
	ld hl,ui_error_out_of_memory
	jp z,ui_error_draw
	cp 006h
	ld hl,ui_error_invalid_track
	jp z,ui_error_draw
	ld hl,ui_error_decode_failed
ui_error_draw:
	ld a,009h
	ld b,00fh
	call ui_text_line
	ld a,014h
	ld b,007h
	ld hl,ui_press_key_text
	call ui_text_line
	call ui_capture_keys
ui_error_wait:
	ei
	halt
	di
	call ui_poll_action
	or a
	jp z,ui_error_wait
	ret
