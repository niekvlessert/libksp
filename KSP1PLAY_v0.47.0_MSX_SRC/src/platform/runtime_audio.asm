; runtime audio.asm - KSP1PLAY v0.47.0

validate_required_hardware:
	xor a
	ld (opl4_present),a
	ld (hardware_error_code),a
	ld a,(engine_required_hardware)
	ld b,a
	ld a,(AVAILABLE_HARDWARE)
	cpl
	and b
	jp nz,validate_hardware_missing
	ld a,b
	and 008h
	jp z,validate_hardware_opl4_ready
	ld a,(scc_slot)
	ld c,a
	ld a,(scc_slot_b)
	cp c
	jp z,validate_hardware_slots_bad
validate_hardware_opl4_ready:
	ld a,b
	and 040h
	ret z
	ld a,001h
	ld (opl4_present),a
	or a
	ret
validate_hardware_slots_bad:
	ld a,001h
	ld (hardware_error_code),a
	scf
	ret
validate_hardware_missing:
	ld a,002h
	ld (hardware_error_code),a
	scf
	ret
upload_current_mwk:
	ld a,(engine_required_hardware)
	and 040h
	ret z
	call page_runtime_available
	jp z,upload_current_mwk_unavailable
	jp SERVICE_OVL_UPLOAD_MWK
upload_current_mwk_unavailable:
	scf
	ret
free_mwk_segment:
	ld a,(mwk_segment_allocated)
	or a
	ret z
	ld a,(mwk_segment)
	call mapper_free_primary
	xor a
	ld (mwk_segment_allocated),a
	ret
prepare_opl4_init:
	ld a,(opl4_present)
	or a
	ret z
	ld a,(engine_required_hardware)
	and 040h
	ret z
	ld a,0f8h
	ld e,000h
	call opl4_write_wave
	ld a,0f9h
	ld e,000h
	jp opl4_write_wave
hard_reset_opl4:
	ld a,(opl4_present)
	or a
	ret z
	ld a,004h
	out (PORT_OPL4_FM0_A),a
	ld a,080h
	out (PORT_OPL4_FM0_D),a
	call opl4_fm_wait
	ld a,0f8h
	ld e,03fh
	call opl4_write_wave
	ld a,0f9h
	ld e,03fh
	call opl4_write_wave
	ld d,0b0h
	ld b,009h
opl4_mute_fm0:
	ld a,d
	out (PORT_OPL4_FM0_A),a
	xor a
	out (PORT_OPL4_FM0_D),a
	call opl4_fm_wait
	inc d
	djnz opl4_mute_fm0
	ld d,0b0h
	ld b,009h
opl4_mute_fm1:
	ld a,d
	out (PORT_OPL4_FM1_A),a
	xor a
	out (PORT_OPL4_FM1_D),a
	call opl4_fm_wait
	inc d
	djnz opl4_mute_fm1
	ld d,050h
	ld b,018h
opl4_mute_wave_level:
	ld a,d
	ld e,0ffh
	call opl4_write_wave
	inc d
	djnz opl4_mute_wave_level
	ld d,068h
	ld b,018h
opl4_mute_wave_key:
	ld a,d
	ld e,040h
	call opl4_write_wave
	inc d
	djnz opl4_mute_wave_key
	ret
opl4_write_wave:
	out (PORT_OPL4_WAVE_A),a
	call opl4_wave_wait
	ld a,e
	out (PORT_OPL4_WAVE_D),a
opl4_wave_wait:
	push bc
	ld b,010h
opl4_wave_wait_loop:
	in a,(PORT_OPL4_WAVE_A)
	djnz opl4_wave_wait_loop
	pop bc
	ret
opl4_fm_wait:
	push bc
	ld b,010h
opl4_fm_wait_loop:
	in a,(PORT_OPL4_FM0_A)
	djnz opl4_fm_wait_loop
	pop bc
	ret
; MoonSound MWK uploader state.  This layout is preserved verbatim from the
; readable v0.45.6 source; it is data, not the apparent Z80 instructions emitted

mwk_segment_allocated: db 0
mwk_segment:           db 0
mwk_source_mode:       db 0
mwk_buffer_ptr:        dw 0
mwk_buffer_left:       dw 0
mwk_block_count:       dw 0
mwk_block_index:       dw 0
mwk_block_table:       db 0,0,0
mwk_edit:              db 0
mwk_wave_count:        db 0
mwk_flag_ptr:          dw 0
mwk_flag:              db 0
mwk_tones_left:        db 0
mwk_sample_size:       dw 0
mwk_sample_addr:       db 0,0,0
mwk_header_addr:       dw 0
mwk_write_enabled:     db 0
mwk_signature:         db 'M','B','M','S',010h
opl4_present:           db 0
	ds 4,0                 ; pad to the fixed 3B10h visual-helper boundary
