; Startup, DOS1 file I/O and cache primitives.

start:
	ld sp,STACK_TOP
	call init_application_defaults
	call get_mapper_api
	jp c,mapper_error
	call capture_original_pages
	call kspos_detect_and_prepare
	jp c,memory_error
	jp ui_application
format_error:
	ld de,msg_err_ksp_format
	ld bc,00010h
	jp fatal_with_file
profile_error:
	ld de,msg_err_profile
	ld bc,0000dh
	jp fatal_with_file
hardware_error:
	ld a,(hardware_error_code)
	cp 001h
	jp nz,hardware_error_opl4
	ld de,msg_err_scc_slots
	ld bc,0000fh
	jp fatal_with_file
hardware_error_opl4:
	ld de,msg_err_opl4
	ld bc,0000ah
	jp fatal_with_file
mapper_error:
	ld de,msg_err_mapper128k
	ld bc,00011h
	jp fatal_with_file
memory_error:
	ld de,msg_err_memory
	ld bc,0000ch
	jp fatal_with_file
	ld de,msg_err_file
	ld bc,0000ah
	jp fatal_with_file
track_error:
	ld de,msg_err_track
	ld bc,0000bh
	jp fatal_with_file
decode_error:
	ld de,msg_err_decode
	ld bc,0000ch
	jp fatal_with_file
fatal_with_file:
	call write_stdout
	call cleanup
terminate_error_no_file:
	ld c,000h
	call BDOS
	ret
clean_exit:
	call cleanup
	ld c,000h
	call BDOS
	ret
init_application_defaults:
	call menu_reset_probe_state
	; Fixed one-byte initialization slot.
	nop
	ld (scc_slot_b+2),a
	ld (selected_track+1),a
	ld a,002h
	ld (scc_slot),a
	ld a,001h
	ld (scc_slot_b),a
	ld (AVAILABLE_HARDWARE),a
	xor a
	ld (HVAR_PRESENT),a
	ld (VISIBLE_TRACK_COUNT),a
	ld (VISIBLE_TRACK_COUNT+1),a
	ld hl,INVALID_WORD
	ld (PREPARED_ENGINE),hl
	ld (CURRENT_ENGINE),hl
	ld (IMPLEMENTATION_TRACK),hl
	ret
write_stdout:
write_stdout_loop:
	ld a,b
	or c
	ret z
	ld a,(de)
	push bc
	push de
	ld e,a
	ld c,002h
	call BDOS
	pop de
	pop bc
	inc de
	dec bc
	jp write_stdout
fcb_open_current:
	call fcb_prepare_filename
	ret c
	ld de,file_fcb
	ld c,00fh
	call BDOS
	or a
	jp nz,fcb_open_failed
	ld hl,00001h
	ld (file_fcb+14),hl
	xor a
	ld (file_fcb+33),a
	ld (file_fcb+34),a
	ld (file_fcb+35),a
	ld (file_fcb+36),a
	ld a,001h
	ld (file_open),a
	or a
	ret
fcb_open_failed:
	scf
	ret
fcb_close_current:
	ld a,(file_open)
	or a
	ret z
	ld de,file_fcb
	ld c,010h
	call BDOS
fcb_close_mark_closed:
	xor a
	ld (file_open),a
	ret
fcb_read_current:
	ld (fcb_request_count),bc
	push bc
	ld c,01ah
	call BDOS
	pop bc
	ld h,b
	ld l,c
	ld de,file_fcb
	ld c,027h
	call BDOS
	or a
	jp nz,fcb_read_failed
	ld de,(fcb_request_count)
	or a
	sbc hl,de
	jp nz,fcb_read_failed
	xor a
	ret
fcb_read_failed:
	ld a,001h
	or a
	ret
read_at:
	ld (tmp_offset_hi),a
	ld (tmp_offset_lo),hl
	ld a,(file_cache_ready)
	or a
	jp z,read_at_disk
	push bc
	push de
	call vdp_irq_begin
	ld hl,(tmp_offset_lo)
	ld de,KSPMENU_ENTRY_VDP_SETUP
	add hl,de
	ld a,(tmp_offset_hi)
	adc a,000h
	call vram_set_read_address
	pop de
	pop bc
read_at_vram_loop:
	ld a,b
	or c
	jp z,read_at_vram_done
	in a,(PORT_VDP_DATA)
	ld (de),a
	inc de
	dec bc
	jp read_at_vram_loop
read_at_vram_done:
	call vdp_irq_end
	xor a
	ret
read_at_disk:
	call mute_fmpac_before_disk_io
	jp RECON_ENTRY_DISK_READ_CACHED
