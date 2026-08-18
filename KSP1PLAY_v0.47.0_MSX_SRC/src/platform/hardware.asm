; Hardware detection and SCC/SCC+ slot probing.

; kspos_detect_and_prepare
; Detects KSPOS/runtime availability and prepares shared HVAR/overlay state.
kspos_detect_and_prepare:
	xor a
	ld (KSPOS_FLAGS),a
	ld hl,KSPOS_INFO
	ld a,(hl)
	cp 04bh
	jp nz,kspos_not_present
	inc hl
	ld a,(hl)
	cp 050h
	jp nz,kspos_not_present
	inc hl
	ld a,(hl)
	cp 04fh
	jp nz,kspos_not_present
	inc hl
	ld a,(hl)
	cp 053h
	jp nz,kspos_not_present
	ld a,(KSPOS_API_VERSION)
	cp 001h
	jp nz,kspos_not_present
	call mapper_alloc_user_primary
	ret c
	ld (KSPOS_RUNTIME_P0),a
	ld a,(original_p0)
	ld (KSPOS_PLAYER_P0),a
	ld a,(original_p3)
	ld (KSPOS_ORIGINAL_P3),a
	ld (KSPOS_ENGINE_P3),a
	ld a,(mapper_segment_mask)
	inc a
	ld (KSPOS_TOTAL_SEGMENTS),a
	ld a,(mapper_pool_count)
	ld (KSPOS_FREE_SEGMENTS),a
	ld a,080h
	ld (KSPOS_FLAGS),a
	ld a,001h
	ld (KSPOS_UNAVAILABLE_COUNT),a
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld (KSPOS_RANGE0_START),hl
	ld hl,PAGE_16K_LAST_OFFSET
	ld (KSPOS_RANGE0_END),hl
	ld hl,INVALID_WORD
	ld (KSPOS_RANGE1_START),hl
	ld (KSPOS_RANGE1_END),hl
	call restore_process_pages
	ld a,(KSPOS_RUNTIME_P0)
	call map_p2
	xor a
	ld hl,KSPMENU_ENTRY_VDP_SETUP
	ld (hl),a
	ld de,08001h
	ld bc,PAGE_16K_LAST_OFFSET
	ldir
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld de,KSPMENU_ENTRY_VDP_SETUP
	ld bc,KSPOS_GATEWAY_COPY_BYTES
	ldir
	ld a,(original_p2)
	call map_p2
	call install_runtime_images
	or a
	ret
kspos_not_present:
	or a
	ret
menu_overlay_draw_header:
	call ui_line_fill_spaces
	xor a
	ld (ui_line_pos),a
	ld hl,legacy_menu_title
	call ui_line_append_string
	ld a,030h
	ld (ui_line_pos),a
	ld a,(menu_scc_count)
	or a
	ld hl,menu_hw_no_scc
	jp z,menu_header_scc_ready
	cp 002h
	ld hl,menu_hw_two_scc
	jp nc,menu_header_scc_ready
	ld a,(menu_hw_flags)
	bit 1,a
	ld hl,menu_hw_scc
	jp z,menu_header_scc_ready
	ld hl,menu_hw_sccplus
menu_header_scc_ready:
	call ui_line_append_string
	call ui_line_terminate
	ld a,000h
	ld b,00fh
	call menu_draw_built_line
	call ui_line_fill_spaces
	xor a
	ld (ui_line_pos),a
	ld hl,legacy_menu_select_title
	call ui_line_append_string
	ld a,02ah
	ld (ui_line_pos),a
	ld a,(menu_hw_flags)
	bit 2,a
	jp z,menu_header_no_fmpac
	ld hl,menu_hw_fmpac
	call ui_line_append_string
menu_header_no_fmpac:
	ld a,(menu_hw_flags)
	bit 3,a
	jp z,menu_header_no_moonsound
	ld hl,menu_hw_moonsound
	call ui_line_append_string
menu_header_no_moonsound:
	call ui_line_terminate
	ld a,001h
	ld b,007h
	call menu_draw_built_line
	ld a,(menu_hw_flags)
	bit 4,a
	ret z
	call ui_line_fill_spaces
	ld a,02ah
	ld (ui_line_pos),a
	ld hl,menu_hw_music32
	ld a,(menu_hw_flags)
	bit 5,a
	jp z,menu_header_music_ready
	ld hl,menu_hw_music256
