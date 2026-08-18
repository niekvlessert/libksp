; Stream I/O, ZX0 decode and hot/cold page data paths.

; stream_begin
; Opens a bounded resource stream from RAM cache or disk and initializes decode state.
stream_begin:
	ld (stream_offset_lo),hl
	ld (stream_offset_hi),a
	ld h,b
	ld l,c
	ld (stream_remaining),hl
	xor a
	ld (stream_remaining+2),a
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld (input_count),hl
	ld (input_ptr),hl
	ld (zx_bit_mask),a
	ld (zx_backtrack),a
	ld (stream_vdp_guard),a
	ld a,(file_cache_ready)
	or a
	jp z,stream_begin_disk
	ld a,001h
	ld (stream_source),a
	ld (stream_vdp_guard),a
	call vdp_irq_begin
	ld hl,(stream_offset_lo)
	ld de,KSPMENU_ENTRY_VDP_SETUP
	add hl,de
	ld a,(stream_offset_hi)
	adc a,000h
	call vram_set_read_address
	or a
	ret
stream_begin_disk:
	call mute_fmpac_before_disk_io
	xor a
	ld (stream_source),a
	or a
	ret
stream_end:
	ld a,(stream_vdp_guard)
	or a
	ret z
	xor a
	ld (stream_vdp_guard),a
	call vdp_irq_end
	ret

; Decode a ZX0-backed KSP stream through the selected output target (linear,
; HOT mapper data, or WARM/runtime storage).
; zx_decode_stream
; Decodes a ZX stream through the configured output/history dispatchers.
; Output size is bounded by zx_remaining.
zx_decode_stream:
	call zx_decode
	push af
	call stream_end
	pop af
	ret
stream_refill:
	ld a,(mapped_p1)
	ld (saved_map_p1),a
	ld a,(mapped_p2)
	ld (saved_map_p2),a
	call restore_process_pages
	ld hl,(stream_remaining)
	ld a,(stream_remaining+2)
	or h
	or l
	jp z,refill_error
	ld de,IO_BUFFER_SIZE
	ld a,(stream_remaining+2)
	or a
	jp nz,refill_use_512
	or a
	sbc hl,de
	jp nc,refill_use_512
	add hl,de
	jp refill_count_ready
refill_use_512:
	ld hl,IO_BUFFER_SIZE
refill_count_ready:
	ld (refill_count),hl
	ld hl,(stream_offset_lo)
	ld (tmp_offset_lo),hl
	ld a,(stream_offset_hi)
	ld (tmp_offset_hi),a
	ld de,io_buffer
	ld bc,(refill_count)
	call RECON_ENTRY_DISK_READ_CACHED
	jp nz,refill_error
	ld hl,(tmp_offset_lo)
	ld (stream_offset_lo),hl
	ld a,(tmp_offset_hi)
	ld (stream_offset_hi),a
	ld hl,(refill_count)
	ld (input_count),hl
	ld d,h
	ld e,l
	ld hl,(stream_remaining)
	or a
	sbc hl,de
	ld (stream_remaining),hl
	ld a,(stream_remaining+2)
	sbc a,000h
	ld (stream_remaining+2),a
	ld hl,io_buffer
	ld (input_ptr),hl
	call restore_saved_maps
	or a
	ret
refill_error:
	call restore_saved_maps
	scf
	ret
restore_saved_maps:
	ld a,(saved_map_p1)
	call map_p1
	ld a,(saved_map_p2)
	call map_p2
	ret
zx_read_byte:
	ld a,(stream_source)
	or a
	jp z,zx_read_byte_disk
	ld hl,(stream_remaining)
	ld a,(stream_remaining+2)
	or h
	or l
	jp z,zx_read_cache_eof
	in a,(PORT_VDP_DATA)
	ld (zx_last_byte),a
	ld hl,(stream_remaining)
	ld a,h
	or l
	jp nz,zx_read_cache_low
	ld hl,INVALID_WORD
	ld (stream_remaining),hl
	ld a,(stream_remaining+2)
	dec a
	ld (stream_remaining+2),a
	ld a,(zx_last_byte)
	or a
	ret
zx_read_cache_low:
	dec hl
	ld (stream_remaining),hl
	ld a,(zx_last_byte)
	or a
	ret
zx_read_cache_eof:
	scf
	ret
zx_read_byte_disk:
	ld hl,(input_count)
	ld a,h
	or l
	jp nz,zx_read_have
	push bc
	push de
	push hl
	call stream_refill
	pop hl
	pop de
	pop bc
	ret c
