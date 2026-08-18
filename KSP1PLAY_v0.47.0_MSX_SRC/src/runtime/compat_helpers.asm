; Runtime compatibility helpers and dynamic page gateway.

dynamic_gateway:
	ld (dynamic_page),hl
	in a,(PORT_MAPPER_P3)
	ld (dynamic_saved_p3),a
	ld a,i
	push af
	di
	push bc
	push de
	push hl
	push ix
	push iy
	exx
	push bc
	push de
	push hl
	exx
	ex af,af'
	push af
	ex af,af'
	call dynamic_install_page
	ld a,000h
	adc a,000h
	ld (dynamic_result),a
	ld a,(dynamic_saved_p3)
	out (PORT_MAPPER_P3),a
	ex af,af'
	pop af
	ex af,af'
	exx
	pop hl
	pop de
	pop bc
	exx
	pop iy
	pop ix
	pop hl
	pop de
	pop bc
	pop af
	jp po,dynamic_restore_iff_done
	ei
dynamic_restore_iff_done:
	ld a,(dynamic_result)
	or a
	ret z
	scf
	ret
dynamic_install_page:
	call restore_process_pages
	call page_runtime_available
	jp z,dynamic_install_bad
	jp RECON_ENTRY_DYNAMIC
dynamic_install_bad:
	xor a
	ld (dynamic_install_active),a
	call prepare_engine_page2
	scf
	ret
dual_scc_select_a:
	push af
	push bc
	ld a,(scc_slot)
	jp dual_scc_select_common
dual_scc_select_b:
	push af
	push bc
	ld a,(scc_slot_b)
dual_scc_select_common:
	call map_primary_slot_page2
	ld a,03fh
	ld (SCC_ENABLE_REG),a
	pop bc
	pop af
	ret
dual_scc_restore_ram:
	push af
	push bc
	push de
	push hl
	push ix
	push iy
	call map_ram_page2
	pop iy
	pop ix
	pop hl
	pop de
	pop bc
	pop af
	ret
map_ram_page2:
	in a,(PORT_PPI_A)
	and 0cfh
	ld b,a
	ld a,(original_a8)
	and 030h
	or b
	out (PORT_PPI_A),a
	ld a,(original_p2)
	jp map_p2
fcb_prepare_filename:
	ld hl,file_fcb
	xor a
	ld (hl),a
	ld de,file_fcb+1
	ld b,00bh
	ld a,020h
fcb_clear_name:
	ld (de),a
	inc de
	djnz fcb_clear_name
	xor a
	ld b,019h
fcb_clear_tail:
	ld (de),a
	inc de
	djnz fcb_clear_tail
	ld hl,filename
	ld a,(hl)
	or a
	jp z,fcb_prepare_bad
	inc hl
	ld a,(hl)
	cp 03ah
	dec hl
	jp nz,fcb_prepare_name
	ld a,(hl)
	and 0dfh
	sub 040h
	cp 001h
	jp c,fcb_prepare_bad
	cp 009h
	jp nc,fcb_prepare_bad
	ld (file_fcb),a
	inc hl
	inc hl
fcb_prepare_name:
	ld de,file_fcb+1
	ld b,008h
fcb_prepare_name_loop:
	ld a,(hl)
	or a
	jp z,fcb_prepare_ok
	cp 02eh
	jp z,fcb_prepare_ext_start
	cp 03ah
	jp z,fcb_prepare_bad
	cp 02fh
	jp z,fcb_prepare_bad
	cp 05ch
	jp z,fcb_prepare_bad
	ld c,a
	ld a,b
	or a
	jp z,fcb_prepare_bad
	ld a,c
	cp 061h
	jp c,fcb_prepare_name_store
	cp 07bh
	jp nc,fcb_prepare_name_store
	and 0dfh
fcb_prepare_name_store:
	ld (de),a
	inc de
	inc hl
	dec b
	jp fcb_prepare_name_loop
fcb_prepare_ext_start:
	inc hl
	ld de,file_fcb+9
	ld b,003h
fcb_prepare_ext_loop:
	ld a,(hl)
	or a
	jp z,fcb_prepare_ok
	cp 02eh
	jp z,fcb_prepare_bad
	cp 03ah
	jp z,fcb_prepare_bad
	cp 02fh
	jp z,fcb_prepare_bad
	cp 05ch
	jp z,fcb_prepare_bad
	ld c,a
	ld a,b
	or a
	jp z,fcb_prepare_bad
	ld a,c
	cp 061h
	jp c,fcb_prepare_ext_store
	cp 07bh
	jp nc,fcb_prepare_ext_store
	and 0dfh
fcb_prepare_ext_store:
	ld (de),a
	inc de
	inc hl
	dec b
	jp fcb_prepare_ext_loop
fcb_prepare_ok:
	or a
	ret
fcb_prepare_bad:
	scf
	ret
restore_secondary_slot_state:
	ld a,(space_previous+1)
	and 080h
	ret z
	ld a,(probe_base_byte)
	ld (SECONDARY_SLOT_REGISTER),a
	ret
ui_recompute_track_total:
	xor a
	ld (ui_total_time_valid),a
	ld (ui_auto_advance_pending),a
	ld hl,(ui_base_seconds)
	ld a,h
	or l
	ret z
	ld a,(track_flags)
	and 006h
	jp nz,ui_total_commit_hl
	ld a,(ui_loop_count)
	ld b,a
	ld d,h
	ld e,l
	dec b
ui_total_multiply_loop:
	jp z,ui_total_commit_hl
	add hl,de
	djnz ui_total_multiply_loop
ui_total_commit_hl:
	ld (ui_total_seconds),hl
	ld a,001h
	ld (ui_total_time_valid),a
	ret
	ld (hl),03eh
	push hl
	ld de,0002fh
	add hl,de
	ld (hl),03ch
	pop hl
	ret
	ld (hl),020h
	push hl
	ld de,0002fh
	add hl,de
	ld (hl),020h
	pop hl
	ret
	ld (hl),03eh
	push hl
	ld de,0003fh
	add hl,de
	ld (hl),03ch
	pop hl
	ret