menu_header_music_ready:
	call ui_line_append_string
	call ui_line_terminate
	ld a,002h
	ld b,007h
	jp menu_draw_built_line
menu_draw_built_line:
	push af
	push bc
	ld hl,ui_line_buffer
	ld de,ui_string_buffer
	ld bc,00040h
	ldir
	xor a
	ld (ui_string_buffer+64),a
	pop bc
	pop af
	ld hl,ui_string_buffer
	jp ui_text_line
; menu_detect_hardware
; Detects SCC/SCC+/FM-PAC/MSX-AUDIO/MoonSound and publishes cached hardware flags.
menu_detect_hardware:
	ld a,(KSPOS_HW_CACHE_FLAGS)
	bit 7,a
	jr z,menu_detect_hardware_uncached
	and 07fh
	ld (menu_hw_flags),a
	ld a,(KSPOS_HW_CACHE_SCC_COUNT)
	ld (menu_scc_count),a
	ret
menu_detect_hardware_uncached:
	xor a
	ld (menu_hw_flags),a
	ld (menu_scc_count),a
	call menu_scan_scc_slots_preserve_slot_state
	; Deliberate post-slot-probe settling space before probing other devices.
	nop
	nop
	nop
	nop
	nop
	call menu_probe_internal_fmpac
	ld a,001h
	call menu_probe_rom_slot
	ld a,002h
	call menu_probe_rom_slot
	call menu_detect_opl4
	jp c,menu_detect_no_moonsound
	ld a,(menu_hw_flags)
	or 008h
	ld (menu_hw_flags),a
menu_detect_no_moonsound:
	call menu_cache_hardware_detection
	ret
menu_publish_hardware:
	ld a,001h
	ld b,a
	ld a,(menu_scc_count)
	or a
	jp z,menu_publish_no_scc
	ld a,b
	or 002h
	ld b,a
	ld a,(menu_scc_count)
	cp 002h
	jp c,menu_publish_no_dual
	ld a,b
	or 008h
	ld b,a
menu_publish_no_dual:
	ld a,(menu_hw_flags)
	bit 1,a
	jp z,menu_publish_no_scc
	ld a,b
	or 004h
	ld b,a
menu_publish_no_sccplus:
menu_publish_no_scc:
	ld a,(menu_hw_flags)
	bit 2,a
	jp z,menu_publish_no_fmpac
	ld a,b
	or 010h
	ld b,a
menu_publish_no_fmpac:
	ld a,(menu_hw_flags)
	bit 4,a
	jp z,menu_publish_no_y8950
	ld a,b
	or 020h
	ld b,a
menu_publish_no_y8950:
	ld a,(menu_hw_flags)
	bit 3,a
	jp z,menu_publish_done
	ld a,b
	or 040h
	ld b,a
menu_publish_done:
	ld a,b
	ld (AVAILABLE_HARDWARE),a
	ret
menu_detect_opl4:
	ld a,005h
	out (PORT_OPL4_FM1_A),a
	call opl4_fm_wait
	ld a,003h
	out (PORT_OPL4_FM1_D),a
	call opl4_fm_wait
	ld a,002h
	out (PORT_OPL4_WAVE_A),a
	call opl4_wave_wait
	in a,(PORT_OPL4_WAVE_D)
	push af
	ld a,005h
	out (PORT_OPL4_FM1_A),a
	call opl4_fm_wait
	xor a
	out (PORT_OPL4_FM1_D),a
	call opl4_fm_wait
	pop af
	and 0e0h
	cp 020h
	ret z
	scf
	ret
; A is a complete BIOS slot ID (primary 00-03h or expanded 80-8Fh).
; Return bit 0 for SCC capability and bit 1 for SCC+ capability.
menu_probe_scc_slot:
	ld (menu_saved_a8),a
	xor a
	ld (menu_music_save8),a
	ld a,(menu_saved_a8)
	ld h,080h
	call BIOS_ENASLT
	xor a
	ld (SCC_ENABLE_REG),a
	ld hl,SCC_WAVE_BASE
	call probe_writable_memory_byte
	jp c,menu_probe_normal_done
	ld a,03fh
	ld (SCC_ENABLE_REG),a
	ld hl,SCC_WAVE_BASE
	call probe_writable_memory_byte
	jp nc,menu_probe_normal_disable
	ld a,(menu_music_save8)
	or 001h
	ld (menu_music_save8),a
