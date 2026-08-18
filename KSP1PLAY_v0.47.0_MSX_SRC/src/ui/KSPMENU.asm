; KSPMENU.asm - KSP1PLAY v0.47.0 reloadable menu/UI module at 8000h
;
; The five-entry jump table at 8000h is the stable interface used by KSPPLAYER.
; Keep entry addresses stable when changing this module.
;
; ABI jump table:
;   8000h -> VDP/TEXT-mode setup used when entering the menu
;   8003h -> full browser draw/open path
;   8006h -> bounded single-row update path (A = package index)
;   8009h -> redraw visible browser rows
;   800Ch -> return/restore hook into the resident player UI
;
include "../include/platform.inc"
include "../include/player_abi.inc"
include "../include/service_abi.inc"
include "../include/compact_entries.inc"
include "../include/ui_p3_abi.inc"
include "../include/kspos_runtime_abi.inc"
include "../include/kspos_abi.inc"
include "../include/image_format.inc"
include "../include/memory_map.inc"
include "../include/recon_runtime_abi.inc"
include "../include/service_runtime_abi.inc"
include "../include/hvar_abi.inc"

org	KSPMENU_RUNTIME_BASE

; The compact renderer deliberately indexes a 3-byte glyph table at 83F1h.
; In the canonical image this address overlaps bytes in the module's one-time
; bootstrap/validation payload. Keep it as an address constant rather than
; inserting a label into the middle of the 83F0h instruction.

kspmenu_entry_vdp_setup:
	jp menu_setup_vdp
	jp kspmenu_entry_open_browser
kspmenu_entry_update_row:
	jp menu_update_visible_row
kspmenu_entry_redraw_list:
	jp menu_redraw_visible_list
	jp kspmenu_entry_restore_player_ui
menu_setup_vdp:
	di
menu_setup_vdp_registers:
	ld a,006h
	ld c,000h
	call menu_write_vdp_register
	ld a,060h
	ld c,001h
	call menu_write_vdp_register
	ld a,03fh
	ld c,002h
	call menu_write_vdp_register
	ld a,(KSPOS_RT_KSPOS_VDP_R7_VALUE)
	and 00fh
	ld c,007h
	call menu_write_vdp_register
	ld a,(BIOS_RG8SAV)
	or 002h
	ld c,008h
	call menu_write_vdp_register
	ld a,(BIOS_RG9SAV)
	and 002h
	or 080h
	ld c,009h
	call menu_write_vdp_register
	xor a
	ld c,012h
	call menu_write_vdp_register
	xor a
	ld c,017h
	call menu_write_vdp_register
	ei
	ret
kspmenu_entry_restore_player_ui:
	jp UI_RESTORE_TEXT2_MODE_ONLY
kspmenu_entry_open_browser:
	call menu_clear_bitmap_rows
	call menu_draw_browser_frame
	call menu_draw_browser_header
	call menu_redraw_visible_list
	call menu_draw_browser_controls
	ret
menu_update_visible_row:
	ld c,a
	ld a,(PLAYER_MENU_COMPAT_TOP_BYTE)
	ld e,a
	ld a,c
	sub e
	ret c
	ld b,a
	call menu_visible_row_count
	cp b
	ret c
	ret z
	ld a,c
	call menu_prepare_centered_title
	ld a,(UI_LINE_SPACE_LOOP)
	cp c
	jp nz,menu_update_row_render
	ld a,03eh
	ld (PLAYER_MENU_COMPAT_MARKER_BYTE),a
	ld a,03ch
	ld (UI_TRACK_PAGE_ORDINAL),a
menu_update_row_render:
	ld a,(UI_LOGO_ROWS)
	add a,003h
	add a,b
	ld b,00fh
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	jp menu_render_text_row
menu_redraw_visible_list:
	ld a,(PLAYER_MENU_COMPAT_TOP_BYTE)
	ld (menu_redraw_package_index),a
	ld a,(UI_LOGO_ROWS)
	add a,003h
	ld (menu_redraw_screen_row),a
	call menu_visible_row_count
	ld b,a