zx_read_have:
	ld hl,(input_ptr)
	ld a,(hl)
	inc hl
	ld (input_ptr),hl
	ld hl,(input_count)
	dec hl
	ld (input_count),hl
	ld (zx_last_byte),a
	or a
	ret
zx_read_bit:
	ld a,(zx_backtrack)
	or a
	jp z,zx_read_bit_normal
	xor a
	ld (zx_backtrack),a
	ld a,(zx_last_byte)
	and 001h
	ret
zx_read_bit_normal:
	ld a,(zx_bit_mask)
	or a
	jp nz,zx_have_mask
	call zx_read_byte
	ret c
	ld (zx_bit_value),a
	ld a,080h
	ld (zx_bit_mask),a
zx_have_mask:
	push de
	ld e,a
	ld a,(zx_bit_value)
	and e
	jp z,zx_bit_zero
	ld a,001h
	jp zx_bit_result
zx_bit_zero:
	xor a
zx_bit_result:
	pop de
	push af
	ld a,(zx_bit_mask)
	srl a
	ld (zx_bit_mask),a
	pop af
	or a
	ret
zx_gamma_normal:
	xor a
	ld (gamma_invert),a
	jp zx_gamma
zx_gamma_inverted:
	ld a,001h
	ld (gamma_invert),a
zx_gamma:
	ld bc,00001h
zx_gamma_loop:
	call zx_read_bit
	ret c
	or a
	ret nz
	sla c
	rl b
	call zx_read_bit
	ret c
	ld d,a
	ld a,(gamma_invert)
	xor d
	or c
	ld c,a
	jp zx_gamma_loop
zx_set_output_size:
	ld (zx_remaining),hl
	ld (zx_remaining+2),a
	xor a
	ld (zx_last_offset+2),a
	ld (zx_output_pos+1),a
	ld (zx_output_pos+2),a
	call RECON_ENTRY_ZX_SELECT
	ret
zx_output_finished:
	ld hl,(zx_remaining)
	ld a,(zx_remaining+2)
	or h
	or l
	ret
zx_decode:
	ld hl,00001h
	ld (zx_last_offset),hl
	call zx_gamma_normal
	ret c
	call zx_copy_literals
	ret c
zx_main_loop:
	call zx_output_finished
	or a
	ret z
	call zx_read_bit
	ret c
	or a
	jp nz,zx_new_offset
	call zx_gamma_normal
	ret c
	call zx_copy_match
	ret c
	call zx_output_finished
	or a
	ret z
	call zx_read_bit
	ret c
	or a
	jp nz,zx_new_offset
	call zx_gamma_normal
	ret c
	call zx_copy_literals
	ret c
	jp zx_main_loop
zx_new_offset:
	call zx_gamma_inverted
	ret c
	ld h,b
	ld l,c
	ld de,ZX0_END_MARKER
	or a
	sbc hl,de
	jp z,zx_decode_done
	add hl,de
	ld a,007h
zx_offset_shift:
	add hl,hl
	dec a
	jp nz,zx_offset_shift
	push hl
	call zx_read_byte
	pop hl
	ret c
	ld e,a
	srl e
	ld d,000h
	or a
	sbc hl,de
	ld (zx_last_offset),hl
	ld a,001h
	ld (zx_backtrack),a
	call zx_gamma_normal
	ret c
	inc bc
	call zx_copy_match
	ret c
	call zx_output_finished
	or a
	ret z
	call zx_read_bit
	ret c
	or a
	jp nz,zx_new_offset
	call zx_gamma_normal
	ret c
	call zx_copy_literals
	ret c
	jp zx_main_loop
zx_decode_done:
	or a
	ret
zx_copy_literals:
	ld a,b
	or c
	ret z
	call zx_read_byte
	ret c
	call zx_write_dispatch
	ret c
	dec bc
	jp zx_copy_literals
zx_copy_match:
	ld a,b
	or c
	ret z
	push bc
	ld hl,(zx_last_offset)
	call zx_read_history
	pop bc
	ret c
	call zx_write_dispatch
	ret c
	dec bc
	jp zx_copy_match
zx_write_dispatch:
	jp zx_write_linear
zx_write_hot:
	push bc
	call hot_write_byte
	pop bc
	jp zx_write_account
zx_write_linear:
	ld hl,(linear_base)
	ld de,(zx_last_offset+2)
	add hl,de
	ld (hl),a
	jp zx_write_account