menu_probe_normal_disable:
	xor a
	ld (SCC_ENABLE_REG),a
menu_probe_normal_done:
	xor a
	ld (SCCPLUS_BANK_REG),a
	ld (SCCPLUS_MODE_REG),a
	ld hl,SCCPLUS_WAVE_BASE
	call probe_writable_memory_byte
	jp c,menu_probe_plus_done
	ld a,020h
	ld (SCCPLUS_MODE_REG),a
	ld a,080h
	ld (SCCPLUS_BANK_REG),a
	ld hl,SCCPLUS_WAVE_BASE
	call probe_writable_memory_byte
	jp nc,menu_probe_plus_disable
	ld a,(menu_music_save8)
	or 002h
	ld (menu_music_save8),a
menu_probe_plus_disable:
	xor a
	ld (SCCPLUS_BANK_REG),a
	ld (SCCPLUS_MODE_REG),a
menu_probe_plus_done:
	call restore_process_pages
	ld a,(menu_music_save8)
	ret
menu_cache_hardware_detection:
	call menu_publish_hardware
	ld a,(menu_hw_flags)
	or 080h
	ld (KSPOS_HW_CACHE_FLAGS),a
	ld a,(menu_scc_count)
	ld (KSPOS_HW_CACHE_SCC_COUNT),a
	ret
	ds 8,0		; 47f5-47fc zero-filled reserved/data bytes (compact NOP run)
menu_probe_internal_fmpac:
	xor a
	ld (menu_probe_primary_id),a
menu_probe_internal_primary:
	ld a,(menu_probe_primary_id)
	ld e,a
	ld d,000h
	ld hl,BIOS_EXPTBL
	add hl,de
	bit 7,(hl)
	jp nz,menu_probe_internal_expanded
	ld a,e
	call menu_probe_apr_slot
	ret z
	jp menu_probe_internal_next_primary
menu_probe_internal_expanded:
	xor a
	ld (menu_probe_secondary_id),a
menu_probe_internal_secondary:
	ld a,(menu_probe_secondary_id)
	add a,a
	add a,a
	ld c,a
	ld a,(menu_probe_primary_id)
	or c
	or 080h
	call menu_probe_apr_slot
	ret z
	ld a,(menu_probe_secondary_id)
	inc a
	ld (menu_probe_secondary_id),a
	cp 004h
	jp c,menu_probe_internal_secondary
menu_probe_internal_next_primary:
	ld a,(menu_probe_primary_id)
	inc a
	ld (menu_probe_primary_id),a
	cp 004h
	jp c,menu_probe_internal_primary
	or 001h
	ret
menu_probe_apr_slot:
	ld c,a
	ld hl,ROM_SIGNATURE_FMPAC_ADDR
	ld de,menu_sig_internal_fmpac
	ld b,ROM_SIGNATURE_BYTES
	call menu_rom_match
	ret nz
	ld a,(menu_hw_flags)
	or 004h
	ld (menu_hw_flags),a
	xor a
	ret
menu_probe_rom_slot:
	ld c,a
	ld hl,ROM_SIGNATURE_FMPAC_ADDR
	ld de,menu_sig_fmpac
	ld b,ROM_SIGNATURE_BYTES
	call menu_rom_match
	jp nz,menu_probe_not_fmpac
	ld a,(menu_hw_flags)
	or 004h
	ld (menu_hw_flags),a
menu_probe_not_fmpac:
	ld hl,ROM_SIGNATURE_MUSICBOX_ADDR
	ld de,menu_sig_musicbox
	ld b,ROM_SIGNATURE_BYTES
	call menu_rom_match
	ret nz
	ld a,(menu_hw_flags)
	or 010h
	ld (menu_hw_flags),a
	call menu_detect_music_ram
	ret c
	ld a,(menu_hw_flags)
	or 020h
	ld (menu_hw_flags),a
	ret