menu_redraw_row_loop:
	push bc
	ld a,(menu_redraw_package_index)
	ld c,a
	ld a,(PLAYER_MENU_COMPAT_LIMIT_BYTE)
	cp c
	jp z,menu_redraw_blank_row
	jp c,menu_redraw_blank_row
	ld a,c
	call menu_prepare_centered_title
	ld a,(UI_LINE_SPACE_LOOP)
	cp c
	jp nz,menu_redraw_emit_row
	ld a,03eh
	ld (PLAYER_MENU_COMPAT_MARKER_BYTE),a
	ld a,03ch
	ld (UI_TRACK_PAGE_ORDINAL),a
	jp menu_redraw_emit_row
menu_redraw_blank_row:
	call menu_clear_line_buffer
menu_redraw_emit_row:
	ld a,(menu_redraw_screen_row)
	ld b,00fh
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	call menu_render_text_row
	ld a,(menu_redraw_package_index)
	inc a
	ld (menu_redraw_package_index),a
	ld a,(menu_redraw_screen_row)
	inc a
	ld (menu_redraw_screen_row),a
	pop bc
	djnz menu_redraw_row_loop
	ret
menu_prepare_centered_title:
	call PLAYER_TITLE_COPY_ENTRY
	call menu_clear_line_buffer
	ld hl,UI_PREVIOUS_TOP
	ld b,03ch
	ld c,000h
menu_title_length_loop:
	ld a,(hl)
	or a
	jp z,menu_title_center_copy
	inc hl
	inc c
	djnz menu_title_length_loop
menu_title_center_copy:
	ld a,040h
	sub c
	srl a
	ld e,a
	ld d,000h
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	add hl,de
	ex de,hl
	ld hl,UI_PREVIOUS_TOP
	ld b,c
menu_title_copy_loop:
	ld a,b
	or a
	ret z
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	djnz menu_title_copy_loop
	ret
menu_visible_row_count:
	ld a,(UI_LOGO_ROWS)
	ld c,a
	ld a,010h
	sub c
	ret
menu_draw_browser_frame:
	ld a,(UI_LOGO_ROWS)
	add a,a
	add a,a
	add a,a
	call menu_fill_vram_row_ff
	ld a,(UI_LOGO_ROWS)
	add a,002h
	add a,a
	add a,a
	add a,a
	call menu_fill_vram_row_ff
	ld a,098h
	call menu_fill_vram_row_ff
	ld a,0a8h
	call menu_fill_vram_row_ff
	ld a,(UI_LOGO_ROWS)
	add a,a
	add a,a
	add a,a
	ld d,a
	ld e,0a8h
menu_frame_side_loop:
	ld a,d
	push de
	call menu_draw_row_edge_nibbles
	pop de
	inc d
	ld a,d
	cp e
	jp c,menu_frame_side_loop
	ret
menu_draw_browser_header:
	call menu_clear_line_buffer
	ld hl,menu_title_text
	ld de,PLAYER_MENU_BROWSER_TITLE_PTR
	call menu_copy_z_string
	ld hl,menu_select_game_text
	ld de,PLAYER_MENU_BROWSER_SELECT_PTR
	call menu_copy_z_string
	ld a,(UI_LOGO_ROWS)
	inc a
	ld b,00fh
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	jp menu_render_text_row
menu_draw_browser_controls:
	call menu_clear_line_buffer
	ld hl,menu_controls_text
	ld de,PLAYER_MENU_CONTROLS_PTR
	call menu_copy_z_string
	ld a,014h
	ld b,00fh
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	jp menu_render_text_row
menu_title_text:
	db "-->KSP1Play<--",0
menu_select_game_text:
	db "SELECT A GAME",0
menu_controls_text:
	db "UP/DOWN SELECT  LEFT/RIGHT PAGE  ENTER OPEN  ESC EXIT",0
menu_copy_z_string:
	ld a,(hl)
	or a
	ret z
	ld (de),a
	inc hl
menu_copy_z_next:
	inc de
	jp menu_copy_z_string
menu_clear_line_buffer:
	ld hl,PLAYER_MENU_COMPAT_TEXT_BASE
	ld b,040h
	ld a,020h
