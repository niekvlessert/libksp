; startup splash.asm - KSP1PLAY v0.47.0

wait_vblank_without_keyclick:
	ld a,(BIOS_CLIKSW)
	ld (ui_saved_cliksw),a
	xor a
	ld (BIOS_CLIKSW),a
	ei
	halt
	di
	ld a,(ui_saved_cliksw)
	ld (BIOS_CLIKSW),a
	ret
ui_saved_cliksw:
	db 0
ui_run_menu_overlay:
	call ui_fill_high_vram_ff
	call ui_preload_logo
	call ui_reload_menu_overlay
	ld a,(ui_logo_rows)
	or a
	jp z,ui_startup_splash_text
	call ui_capture_keys
	call ui_activate_menu_vdp
ui_startup_splash_wait:
	call wait_vblank
	call ui_poll_action
	cp 007h
	jp nz,ui_startup_splash_wait
	call ui_restore_player_from_menu
ui_startup_splash_text:
	xor a
	ld (filename),a
	jp ui_enable_text80
ui_fill_high_vram_ff:
	call vdp_irq_begin
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	xor a
	call vram_set_write_address
	ld bc,UI_SPLASH_CLEAR_BYTES
	ld d,0ffh
ui_splash_clear_loop:
	ld a,d
	out (PORT_VDP_DATA),a
	dec bc
	ld a,b
	or c
	jp nz,ui_splash_clear_loop
	jp vdp_irq_end
	ds 3,0		; fixed layout gap

; Main stopped-state application loop. The reloadable KSPMENU module owns the
; browser presentation; package preparation and playback installation remain here.
