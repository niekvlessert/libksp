; Resident package-browser backend and menu overlay bridge.

menu_overlay_entry:
	jp menu_overlay_boot
menu_ovl_refresh:
	jp menu_overlay_refresh
menu_ovl_get_line:
	jp menu_overlay_get_line
	jp menu_overlay_draw_frame
menu_ovl_draw_header:
	jp menu_overlay_draw_header
menu_overlay_boot:
	ld a,0feh
	ld (ui_menu_overlay_segment),a
menu_overlay_backup_begin:
	call vdp_irq_begin
	ld hl,MENU_OVERLAY_VRAM_IMAGE
	xor a
	call vram_set_write_address
	ld hl,CPU_PAGE1_BASE
	ld bc,MENU_OVERLAY_VRAM_IMAGE_BYTES
menu_overlay_backup_loop:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,menu_overlay_backup_loop
	ld hl,HVAR_OVERLAY_VRAM
	xor a
	call vram_set_write_address
	ld hl,hvar_overlay_image
	ld bc,HVAR_OVERLAY_MAX
menu_hvar_backup_loop:
	ld a,(hl)
	out (PORT_VDP_DATA),a
	inc hl
	dec bc
	ld a,b
	or c
	jp nz,menu_hvar_backup_loop
	jp vdp_irq_end
menu_overlay_refresh:
	call menu_detect_hardware
	call menu_titles_clear
	xor a
	ld (menu_index_dirty),a
	call menu_index_load
	jp nc,menu_index_loaded
	ld a,001h
	ld (menu_index_dirty),a
menu_index_loaded:
	xor a
	ld (menu_index_cursor),a
menu_index_fill_loop:
	ld a,(menu_index_cursor)
	ld b,a
	ld a,(ui_file_count)
	cp b
	jp z,menu_index_fill_done
	jp c,menu_index_fill_done
	ld a,b
	call menu_title_present
	jp nz,menu_index_fill_next
	ld a,b
	call menu_extract_title
	ld a,(menu_index_cursor)
	call menu_title_write
	ld a,001h
	ld (menu_index_dirty),a
menu_index_fill_next:
	ld a,(menu_index_cursor)
	inc a
	ld (menu_index_cursor),a
	jp menu_index_fill_loop
menu_index_fill_done:
	call menu_index_rebuild
	call menu_set_index_filename
	jp menu_index_open_records
menu_overlay_get_line:
	push bc
	push af
	call ui_line_fill_spaces
	pop af
	cp 0ffh
	jp z,menu_get_line_done
	call menu_title_read
	ld hl,ui_string_buffer
	ld b,03fh
	xor a
menu_get_length:
	cp b
	jp z,menu_get_length_done
	ld e,a
	ld d,000h
	push hl
	add hl,de
	ld a,(hl)
	pop hl
	or a
	jp z,menu_get_length_value
	ld a,e
	inc a
	jp menu_get_length
menu_get_length_value:
	ld a,e
menu_get_length_done:
	cp 03dh
	jp c,menu_get_length_ok
	ld a,03ch
menu_get_length_ok:
	ld c,a
	ld a,03ch
	sub c
	srl a
	add a,002h
	ld e,a
	ld d,000h
	ld hl,ui_line_buffer
	add hl,de
	ex de,hl
	ld hl,ui_string_buffer
	ld b,c
menu_get_copy:
	ld a,b
	or a
	jp z,menu_get_line_done
	ld a,(hl)
	or a
	jp z,menu_get_line_done
	ld (de),a
	inc hl
	inc de
	djnz menu_get_copy
menu_get_line_done:
	ld hl,ui_line_buffer
	ld de,ui_string_buffer
	ld bc,00040h
	ldir
	xor a
	ld (ui_string_buffer+64),a
	ld hl,ui_string_buffer
	pop bc
	ret
	ld (menu_index_cursor),a
	ld (file_fcb+33),a
	xor a
	ld (file_fcb+34),a
	ld (file_fcb+35),a
	ld (file_fcb+36),a
	ld de,hpl_header
	ld c,01ah
	call BDOS
	ld hl,00001h
	ld de,file_fcb
	ld c,027h
	call BDOS
	or a
	jp nz,menu_index_direct_fallback
	ld a,(hpl_page_count)
	cp 07ch
	jp nz,menu_index_direct_fallback
	ld hl,hpl_page_count_hi
	ld de,ui_string_buffer
	ld b,03fh