menu_clear_line_loop:
	ld (hl),a
	inc hl
	djnz menu_clear_line_loop
	xor a
	ld (hl),a
	ret
menu_clear_bitmap_rows:
	ld a,(UI_LOGO_ROWS)
	add a,a
	add a,a
	add a,a
	ld e,a
menu_clear_bitmap_row_loop:
	ld a,e
	cp 0d4h
	ret nc
	push de
	call menu_y_to_vram_address
menu_clear_bitmap_write_row:
	call menu_set_vram_write_address
	xor a
	ld b,080h
menu_clear_bitmap_write_zero_loop:
	out (PORT_VDP_DATA),a
	djnz menu_clear_bitmap_write_zero_loop
	pop de
	inc e
	jp menu_clear_bitmap_row_loop
menu_y_to_vram_address:
	ld l,a
menu_y_to_vram_shift:
	ld h,000h
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,kspmenu_entry_vdp_setup
	add hl,de
	ret
menu_fill_vram_row_ff:
	call menu_y_to_vram_address
	call menu_set_vram_write_address
	ld a,0ffh
	ld b,080h
menu_fill_vram_row_ff_loop:
	out (PORT_VDP_DATA),a
	djnz menu_fill_vram_row_ff_loop
	ret
menu_draw_row_edge_nibbles:
	push af
	call menu_y_to_vram_address
	call menu_set_vram_write_address
	ld a,0f0h
	out (PORT_VDP_DATA),a
	pop af
	call menu_y_to_vram_address
	ld de,0007fh
	add hl,de
	call menu_set_vram_write_address
	ld a,00fh
	out (PORT_VDP_DATA),a
	ret
menu_render_text_row:
	ld (menu_render_y),a
	ld a,b
	and 00fh
	ld (menu_render_color),a
	ld de,menu_render_buffer
	ld b,040h
menu_render_copy_chars:
	ld a,(hl)
	or a
	jp z,menu_render_pad_spaces
	cp 020h
	jp c,menu_render_pad_spaces
	cp 080h
	jp c,menu_render_store_char
	ld a,03fh
menu_render_store_char:
	ld (de),a
	inc hl
	inc de
	djnz menu_render_copy_chars
	jp menu_render_scanlines_begin
menu_render_pad_spaces:
	ld a,020h
menu_render_pad_loop:
	ld (de),a
	inc de
	djnz menu_render_pad_loop
menu_render_scanlines_begin:
	xor a
	ld (menu_render_scanline),a
menu_render_scanline_loop:
	ld a,(menu_render_y)
	ld h,a
	ld l,000h
	add hl,hl
	add hl,hl
	ld de,kspmenu_entry_vdp_setup
	add hl,de
	ld a,(menu_render_scanline)
	or a
	jp z,menu_render_scanline_ready
	ld e,a
	ld d,000h
menu_render_scanline_offset_loop:
	ld bc,00080h
	add hl,bc
	dec e
	jp nz,menu_render_scanline_offset_loop
menu_render_scanline_ready:
	call menu_set_vram_write_address
	ld hl,menu_render_buffer
	ld b,040h
menu_render_character_loop:
	push bc
	ld a,(hl)
	inc hl
	push hl
	call menu_glyph_lookup
	ld a,(menu_render_scanline)
	cp 005h
	jp nc,menu_render_no_glyph_bits
	call menu_glyph_scan_bits
	jp menu_render_emit_bits
menu_render_no_glyph_bits:
	xor a
menu_render_emit_bits:
	pop hl
	call menu_emit_glyph_scan
	pop bc
	djnz menu_render_character_loop
	ld a,(menu_render_scanline)
	inc a
	ld (menu_render_scanline),a
	cp 008h
	jp c,menu_render_scanline_loop
	ret
menu_glyph_lookup:
	cp 061h
	jp c,menu_glyph_range_check
	cp 07bh
	jp nc,menu_glyph_range_check
	sub 020h
menu_glyph_range_check:
	cp 020h
	jp c,menu_glyph_fallback
	cp 060h
	jp c,menu_glyph_index
menu_glyph_fallback:
	ld a,03fh
