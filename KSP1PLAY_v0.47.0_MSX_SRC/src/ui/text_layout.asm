; text layout.asm - KSP1PLAY v0.47.0

ui_prepare_menu_overlay:
	ld a,(ui_menu_overlay_segment)
	cp 0feh
	ret z
	cp 0ffh
	ret nz
	call mapper_alloc_user_primary
	ret c
	ld (ui_menu_overlay_segment),a
	call map_p2
	call vdp_irq_begin
	ld hl,MENU_OVERLAY_VRAM_IMAGE
	xor a
	call vram_set_read_address
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	ld bc,MENU_OVERLAY_VRAM_IMAGE_BYTES
ui_restore_overlay_loop:
	in a,(PORT_VDP_DATA)
	ld (hl),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,ui_restore_overlay_loop
	call vdp_irq_end
	ld a,(ui_menu_overlay_segment)
	call map_p1
	ld a,(original_p2)
	call map_p2
	or a
	ret
ui_release_menu_overlay:
	ld a,(ui_menu_overlay_segment)
	cp 0ffh
	ret z
	cp 0feh
	jp z,ui_release_overlay_restore_p1
	ld b,a
	ld a,(original_p1)
	call map_p1
	ld a,b
	call mapper_free_primary
	jp ui_release_overlay_finish
ui_release_overlay_restore_p1:
	ld a,(original_p1)
	call map_p1
ui_release_overlay_finish:
	ld a,0ffh
	ld (ui_menu_overlay_segment),a
	ret
ui_screen5_init:
	jp ui_text80_clear
ui_restore_text2_screen:
	jp ui_enable_text80
call_main_bios:
	ld iy,(BIOS_MAINROM_SLOT)
	jp BIOS_CALSLT
save_interrupt_hook:
	push hl
	ld hl,(BIOS_H_TIMI)
	ld (BIOS_H_TIMI+2),hl
	pop hl
	ret
ui_clear_bios_keyboard_buffer:
	ei
ui_wait_keys_released_loop:
	halt
	di
	call ui_scan_keyboard_rows
	ld a,(ui_keys7_now)
	ld b,a
	ld a,(ui_keys8_now)
	or b
	jp nz,ui_wait_keys_released_more
	xor a
	ld (ui_keys3_prev),a
	ld (ui_keys4_prev),a
	ld (ui_keys5_prev),a
	ld (ui_keys7_prev),a
	ld (ui_keys8_prev),a
	ei
	ret
ui_wait_keys_released_more:
	ei
	jp ui_wait_keys_released_loop
ui_write_vdp_register:
	push af
	push bc
	ld b,a
	ld a,c
	cp ACTION_CODE_LOOP_TOGGLE
	jp nc,ui_vdp_shadow_high
	ld hl,BIOS_RG0SAV
	ld e,c
	ld d,000h
	add hl,de
	ld (hl),b
	jp ui_vdp_write_hw
ui_vdp_shadow_high:
	cp ACTION_CODE_LOOP_TOGGLE
	jp nz,ui_vdp_shadow_r9
	ld a,b
	ld (BIOS_RG8SAV),a
	jp ui_vdp_write_hw
ui_vdp_shadow_r9:
	cp ACTION_CODE_SHOW_METADATA
	jp nz,ui_vdp_shadow_r18
	ld a,b
	ld (BIOS_RG9SAV),a
	jp ui_vdp_write_hw
ui_vdp_shadow_r18:
	cp 012h
	jp nz,ui_vdp_shadow_r23
	ld a,b
	ld (BIOS_RG18SAV),a
	jp ui_vdp_write_hw
ui_vdp_shadow_r23:
	cp 017h
	jp nz,ui_vdp_write_hw
	ld a,b
	ld (BIOS_RG23SAV),a
ui_vdp_write_hw:
	ld a,b
	out (PORT_VDP_CTRL),a
	ld a,c
	or 080h
	out (PORT_VDP_CTRL),a
	pop bc
	pop af
	ret
ui_text_line:
	ld (ui_text_row),a
	jp ui_text80_render
ui_row_address:
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
	ret
ui_write_field:
	push hl
	push bc
	call ui_row_address
	pop bc
	ld e,b
	ld d,000h
	add hl,de
	call vdp_irq_begin
	xor a
	call vram_set_write_address
	pop hl
	ld b,c
	ld c,000h
ui_field_loop:
	ld a,b
	or a
	jp z,ui_field_done
	ld a,c
	or a
	jp nz,ui_field_emit_space
	ld a,(hl)
	or a
	jp z,ui_field_begin_padding
	cp 013h
	jp c,ui_field_begin_padding
	cp 080h
	jp c,ui_field_emit
	ld a,03fh
	jp ui_field_emit
ui_field_begin_padding:
	inc c
ui_field_emit_space:
	ld a,020h
ui_field_emit:
	out (PORT_VDP_DATA),a
	ld a,c
	or a
	jp nz,ui_field_no_inc
	inc hl
