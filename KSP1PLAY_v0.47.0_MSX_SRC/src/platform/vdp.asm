; VDP interrupt guards, VRAM addressing and transfers.

vdp_irq_begin:
	ld a,i
	jp po,vdp_irq_was_disabled
	ld a,001h
	ld (vdp_saved_iff),a
	di
	ret
vdp_irq_was_disabled:
	xor a
	ld (vdp_saved_iff),a
	di
	ret
vdp_irq_end:
	ld a,(vdp_saved_iff)
	or a
	ret z
	ei
	ret
vram_set_warm_base_write:
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	xor a
	call vram_set_write_address
	ret
vram_set_write_address:
	ld d,a
	ld a,h
	rlca
	rlca
	and 003h
	ld e,a
	ld a,d
	add a,a
	add a,a
	or e
	and 007h
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
vram_set_read_address:
	ld d,a
	ld a,h
	rlca
	rlca
	and 003h
	ld e,a
	ld a,d
	add a,a
	add a,a
	or e
	and 007h
	out (PORT_VDP_CTRL),a
	ld a,08eh
	out (PORT_VDP_CTRL),a
	ld a,l
	out (PORT_VDP_CTRL),a
	ld a,h
	and 03fh
	out (PORT_VDP_CTRL),a
	ret