menu_glyph_index:
	sub 020h
	ld e,a
	ld d,000h
	ld h,d
	ld l,e
	add hl,hl
	add hl,de
	ld de,MENU_GLYPH_TABLE
	add hl,de
	ret
menu_glyph_scan_bits:
	cp 002h
	jp c,menu_glyph_top_row
	cp 004h
	jp c,menu_glyph_middle_row
	inc hl
	inc hl
	ld a,(hl)
	and 007h
	ret
menu_glyph_middle_row:
	inc hl
	sub 002h
menu_glyph_top_row:
	or a
	ld a,(hl)
	ret nz
	rrca
	rrca
	rrca
	rrca
	and 007h
	ret
menu_emit_glyph_scan:
	and 007h
	rlca
	rlca
	rlca
	rlca
	rlca
	ld c,a
	ld a,(menu_render_color)
	ld b,a
	rlca
	rlca
	rlca
	rlca
	ld d,a
	call menu_emit_two_pixels
	call menu_emit_two_pixels
	ret
menu_emit_two_pixels:
	xor a
	sla c
	jp nc,menu_emit_second_pixel
	or d
menu_emit_second_pixel:
	sla c
	jp nc,menu_emit_pixel_byte
	or b
menu_emit_pixel_byte:
	out (PORT_VDP_DATA),a
	ret
menu_set_vram_write_address:
	ld a,h
	rlca
	rlca
	and 003h
	out (PORT_VDP_CTRL),a
	ld a,08eh
	out (PORT_VDP_CTRL),a
	ld a,l
	out (PORT_VDP_CTRL),a
	ld a,h
	and 03fh
	or 040h
	out (PORT_VDP_CTRL),a
	ret
menu_write_vdp_register:
	push af
	push bc
	ld b,a
	ld a,c
	cp 000h
	jp nz,menu_write_vdp_wr_r1
	ld a,b
	ld (BIOS_RG0SAV),a
	jp menu_write_vdp_hw
menu_write_vdp_wr_r1:
	cp 001h
	jp nz,menu_write_vdp_wr_r2
	ld a,b
	ld (BIOS_RG1SAV),a
	jp menu_write_vdp_hw
menu_write_vdp_wr_r2:
	cp 002h
	jp nz,menu_write_vdp_wr_r7
	ld a,b
	ld (BIOS_RG2SAV),a
	jp menu_write_vdp_hw
menu_write_vdp_wr_r7:
	cp 007h
	jp nz,menu_write_vdp_wr_r8
	ld a,b
	ld (BIOS_RG7SAV),a
	jp menu_write_vdp_hw
menu_write_vdp_wr_r8:
	cp 008h
	jp nz,menu_write_vdp_wr_r9
	ld a,b
	ld (BIOS_RG8SAV),a
	jp menu_write_vdp_hw
menu_write_vdp_wr_r9:
	cp 009h
	jp nz,menu_write_vdp_hw
	ld a,b
	ld (BIOS_RG9SAV),a
menu_write_vdp_hw:
	ld a,b
	out (PORT_VDP_CTRL),a
	ld a,c
	or 080h
	out (PORT_VDP_CTRL),a
	pop bc
	pop af
	ret
menu_redraw_package_index:
	db 0
menu_redraw_screen_row:
	db 0
menu_render_y:
	db 0
menu_render_color:
	rrca
menu_render_scanline:
	xor a
menu_render_buffer:
	ld (IMG5_RUNTIME_IMAGE_INDEX),a
	ld (IMG5_RUNTIME_RESERVED),a
	ld a,(KSP_FILE_SIZE_HI)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_FILE_SIZE_TOP)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_TABLE_OFFSET_HI)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_TABLE_OFFSET_TOP)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_COUNT_HI)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_ENTRY_SIZE_HI)
	or a
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_ENTRY_SIZE)
	cp 020h
	jp nz,IMG5_RT_FINISH
	ld a,(KSP_RESOURCE_COUNT)
	or a
	jp z,IMG5_RT_FINISH
	ld (SERVICE_SPLIT_STRIDE),a