menu_index_direct_copy:
	ld a,(hl)
	cp 020h
	jp c,menu_index_direct_end
	ld (de),a
	inc hl
	inc de
	djnz menu_index_direct_copy
menu_index_direct_end:
	xor a
	ld (de),a
	ld hl,ui_string_buffer+62
	ld b,03fh
menu_index_direct_trim:
	ld a,(hl)
	cp 020h
	jp nz,menu_index_direct_ok
	xor a
	ld (hl),a
	dec hl
	djnz menu_index_direct_trim
menu_index_direct_ok:
	or a
	ret
menu_index_direct_fallback:
	ld a,(menu_index_cursor)
	call menu_title_from_filename
	or a
	ret
menu_overlay_draw_frame:
	ld a,002h
	ld b,007h
	ld hl,menu_frame_outer
	call ui_text_line
	ld a,003h
	ld b,005h
	ld hl,menu_frame_inner
	call ui_text_line
	ld a,016h
	ld b,007h
	ld hl,menu_frame_outer
	jp ui_text_line
menu_titles_clear:
	ld hl,recon_overlay_image
	ld de,recon_overlay_image+1
	ld bc,MENU_TITLE_CLEAR_TAIL_BYTES
	xor a
	ld (hl),a
	ldir
	ret
menu_title_address:
	ld e,a
	ld d,000h
	ld h,d
	ld l,e
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	add hl,hl
	ld de,recon_overlay_image
	add hl,de
	ret
menu_title_present:
	call menu_title_address
	ld a,(hl)
	or a
	ret
menu_title_read:
	call menu_title_address
	ld de,ui_string_buffer
	ld bc,00040h
	ldir
	xor a
	ld (ui_string_buffer+63),a
	ret
menu_title_write:
	push af
	call menu_title_address
	ex de,hl
	ld hl,ui_string_buffer
	ld bc,00040h
	ldir
	pop af
	ret
menu_set_index_filename:
	ld hl,menu_index_filename
	ld de,filename
	ld b,00ah
menu_set_index_filename_loop:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	djnz menu_set_index_filename_loop
	ret
menu_index_open_records:
	call fcb_open_current
	ret c
	ld hl,00050h
	ld (file_fcb+14),hl
	xor a
	ld (file_fcb+33),a
	ld (file_fcb+34),a
	ld (file_fcb+35),a
	ld (file_fcb+36),a
	or a
	ret
menu_index_load:
	call menu_set_index_filename
	call menu_index_open_records
	ret c
menu_index_read_loop:
	ld de,hpl_header
	ld c,01ah
	call BDOS
	ld hl,00001h
	ld de,file_fcb
	ld c,027h
	call BDOS
	or a
	jp nz,menu_index_read_done
	ld a,(hpl_page_count)
	cp 07ch
	call z,menu_index_apply_record
	jp menu_index_read_loop
menu_index_read_done:
	call fcb_close_current
	or a
	ret
menu_index_apply_record:
	xor a
	ld (menu_index_cursor),a
menu_index_match_loop:
	ld a,(menu_index_cursor)
	ld b,a
	ld a,(ui_file_count)
	cp b
	ret z
	ret c
	ld a,b
	call menu_index_filename_matches_record
	jp z,menu_index_record_found
	ld a,(menu_index_cursor)
	inc a
	ld (menu_index_cursor),a
	jp menu_index_match_loop
menu_index_record_found:
	ld hl,hpl_page_count_hi
	ld de,ui_string_buffer
	ld b,03fh
menu_index_title_copy:
	ld a,(hl)
	cp 020h
	jp c,menu_index_title_end
	ld (de),a
	inc hl
	inc de
	djnz menu_index_title_copy
menu_index_title_end:
	xor a
	ld (de),a
	ld hl,ui_string_buffer+62
	ld b,03fh
menu_index_title_trim:
	ld a,(hl)
	cp 020h
	jp nz,menu_index_title_store
	xor a
	ld (hl),a
	dec hl
	djnz menu_index_title_trim
menu_index_title_store:
	ld a,(menu_index_cursor)
	jp menu_title_write
menu_index_filename_matches_record:
	call ui_filename_slot_address
	ld de,hpl_header
	ld b,00ch
	xor a
	ld (menu_filename_ended),a