ui_field_no_inc:
	djnz ui_field_loop
ui_field_done:
	jp vdp_irq_end
ui_draw_hline:
	push af
	push bc
	call ui_row_address
	call vdp_irq_begin
	xor a
	call vram_set_write_address
	pop bc
	ld a,b
	out (PORT_VDP_DATA),a
	ld b,04eh
	ld a,017h
ui_draw_hline_loop:
	out (PORT_VDP_DATA),a
	djnz ui_draw_hline_loop
	ld a,c
	out (PORT_VDP_DATA),a
	call vdp_irq_end
	pop af
	ret
ui_write_char:
	push bc
	call ui_row_address
	pop bc
	ld e,b
	ld d,000h
	add hl,de
	call vdp_irq_begin
	xor a
	call vram_set_write_address
	ld a,c
	out (PORT_VDP_DATA),a
	jp vdp_irq_end
ui_draw_frame:
	xor a
	ld bc,UI_FRAME_OUTER_GLYPHS
	call ui_draw_hline
	ld a,002h
	ld bc,UI_FRAME_SEPARATOR_GLYPHS
	call ui_draw_hline
	ld a,017h
	ld bc,UI_FRAME_BOTTOM_GLYPHS
	call ui_draw_hline
	ld a,001h
ui_draw_frame_side_loop:
	cp 017h
	jp z,ui_frame_separator
	cp 002h
	jp z,ui_draw_frame_side_next
	push af
	ld b,000h
	ld c,016h
	call ui_write_char
	pop af
	push af
	ld b,04fh
	ld c,016h
	call ui_write_char
	pop af
ui_draw_frame_side_next:
	inc a
	jp ui_draw_frame_side_loop
ui_frame_separator:
	ld a,014h
	ld bc,UI_FRAME_SEPARATOR_GLYPHS
	jp ui_draw_hline
ui_draw_common_header:
	ld a,001h
	ld b,003h
	ld c,00eh
	ld hl,ui_header_brand
	call ui_write_field
	call vdp_irq_begin
	ld hl,UI_GAME_TITLE_VRAM
	xor a
	call vram_set_read_address
	ld de,ui_string_buffer
	ld b,030h
ui_common_title_read:
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	djnz ui_common_title_read
	call vdp_irq_end
	xor a
	ld (ui_string_buffer+47),a
	ld hl,ui_string_buffer
	ld b,02fh
	ld c,000h
	ld e,000h
ui_common_title_scan_loop:
	ld a,(hl)
	or a
	jp z,ui_common_title_len_done
	inc hl
	inc c
	cp 020h
	jp z,ui_common_title_len_space
	ld e,c
ui_common_title_len_space:
	djnz ui_common_title_scan_loop
ui_common_title_len_done:
	ld a,e
	or a
	ret z
	ld e,a
	ld a,050h
	sub e
	srl a
	cp 014h
	jp nc,ui_common_title_col_ok
	ld a,014h
ui_common_title_col_ok:
	ld b,a
	ld c,e
	ld a,001h
	ld hl,ui_string_buffer
	jp ui_write_field
ui_draw_menu_header:
	ld a,001h
	ld b,003h
	ld c,00eh
	ld hl,ui_header_brand
	call ui_write_field
	ld a,001h
	ld b,022h
	ld c,00dh
	ld hl,legacy_menu_select_title
	jp ui_write_field
ui_line_clear:
	xor a
	ld (ui_line_pos),a
	ld (ui_line_buffer),a
	ret
ui_line_fill_spaces:
	ld hl,ui_line_buffer
	ld b,040h
	ld a,020h
ui_line_space_loop:
	ld (hl),a
	inc hl
	djnz ui_line_space_loop
	xor a
	ld (hl),a
	ret
ui_line_append_char:
	push hl
	push de
	push bc
	ld c,a
	ld a,(ui_line_pos)
	cp 03fh
	jp nc,ui_line_append_char_done
	ld l,a
	ld h,000h
	ld de,ui_line_buffer
	add hl,de
	ld (hl),c
	ld a,(ui_line_pos)
	inc a
	ld (ui_line_pos),a
ui_line_append_char_done:
	pop bc
	pop de
	pop hl
	ret
ui_line_append_string:
	ld a,(hl)
	or a
	ret z
	call ui_line_append_char
	inc hl
	jp ui_line_append_string
ui_line_terminate:
	ld a,(ui_line_pos)
	ld l,a
	ld h,000h
	ld de,ui_line_buffer
	add hl,de
	xor a
	ld (hl),a
	ret
ui_line_append_u16:
	ld de,ui_num_buffer+5
	xor a
	ld (de),a
ui_u16_digits:
	push de
	call div10_u16
	pop de
	add a,030h
	dec de
	ld (de),a
	ld a,h
	or l
	jp nz,ui_u16_digits
	ex de,hl
	call ui_line_append_string
	ret
; Resident menu/track UI state and work buffers.  The v0.45.6 symbolic
; source proves this exact layout; v0.47 relocates it by +56h.