; Packed 3-byte glyph/font payload. The table begins at $83F1, deliberately
; overlapping the final operand bytes of the one-time IMG5 bootstrap fragment.
; These bytes are data, not executable Z80 code.
menu_glyph_payload_83f3:
	db 02ah,022h,020h,002h,055h,000h,000h,057h,057h,005h,036h,023h,006h,051h,024h,005h
	db 025h,025h,003h,022h,000h,000h,012h,022h,001h,042h,022h,004h,005h,025h,000h,002h
	db 072h,000h,000h,002h,004h,000h,070h,000h,000h,000h,002h,011h,024h,004h,075h,055h
	db 007h,026h,022h,007h,061h,074h,007h,061h,071h,006h,055h,071h,001h,074h,061h,006h
	db 034h,075h,007h,071h,022h,002h,075h,075h,007h,075h,071h,006h,002h,002h,000h,002h
	db 002h,004h,012h,042h,001h,007h,007h,000h,042h,012h,004h,061h,020h,002h,075h,074h
	db 007h,025h,075h,005h,065h,065h,006h,034h,044h,003h,065h,055h,006h,074h,064h,007h
	db 074h,064h,004h,034h,055h,003h,055h,075h,005h,072h,022h,007h,011h,015h,002h,055h
	db 065h,005h,044h,044h,007h,057h,075h,005h,057h,077h,005h,025h,055h,002h,065h,064h
	db 004h,025h,057h,003h,065h,065h,005h,034h,021h,006h,072h,022h,002h,055h,055h,007h
	db 055h,055h,002h,055h,077h,005h,055h,025h,005h,055h,022h,002h,071h,024h,007h,032h
	db 022h,003h,044h,021h,001h,062h,022h,006h,025h,000h,000h,000h,000h,007h
menu_show_hardware_page:
	call menu_prepare_text_palette
	call MENU_DETECT_HARDWARE
	call UI_DRAW_FRAME
	ld a,001h
	ld b,017h
	ld c,022h
	ld hl,menu_hw_title_text
	call UI_WRITE_FIELD
	ld a,003h
	ld b,005h
	ld c,020h
	ld hl,menu_hw_devices_text
	call UI_WRITE_FIELD
	ld a,005h
	ld (menu_hw_next_row),a
	ld a,(AVAILABLE_HARDWARE)
	bit 0,a
	call nz,menu_show_psg_row
	ld a,(AVAILABLE_HARDWARE)
	bit 1,a
	call nz,menu_show_scc_row
	ld a,(AVAILABLE_HARDWARE)
	bit 2,a
	call nz,menu_show_sccplus_row
	ld a,(AVAILABLE_HARDWARE)
	bit 3,a
	call nz,menu_show_dual_scc_row
	ld a,(AVAILABLE_HARDWARE)
	bit 4,a
	call nz,menu_show_fmpac_row
	ld a,(AVAILABLE_HARDWARE)
	bit 5,a
	call nz,menu_show_y8950_row
	ld a,(AVAILABLE_HARDWARE)
	bit 6,a
	call nz,menu_show_moonsound_row
	ld a,014h
	ld b,01ch
	ld c,017h
	ld hl,menu_hw_continue_text
	call UI_WRITE_FIELD
	call UI_CAPTURE_KEYS
menu_hardware_wait_enter:
	ei
	halt
	di
	call UI_POLL_ACTION
	cp 002h
	jp nz,menu_hardware_wait_enter
	ret
menu_show_psg_row:
	ld hl,menu_hw_psg_text
	ld c,028h
	jp menu_show_device_row
menu_show_scc_row:
	ld hl,menu_hw_scc_text
	ld c,028h
	jp menu_show_device_row
menu_show_sccplus_row:
	ld hl,menu_hw_sccplus_text
	ld c,028h
	jp menu_show_device_row
menu_show_dual_scc_row:
	ld hl,menu_hw_dual_scc_text
	ld c,028h
	jp menu_show_device_row
menu_show_fmpac_row:
	ld hl,menu_hw_fmpac_text
	ld c,028h
	jp menu_show_device_row
menu_show_y8950_row:
	ld hl,menu_hw_y8950_text
	ld c,028h
	jp menu_show_device_row
menu_show_moonsound_row:
	ld hl,menu_hw_moonsound_text
	ld c,028h
	jp menu_show_device_row