menu_filename_compare_loop:
	ld a,(menu_filename_ended)
	or a
	jp nz,menu_filename_expected_space
	ld a,(hl)
	or a
	jp nz,menu_filename_expected_char
	ld a,001h
	ld (menu_filename_ended),a
menu_filename_expected_space:
	ld a,020h
	jp menu_filename_compare
menu_filename_expected_char:
	inc hl
menu_filename_compare:
	ld c,a
	ld a,(de)
	cp c
	ret nz
	inc de
	djnz menu_filename_compare_loop
	xor a
	ret
menu_index_rebuild:
	call menu_set_index_filename
	call fcb_prepare_filename
	ret c
	ld de,file_fcb
	ld c,013h
	call BDOS
	call fcb_prepare_filename
	ret c
	ld de,file_fcb
	ld c,016h
	call BDOS
	or a
	ret nz
	ld a,001h
	ld (file_open),a
	ld hl,00050h
	ld (file_fcb+14),hl
	xor a
	ld (file_fcb+33),a
	ld (file_fcb+34),a
	ld (file_fcb+35),a
	ld (file_fcb+36),a
	ld (menu_index_cursor),a
menu_index_write_loop:
	ld a,(menu_index_cursor)
	ld b,a
	ld a,(ui_file_count)
	cp b
	jp z,menu_index_write_done
	jp c,menu_index_write_done
	ld hl,hpl_header
	ld b,050h
	ld a,020h
menu_index_record_clear:
	ld (hl),a
	inc hl
	djnz menu_index_record_clear
	ld a,07ch
	ld (hpl_page_count),a
	ld a,00dh
	ld (hpl_cold_raw_size_hi),a
	ld a,00ah
	ld (hpl_cold_raw_size_top),a
	ld a,(menu_index_cursor)
	call ui_filename_slot_address
	ld de,hpl_header
	ld b,00ch
menu_index_filename_copy:
	ld a,(hl)
	or a
	jp z,menu_index_filename_done
	ld (de),a
	inc hl
	inc de
	djnz menu_index_filename_copy
menu_index_filename_done:
	ld a,(menu_index_cursor)
	call menu_title_read
	ld hl,ui_string_buffer
	ld de,hpl_page_count_hi
	ld b,041h
menu_index_record_title:
	ld a,(hl)
	or a
	jp z,menu_index_record_ready
	ld (de),a
	inc hl
	inc de
	djnz menu_index_record_title
menu_index_record_ready:
	ld de,hpl_header
	ld c,01ah
	call BDOS
	ld hl,00001h
	ld de,file_fcb
	ld c,026h
	call BDOS
	or a
	jp nz,menu_index_write_done
	ld a,(menu_index_cursor)
	inc a
	ld (menu_index_cursor),a
	jp menu_index_write_loop
menu_index_write_done:
	jp fcb_close_current
menu_extract_title:
	push af
	call menu_copy_filename
	call fcb_open_current
	jp c,menu_extract_fallback_pop
	xor a
	ld hl,ENGINE_DIRECT_CALL_PATCH
	ld de,ksp_header
	ld bc,00050h
	call read_at
	jp nz,menu_extract_close_fallback
	ld hl,ksp_header
	ld a,(hl)
	cp 04bh
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 053h
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 050h
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 031h
	jp nz,menu_extract_close_fallback
	ld hl,(ksp_meta_resource_index)
	ld a,h
	cp 0ffh
	jp nz,menu_extract_meta_index
	ld a,l
	cp 0ffh
	jp z,menu_extract_close_fallback