preload_file_cache:
	xor a
	ld a,(ksp_file_size_top)
	or a
	jp nz,preload_file_cache_bad
	ld a,(ksp_file_size_hi)
	cp 002h
	jp nc,preload_file_cache_bad
	or a
	jp z,preload_file_cache_size_ok
	ld hl,(ksp_file_size_lo)
	ld de,FILE_CACHE_MAX_BYTES_EXCLUSIVE
	or a
	sbc hl,de
	jp nc,preload_file_cache_bad
preload_file_cache_size_ok:
	ld hl,(ksp_file_size_lo)
	ld (cache_remaining),hl
	ld a,(ksp_file_size_hi)
	ld (cache_remaining+2),a
	ld (file_cache_size),hl
	ld (file_cache_size+2),a
	xor a
	ld (cache_written),a
	ld (cache_written+1),a
	ld (cache_written+2),a
preload_file_cache_loop:
	ld hl,(cache_remaining)
	ld a,(cache_remaining+2)
	or h
	or l
	jp z,preload_file_cache_done
	ld de,IO_BUFFER_SIZE
	ld a,(cache_remaining+2)
	or a
	jp nz,preload_file_cache_512
	or a
	sbc hl,de
	jp nc,preload_file_cache_512
	add hl,de
	jp preload_file_cache_count
preload_file_cache_512:
	ld hl,IO_BUFFER_SIZE
preload_file_cache_count:
	ld (cache_chunk),hl
	ld hl,(cache_written)
	ld a,(cache_written+2)
	ld de,io_buffer
	ld bc,(cache_chunk)
	call read_at
	jp nz,preload_file_cache_bad
	call vdp_irq_begin
	ld hl,(cache_written)
	ld de,KSPMENU_ENTRY_VDP_SETUP
	add hl,de
	ld a,(cache_written+2)
	adc a,000h
	call vram_set_write_address
	ld bc,(cache_chunk)
	ld hl,io_buffer
preload_file_cache_write:
	ld a,b
	or c
	jp z,preload_file_cache_written
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	dec bc
	jp preload_file_cache_write
preload_file_cache_written:
	call vdp_irq_end
	ld hl,(cache_written)
	ld de,(cache_chunk)
	add hl,de
	ld (cache_written),hl
	ld a,(cache_written+2)
	adc a,000h
	ld (cache_written+2),a
	ld hl,(cache_remaining)
	ld de,(cache_chunk)
	or a
	sbc hl,de
	ld (cache_remaining),hl
	ld a,(cache_remaining+2)
	sbc a,000h
	ld (cache_remaining+2),a
	jp preload_file_cache_loop
preload_file_cache_done:
	ld a,001h
	ld (file_cache_ready),a
	or a
	ret
preload_file_cache_bad:
	xor a
	ld (file_cache_ready),a
	scf
	ret
allocate_page3_workram_segment:
	ld a,(page3_workram_profile)
	or a
	jp nz,allocate_page3_workram_needed
	call kspos_configure_engine_runtime
	jp kspos_verify_engine_memory
allocate_page3_workram_needed:
	call mapper_alloc_user_primary
	ret c
	ld (engine_p3_segment),a
	ld a,001h
	ld (engine_p3_segment_allocated),a
	call kspos_configure_engine_runtime
	jp kspos_verify_engine_memory
initialize_page3_workram_segment:
	ld a,(page3_workram_profile)
	or a
	ret z
	di
	ld a,(engine_p3_segment)
	out (PORT_MAPPER_P3),a
	ld a,0ffh
	ld hl,KSPOS_RT_KSPOS_DISK_CALL
	ld (hl),a
	ld de,KSPOS_RT_KSPOS_DISK_CALL+1
	ld bc,PAGE_16K_CLEAR_BYTES_AFTER_0
	ldir
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ret
free_page3_workram_segment:
	ld a,(engine_p3_segment_allocated)
	or a
	ret z
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ld a,(engine_p3_segment)
	call mapper_free_primary
	xor a
	ld (engine_p3_segment_allocated),a
	ret
allocate_template_segment:
	call mapper_alloc_user_primary
	ret c
	ld (template_segment),a
	ld a,001h
	ld (template_segment_allocated),a
	or a
	ret
free_template_segment:
	ld a,(template_segment_allocated)
	or a
	ret z
	ld a,(template_segment)
	call mapper_free_primary
	xor a
	ld (template_segment_allocated),a
	ld (template_cache_ready),a
	ret
preload_template_page:
	call restore_process_pages
	ld a,(template_segment)
	call map_p1
	call decode_template_page
	push af
	call restore_process_pages
	pop af
	ret c
	ld a,001h
	ld (template_cache_ready),a
	or a
	ret

; Resolve the MSX memory-mapper API and build the allocator view used by the
; engine/template/hot-page loaders. Carry signals that no usable mapper exists.