menu_show_device_row:
	ld a,(menu_hw_next_row)
	ld b,008h
	call UI_WRITE_FIELD
	ld a,(menu_hw_next_row)
	inc a
	ld (menu_hw_next_row),a
	ret
menu_hw_next_row:
	db 0
menu_hw_title_text:
	db "-->KSP1PLAY<-- Detected Hardware",0
menu_hw_devices_text:
	db "Detected audio devices:",0
menu_hw_continue_text:
	db "Press ENTER to continue",0
menu_hw_psg_text:
	db "PSG",0
menu_hw_scc_text:
	db "SCC",0
menu_hw_sccplus_text:
	db "SCC+",0
menu_hw_dual_scc_text:
	db "Dual SCC",0
menu_hw_fmpac_text:
	db "FM-PAC / MSX-MUSIC (YM2413)",0
menu_hw_y8950_text:
	db "MSX-AUDIO / Y8950",0
menu_hw_moonsound_text:
	; The original v0.47 binary deliberately has no NUL terminator here.
	; The fixed-width renderer consumes this 16-byte label; code resumes at 8618h.
	db "MoonSound / OPL4"

; Stored tail of the IMG5 gallery preload runtime. KSPPLAYER copies this block
; from $8618 to its runtime address $7144 before executing it. Absolute branch
; targets below therefore refer to the stitched $71xx/$72xx runtime image.
img5_gallery_runtime_tail_image:
	xor b
	inc e
	ld (SERVICE_SPLIT_PIXEL_PTR),hl
	ld hl,(SERVICE_SPLIT_PIXEL_PTR)
	xor a
	ld de,RESOURCE_ENTRY
	ld bc,00020h
	call READ_AT
img5_gallery_descriptor_read_result:
	or a
	jp nz,IMG5_RT_FINISH
	ld hl,RESOURCE_ENTRY
img5_gallery_check_descriptor_signature:
	ld a,(hl)
	cp 049h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	inc hl
	ld a,(hl)
	cp 04dh
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
img5_gallery_check_descriptor_g:
	inc hl
	ld a,(hl)
	cp 047h
img5_gallery_check_descriptor_tail:
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	inc hl
	ld a,(hl)
	cp 035h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(RESOURCE_COMPRESSION)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(RESOURCE_PAYLOAD_OFFSET_HI)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(RESOURCE_PAYLOAD_OFFSET_TOP)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld hl,(RESOURCE_PACKED_SIZE_LO)
img5_gallery_check_payload_size:
	ld de,IMG5_PAYLOAD_BYTES
	or a
	sbc hl,de
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(RESOURCE_PACKED_SIZE_HI)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(RESOURCE_PACKED_SIZE_TOP)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld hl,(RESOURCE_PAYLOAD_OFFSET_LO)
	xor a
	ld de,kspmenu_entry_vdp_setup
	ld bc,IMG5_PAYLOAD_BYTES
	call READ_AT
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld hl,kspmenu_entry_vdp_setup
	ld a,(hl)
	cp 049h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	inc hl
	ld a,(hl)
	cp 035h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	inc hl
	ld a,(hl)
	cp 056h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	inc hl
	ld a,(hl)
	cp 031h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(IMAGE_HEADER_WIDTH)
	cp 080h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(IMAGE_HEADER_WIDTH+1)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_update_row)
	cp 06ah
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_update_row+1)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_update_row+2)
	cp 040h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_redraw_list)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_redraw_list+1)
	cp 010h
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(kspmenu_entry_redraw_list+2)
	or a
	jp nz,IMG5_RT_ADVANCE_DESCRIPTOR
	ld a,(IMG5_RUNTIME_IMAGE_INDEX)
	or a
	jp nz,IMG5_RT_COPY_NEXT_IMAGE
	call IMG5_RT_CLEAR_VRAM_PAGE
	call IMG5_RT_UPLOAD_PALETTE
	call IMG5_RT_COPY_IMAGE
	ld a,(IMG5_RUNTIME_IMAGE_INDEX)
	inc a
	ld (IMG5_RUNTIME_IMAGE_INDEX),a
	cp 004h
	jp z,IMG5_RT_FINISH
	ld hl,(SERVICE_SPLIT_PIXEL_PTR)
	ld de,00020h
	add hl,de
	ld (SERVICE_SPLIT_PIXEL_PTR),hl
	ld a,(SERVICE_SPLIT_STRIDE)
	dec a
	ld (SERVICE_SPLIT_STRIDE),a
	jp nz,IMG5_RT_DESCRIPTOR_LOOP
	call IMG5_RT_DRAW_INDICATOR
	jp SAVE_INTERRUPT_HOOK
	call VDP_IRQ_BEGIN
	ld hl,kspmenu_entry_vdp_setup
	ld a,001h
	call VRAM_SET_WRITE_ADDRESS
	ld bc,IMG5_GALLERY_CLEAR_BYTES
	xor a
	out (PORT_VDP_DATA),a
	dec bc
	ld a,b
	or c
	jp nz,IMG5_RT_CLEAR_VRAM_LOOP
	call VDP_IRQ_END
	ret
	call VDP_IRQ_BEGIN
	ld hl,IMG5_GALLERY_PALETTE_VRAM
	ld a,001h
	call VRAM_SET_WRITE_ADDRESS
	ld hl,IMG5_PALETTE_DATA
	ld b,010h