menu_rom_match:
	push bc
	push hl
	push de
	ld a,c
	call BIOS_RDSLT
	ld c,a
	pop de
	pop hl
	ld a,(de)
	cp c
	pop bc
	ret nz
	inc hl
	inc de
	djnz menu_rom_match
	xor a
	ret
menu_detect_music_ram:
	ld hl,dynamic_gateway
	call menu_y8950_read
	ret c
	ld (menu_music_save8),a
	xor a
	ld hl,dynamic_gateway
	call menu_y8950_write
	jp c,menu_music_32k
	ld hl,dynamic_gateway
	call menu_y8950_read
	jp c,menu_music_32k
	or a
	jp nz,menu_music_32k
	ld a,0ffh
	ld hl,dynamic_gateway
	call menu_y8950_write
	jp c,menu_music_32k
	ld hl,dynamic_gateway
	call menu_y8950_read
	jp c,menu_music_32k
	inc a
	jp nz,menu_music_32k
	ld hl,dynamic_gateway
	ld a,(menu_music_save8)
	call menu_y8950_write
	or a
	ret
menu_music_32k:
	scf
	ret
	ld hl,ENGINE_DIRECT_CALL_PATCH
menu_y8950_read:
	call menu_y8950_setup
	ret c
	ld a,007h
	out (0c0h),a
	ld a,020h
	out (0c1h),a
	ld a,00fh

	out (0c0h),a
	in a,(0c1h)
	in a,(0c1h)
	call menu_y8950_wait
	ret c
	ld a,00fh
	out (0c0h),a
	in a,(0c1h)
	push af
	call menu_y8950_finish
	pop af
	or a
	ret
menu_y8950_write:
	push af
	call menu_y8950_setup
	jp c,menu_y8950_write_fail
	ld a,007h
	out (0c0h),a
	ld a,060h
	out (0c1h),a
	call menu_y8950_wait
	jp c,menu_y8950_write_fail
	ld a,00fh
	out (0c0h),a
	pop af
	out (0c1h),a
	call menu_y8950_finish
	or a
	ret
menu_y8950_write_fail:
	pop af
	scf
	ret
menu_y8950_setup:
	push hl
	ld a,008h
	out (0c0h),a
	xor a
	out (0c1h),a
	pop hl
	ld a,009h
	out (0c0h),a
	ld a,l
	out (0c1h),a
	ld a,00ah
	out (0c0h),a
	ld a,h
	out (0c1h),a
	ld a,00bh
	out (0c0h),a
	ld a,0ffh
	out (0c1h),a
	ld a,00ch
	out (0c0h),a
	ld a,0ffh
	out (0c1h),a
	ld a,004h
	out (0c0h),a
	xor a
	out (0c1h),a
	or a
	ret
menu_y8950_wait:
	ld b,000h
menu_y8950_wait_loop:
	in a,(0c0h)
	and 008h
	ret nz
	djnz menu_y8950_wait_loop
	scf
	ret
menu_y8950_finish:
	ld a,007h
	out (0c0h),a
	ld a,001h
	out (0c1h),a
	xor a
	out (0c1h),a
	ld a,004h
	out (0c0h),a
	ld a,018h
	out (0c1h),a
	ret
menu_hw_flags:
	db 0
menu_scc_count:
	db 0
menu_saved_a8:
	db 0
menu_music_save8:
	db 0
menu_probe_primary_id:
	db 0
menu_probe_secondary_id:
	db 0
menu_sig_internal_fmpac:
	db "APRLOPLL"
menu_sig_fmpac:
	db "PAC2OPLL"
menu_sig_musicbox:
	db "MUSICBOX"
menu_hw_no_scc:
	db "SCC -",0
menu_hw_scc:
	db "SCC",0
menu_hw_sccplus:
	db "SCC+",0
menu_hw_two_scc:
	db "2 SCC",0
menu_hw_fmpac:
	db "FMPAC ",0
menu_hw_moonsound:
	db "MOONSOUND",0
menu_hw_music32:
	db "MUSIC MODULE 32K",0
menu_hw_music256:
	db "MUSIC MODULE 256K",0
menu_overlay_end:
	ds 14,0
