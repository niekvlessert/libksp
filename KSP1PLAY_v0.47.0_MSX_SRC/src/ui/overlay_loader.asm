; Logo/resource loading and package state.

ui_preload_logo:
	xor a
	ld (ui_logo_rows),a
	ld (ui_logo_chunks),a
	ld (KSPOS_RT_KSPOS_VDP_R7_VALUE),a
	call page_runtime_available
	ret z
	ld hl,logo_filename
	ld de,filename
	ld bc,00008h
	ldir
	call fcb_open_current
	jp c,ui_load_menu_binary
	ld de,io_buffer
	ld bc,00028h
	call fcb_read_current
	jp nz,ui_logo_load_failed
	ld hl,io_buffer
	ld a,(hl)
	cp 053h
	jp nz,ui_logo_load_failed
	inc hl
	ld a,(hl)
	cp 035h
	jp nz,ui_logo_load_failed
	inc hl
	ld a,(hl)
	cp 04ch
	jp nz,ui_logo_load_failed
	inc hl
	ld a,(hl)
	cp 047h
	jp nz,ui_logo_load_failed
	ld a,(io_buffer+004h)
	cp 001h
	jp nz,ui_logo_load_failed
	ld a,(io_buffer+005h)
	or a
	jp z,ui_logo_load_failed
	cp 081h
	jp nc,ui_logo_load_failed
	ld a,(io_buffer+007h)
	ld b,a
	and 001h
	jp z,ui_logo_load_failed
	ld a,b
	and 0f0h
	rrca
	rrca
	rrca
	rrca
	ld (KSPOS_RT_KSPOS_VDP_R7_VALUE),a
	ld a,(io_buffer+006h)
	or a
	jp z,ui_logo_load_failed
	add a,007h
	srl a
	srl a
	srl a
	ld (ui_logo_rows),a
	add a,a
	ld (ui_logo_chunks),a
	ld hl,io_buffer+008h
	call vdp_irq_begin
	call KSPOS_RT_KSPOS_VDP_UPLOAD_PALETTE32
	call vdp_irq_end
	ld hl,UI_LOGO_VRAM_BASE
	ld (ui_logo_vram_addr),hl
ui_menu_logo_chunk_loop:
	ld a,(ui_logo_chunks)
	or a
	jp z,ui_menu_logo_loaded
	ld de,io_buffer
	ld bc,IO_BUFFER_SIZE
	call fcb_read_current
	jp nz,ui_logo_load_failed
	call vdp_irq_begin
	ld hl,(ui_logo_vram_addr)
	xor a
	call vram_set_write_address
	ld hl,io_buffer
	ld bc,IO_BUFFER_SIZE
ui_menu_logo_chunk_out:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,ui_menu_logo_chunk_out
	call vdp_irq_end
	ld hl,(ui_logo_vram_addr)
	ld de,IO_BUFFER_SIZE
	add hl,de
	ld (ui_logo_vram_addr),hl
	ld a,(ui_logo_chunks)
	dec a
	ld (ui_logo_chunks),a
	jp ui_menu_logo_chunk_loop
ui_menu_logo_loaded:
	call fcb_close_current
	ret
ui_logo_load_failed:
	call fcb_close_current
	xor a
	ld (ui_logo_rows),a
	ld (KSPOS_RT_KSPOS_VDP_R7_VALUE),a
	ret
ui_load_menu_binary:
	ld hl,kspmenu_filename
	ld de,filename
	ld bc,0000ch
	ldir
	call fcb_open_current
	jp c,ui_menu_binary_load_failed
	ld de,KSPMENU_ENTRY_VDP_SETUP
	ld bc,MENU_GFX_SIZE
	call fcb_read_current
	push af
	call fcb_close_current
	pop af
	jp nz,ui_menu_binary_load_failed
	ld a,001h
	ld (ui_logo_chunks),a
	ret
ui_menu_binary_load_failed:
	xor a
	ld (ui_logo_chunks),a
	ld (ui_logo_rows),a
	ret
ui_restore_player_from_menu:
	ld a,(ui_logo_chunks)
	or a
	ret z
	call KSPMENU_JUMP_RESTORE_PLAYER_UI
	xor a
	ld (ui_logo_chunks),a
	ld (ui_logo_rows),a
	ret
ui_activate_menu_vdp:
	ld a,(ui_logo_chunks)
	or a
	ret z
	jp KSPMENU_ENTRY_VDP_SETUP
wait_vblank:
	ei
	halt
	di
	ret
ui_menu_store_selection:
	ld (ui_menu_selected),a
	jp ui_draw_menu_rows
	jp ui_draw_menu_rows
	ld hl,(scc_slot_b+2)
	ld (ui_previous_top),hl
	ret
ui_redraw_player_track_selection:
	ld hl,(ui_previous_top)
	ld b,007h
	call ui_draw_player_track_index
	ld hl,(scc_slot_b+2)
	ld b,00fh
	jp ui_draw_player_track_index
page_runtime_available:
	ld hl,KSPOS_INFO
	ld a,(hl)
	cp 04bh
	ret nz
	inc hl
	ld a,(hl)
	cp 050h
	ret nz
	inc hl
	ld a,(hl)
	cp 04fh
	ret nz
	inc hl
	ld a,(hl)
	cp 053h
	ret nz
	ld a,(KSPOS_FLAGS)
	and 080h
	ret
sparse_apply_dynamic_range_raw:
	ld de,(engine_page_load_address)
	ld bc,(engine_page_size)
	ld hl,(page_payload_offset_lo)
	ld (tmp_offset_lo),hl
	ld a,(page_payload_offset_hi)
	ld (tmp_offset_hi),a
	jp read_at_disk
ui_tracks_per_page:
	ld a,011h
	ret
ui_menu_move_up_dynamic:
	ld a,(ui_menu_selected)
	ld b,a
	ld a,(ui_menu_top)
	cp b
	ret z
	ld a,b
	dec a
	jp ui_menu_store_selection
ui_reload_menu_overlay:
	call ui_load_menu_binary
	call MENU_SHOW_HARDWARE_PAGE
	ret
menu_scan_scc_slots_preserve_slot_state:
	ld hl,(BIOS_SLTTBL+1)
	push hl
	call menu_scan_scc_slots
	pop hl
	ld (BIOS_SLTTBL+1),hl
	ret
vdp_write_data_word:
	ld a,l
	out (PORT_VDP_DATA),a
	push hl
	pop af
	out (PORT_VDP_DATA),a
	ret
	ds 5,0		; fixed gap before the KSP header workspace