img5_gallery_palette_loop:
	ld a,(hl)
	and 007h
	rlca
	rlca
	rlca
	rlca
	ld d,a
	inc hl
	ld e,(hl)
	inc hl
	ld a,(hl)
	and 007h
	or d
	out (PORT_VDP_DATA),a
	ld a,e
	and 007h
	out (PORT_VDP_DATA),a
	inc hl
	djnz img5_gallery_palette_loop
	call VDP_IRQ_END
	ret
	ld hl,kspmenu_entry_vdp_setup
	ld a,(IMG5_RUNTIME_IMAGE_INDEX)
	bit 0,a
	jp z,IMG5_RT_COPY_SECOND_HALF
	ld de,00040h
	add hl,de
	bit 1,a
	jp z,IMG5_RT_COPY_LAYOUT_READY
	ld de,IMG5_GALLERY_LAYOUT_SKIP
	add hl,de
	ld (SERVICE_SPLIT_ROWS),hl
	ld hl,menu_setup_vdp_registers
	ld (SERVICE_SPLIT_HEIGHT),hl
	ld a,06ah
	ld (SERVICE_SPLIT_Y),a
	call VDP_IRQ_BEGIN
	ld hl,(SERVICE_SPLIT_ROWS)
	ld a,001h
	call VRAM_SET_WRITE_ADDRESS
	ld hl,(SERVICE_SPLIT_HEIGHT)
	ld b,040h
img5_gallery_copy_scanline_loop:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	djnz img5_gallery_copy_scanline_loop
	ld (SERVICE_SPLIT_HEIGHT),hl
	call VDP_IRQ_END
	ld hl,(SERVICE_SPLIT_ROWS)
	ld de,00080h
	add hl,de
	ld (SERVICE_SPLIT_ROWS),hl
	ld a,(SERVICE_SPLIT_Y)
	dec a
	ld (SERVICE_SPLIT_Y),a
	jp nz,IMG5_RT_COPY_SCANLINE_LOOP
	ret
	call VDP_IRQ_BEGIN
	ld hl,IMG5_INDICATOR_VRAM
	xor a
	call VRAM_SET_WRITE_ADDRESS
	ld hl,IMG5_RT_INDICATOR_TEXT_OFF
	ld a,(IMG5_RUNTIME_IMAGE_INDEX)
	or a
	jp z,IMG5_RT_INDICATOR_COPY_LOOP
	ld hl,IMG5_RT_INDICATOR_TEXT_ON
	ld b,008h
img5_gallery_indicator_copy_loop:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	djnz img5_gallery_indicator_copy_loop
	call VDP_IRQ_END
	ret
images_label_text:
	db "I IMAGES        "
menu_prepare_text_palette:
	call UI_ENABLE_TEXT80
	xor a
	ld (BIOS_BAKCLR),a
	ld (BIOS_BDRCLR),a
	ret
	ds 7,0		; 87f9-87ff final module padding
