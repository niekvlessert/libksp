; input.asm - KSP1PLAY v0.47.0

ui_capture_keys:
	call ui_scan_keyboard_rows
	ld a,(ui_keys3_now)
	ld (ui_keys3_prev),a
	ld a,(ui_keys4_now)
	ld (ui_keys4_prev),a
	ld a,(ui_keys5_now)
	ld (ui_keys5_prev),a
	ld a,(ui_keys7_now)
	ld (ui_keys7_prev),a
	ld a,(ui_keys8_now)
	ld (ui_keys8_prev),a
	ret
ui_poll_action:
	call ui_scan_keyboard_rows
	ld hl,ui_keys3_prev
	ld de,ui_keys3_now
	ld b,005h
ui_key_edge_loop:
	ld a,(hl)
	cpl
	ld c,a
	ld a,(de)
	ld (hl),a
	and c
	ld (de),a
	inc hl
	inc de
	djnz ui_key_edge_loop
	ld a,(ui_keys7_now)
	bit 2,a
	jp nz,ui_action_escape
	bit 7,a
	jp nz,ui_action_enter
	ld a,(ui_keys8_now)
	bit 5,a
	jp nz,ui_action_up
	bit 6,a
	jp nz,ui_action_down
	bit 4,a
	jp nz,ui_action_left
	bit 7,a
	jp nz,ui_action_right
	bit 0,a
	jp nz,ui_action_space
	ld a,(ui_keys3_now)
	bit 0,a
	jp nz,ui_action_c
	bit 5,a
	jp nz,ui_action_h
	bit 6,a
	jp nz,ui_action_i
	ld a,(ui_keys4_now)
	bit 1,a
	jp nz,ui_action_l
	bit 2,a
	jp nz,ui_action_m
	bit 3,a
	jp nz,ui_action_n
	bit 5,a
	jp nz,ui_action_p
	ld a,(ui_keys5_now)
	bit 1,a
	jp nz,ui_action_t
	xor a
	ret
ui_action_escape:
	ld a,001h
	jp ui_action_finish
ui_action_enter:
	ld a,002h
	jp ui_action_finish
ui_action_up:
	ld a,003h
	jp ui_action_finish
ui_action_down:
	ld a,004h
	jp ui_action_finish
ui_action_left:
	ld a,005h
	jp ui_action_finish
ui_action_right:
	ld a,006h
	jp ui_action_finish
ui_action_space:
	ld a,007h
	jp ui_action_finish
ui_action_l:
	ld a,008h
	jp ui_action_finish
ui_action_m:
	ld a,009h
	jp ui_action_finish
ui_action_t:
	ld a,00ah
	jp ui_action_finish
ui_action_i:
	ld a,00bh
	jp ui_action_finish
ui_action_c:
	ld a,00ch
	jp ui_action_finish
ui_action_h:
	ld a,00dh
	jp ui_action_finish
ui_action_n:
	ld a,00eh
	jp ui_action_finish
ui_action_p:
	ld a,00fh
ui_action_finish:
	push af
	ld a,(engine_running)
	or a
	call z,save_interrupt_hook
	pop af
	ret
ui_scan_keyboard_rows:
	in a,(PORT_KEY_ROW)
	ld e,a
	and 0f0h
	or 003h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	cpl
	and 061h
	ld (ui_keys3_now),a
	ld a,e
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_ROW)
	ld e,a
	and 0f0h
	or 004h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	cpl
	and 02eh
	ld (ui_keys4_now),a
	ld a,e
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_ROW)
	ld e,a
	and 0f0h
	or 005h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	cpl
	and 002h
	ld (ui_keys5_now),a
	ld a,e
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_ROW)
	ld e,a
	and 0f0h
	or 007h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	cpl
	and 084h
	ld (ui_keys7_now),a
	ld a,e
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_ROW)
	ld e,a
	and 0f0h
	or 008h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	cpl
	and 0f1h
	ld (ui_keys8_now),a
	ld a,e
	out (PORT_KEY_ROW),a
	ret