menu_extract_meta_index:
	ld de,00020h
	call mul16x16_24
	ld c,a
	ld de,(ksp_resource_table_offset_lo)
	add hl,de
	ld a,(ksp_resource_table_offset_hi)
	adc a,c
	ld de,resource_entry
	ld bc,00020h
	call read_at
	jp nz,menu_extract_close_fallback
	ld hl,resource_entry
	ld a,(hl)
	cp 04dh
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 045h
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 054h
	jp nz,menu_extract_close_fallback
	inc hl
	ld a,(hl)
	cp 041h
	jp nz,menu_extract_close_fallback
	ld a,(resource_compression)
	or a
	jp nz,menu_extract_close_fallback
	ld a,(resource_payload_offset_top)
	or a
	jp nz,menu_extract_close_fallback
	ld a,(resource_packed_size_hi)
	or a
	jp nz,menu_extract_close_fallback
	ld a,(resource_packed_size_top)
	or a
	jp nz,menu_extract_close_fallback
	ld hl,(resource_packed_size_lo)
	ld de,IO_BUFFER_SIZE+1
	or a
	sbc hl,de
	jp nc,menu_extract_close_fallback
	ld hl,(resource_payload_offset_lo)
	ld a,(resource_payload_offset_hi)
	ld de,io_buffer
	ld bc,(resource_packed_size_lo)
	call read_at
	jp nz,menu_extract_close_fallback
	ld hl,io_buffer
	ld bc,(resource_packed_size_lo)
	ld de,menu_meta_game

	ld a,005h
	call menu_find_meta_key
	jp nc,menu_extract_copy_value
	ld hl,io_buffer
	ld bc,(resource_packed_size_lo)
	ld de,menu_meta_title
	ld a,006h
	call menu_find_meta_key
	jp c,menu_extract_close_fallback
menu_extract_copy_value:
	call menu_copy_meta_value
	ld a,(ui_string_buffer)
	or a
	jp z,menu_extract_close_fallback
	call fcb_close_current
	pop af
	ret
menu_extract_close_fallback:
	call fcb_close_current
menu_extract_fallback_pop:
	pop af
	jp menu_title_from_filename
menu_copy_filename:
	call ui_filename_slot_address
	ld de,filename
	ld b,00dh
menu_copy_filename_loop:
	ld a,(hl)
	ld (de),a
	inc hl
	inc de
	or a
	ret z
	djnz menu_copy_filename_loop
	xor a
	ld (de),a
	ret
menu_title_from_filename:
	call ui_filename_slot_address
	ld de,ui_string_buffer
	ld b,03fh
menu_title_filename_loop:
	ld a,(hl)
	or a
	jp z,menu_title_filename_done
	cp 02eh
	jp z,menu_title_filename_done
	cp 05fh
	jp nz,menu_title_filename_store
	ld a,020h
menu_title_filename_store:
	ld (de),a
	inc hl
	inc de
	djnz menu_title_filename_loop
menu_title_filename_done:
	xor a
	ld (de),a
	ret
menu_find_meta_key:
	ld (menu_key_len),a
menu_find_line:
	ld a,b
	or c
	jp z,menu_find_key_bad
	push hl
	push bc
	push de
	ld a,(menu_key_len)
	ld b,a
menu_find_key_compare:
	ld a,(de)
	cp (hl)
	jp nz,menu_find_key_miss
	inc de
	inc hl
	djnz menu_find_key_compare
	pop de
	pop bc
	pop de
	ld a,(menu_key_len)
	ld e,a
	ld d,000h
	push hl
	ld h,b
	ld l,c
	or a
	sbc hl,de
	ld b,h
	ld c,l
	pop hl
	or a
	ret
menu_find_key_miss:
	pop de
	pop bc
	pop hl
menu_find_skip_line:
	ld a,b
	or c
	jp z,menu_find_key_bad
	ld a,(hl)
	inc hl
	dec bc
	cp 00ah
	jp nz,menu_find_skip_line
	jp menu_find_line
menu_find_key_bad:
	scf
	ret
menu_copy_meta_value:
	ld de,ui_string_buffer
	ld b,03fh
menu_copy_meta_loop:
	ld a,b
	or a
	jp z,menu_copy_meta_done
	ld a,(hl)
	cp 020h
	jp c,menu_copy_meta_done
	cp 080h
	jp c,menu_copy_meta_store
	ld a,03fh
menu_copy_meta_store:
	ld (de),a
	inc hl
	inc de
	dec b
	jp menu_copy_meta_loop
menu_copy_meta_done:
	xor a
	ld (de),a
	ret
menu_index_cursor:
	db 0
menu_index_dirty:
	db 0
menu_filename_ended:
	db 0
menu_key_len:
	db 0
index_filename:
menu_index_filename:
	db "INDEX.TXT",0
menu_meta_game:
	db "game=",0
menu_meta_title:
	db "title=",0
menu_frame_outer:
	db "+==============================================================+",0
menu_frame_inner:
	db "[[------------------------------------------------------------]]",0

; Detect the KSPOS low-memory ABI ("KPOS" signature/version) and publish the
; runtime flags used by mapper-safe engine and menu transitions.