zx_write_warm:
	push af
	ld hl,(zx_last_offset+2)
	ld a,h
	and 07fh
	add a,040h
	ld h,a
	pop af
	ld (hl),a
	out (PORT_VDP_DATA),a
	jp zx_write_account
zx_write_account:
	ld hl,(zx_last_offset+2)
	inc hl
	ld (zx_last_offset+2),hl
	ld a,h
	or l
	jp nz,zx_position_done
	ld a,(zx_output_pos+2)
	inc a
	ld (zx_output_pos+2),a
zx_position_done:
	ld hl,(zx_remaining)
	ld a,(zx_remaining+2)
	or h
	or l
	jp z,zx_write_overflow
	ld hl,(zx_remaining)
	ld a,h
	or l
	jp nz,zx_remaining_low_nonzero
	ld hl,INVALID_WORD
	ld (zx_remaining),hl
	ld a,(zx_remaining+2)
	dec a
	ld (zx_remaining+2),a
	or a
	ret
zx_remaining_low_nonzero:
	dec hl
	ld (zx_remaining),hl
	or a
	ret
zx_write_overflow:
	scf
	ret
zx_read_history:
	push hl
	ld de,(zx_last_offset+2)
	ex de,hl
	pop de
	or a
	sbc hl,de
	ld a,(zx_output_pos+2)
	sbc a,000h
	ld (history_pos_lo),hl
	ld (history_pos_hi),a
	jp zx_read_linear
zx_read_hot:
	call hot_read_byte
	ret
zx_read_linear:
	ld hl,(linear_base)
	ld de,(history_pos_lo)
	add hl,de
	ld a,(hl)
	or a
	ret
zx_read_warm:
	ld hl,(history_pos_lo)
	ld a,h
	and 07fh
	add a,040h
	ld h,a
	ld a,(hl)
	or a
	ret
hot_write_byte:
	push af
	call hot_output_segment

	ld b,a
	ld a,(hot_write_mapped)
	cp b
	jp z,hot_write_seg_ok
	ld a,b
	ld (hot_write_mapped),a
	ld hl,hot_segments
	ld c,a
	ld b,000h
	add hl,bc
	ld a,(hl)
	call map_p2
hot_write_seg_ok:
	ld hl,(zx_last_offset+2)
	ld a,h
	and 03fh
	or 080h
	ld h,a
	pop af
	ld (hl),a
	ret
hot_read_byte:
	call hot_history_segment
	ld c,a
	call hot_output_segment
	cp c
	jp nz,hot_read_other
	ld hl,(history_pos_lo)
	ld a,h
	and 03fh
	or 080h
	ld h,a
	ld a,(hl)
	or a
	ret
hot_read_other:
	ld a,(hot_read_mapped)
	cp c
	jp z,hot_read_seg_ok
	ld a,c
	ld (hot_read_mapped),a
	ld hl,hot_segments
	ld e,a
	ld d,000h
	add hl,de
	ld a,(hl)
	call map_p1
hot_read_seg_ok:
	ld hl,(history_pos_lo)
	ld a,h
	and 03fh
	or 040h
	ld h,a
	ld a,(hl)
	or a
	ret
hot_output_segment:
	ld a,(zx_output_pos+2)
	add a,a
	add a,a
	ld b,a
	ld a,(zx_output_pos+1)
	rlca
	rlca
	and 003h
	or b
	ret
hot_history_segment:
	ld a,(history_pos_hi)
	add a,a
	add a,a
	ld b,a
	ld a,(history_pos_lo+1)
	rlca
	rlca
	and 003h
	or b
	ret
configure_engine_refresh:
	ld a,(BIOS_RG9SAV)
	ld (original_vdp_r9),a
	ld b,a
	ld hl,(engine_play_frequency)
	ld a,l
	cp 032h
	ld a,b
	jp nz,configure_refresh_60
	or 002h
	jp configure_refresh_write
configure_refresh_60:
	and 0fdh
configure_refresh_write:
	call write_vdp_r9
	ld a,001h
	ld (refresh_saved),a
	ret
restore_refresh_rate:
	ld a,(refresh_saved)
	or a
	ret z
	xor a
	ld (refresh_saved),a
	ld a,(original_vdp_r9)
write_vdp_r9:
	ld b,a
	call vdp_irq_begin
	ld a,b
	ld (BIOS_RG9SAV),a
	out (PORT_VDP_CTRL),a
	ld a,089h
	out (PORT_VDP_CTRL),a
	jp vdp_irq_end
