; KSP1PLAY.COM - clean MSX-DOS2 KSP 1.0 player
; Generated with tools/z80asm.py. No external assembler required.
;
; Current executable profile:
;   - KSP1 header/tables, 16-bit tracks
;   - resident program, stack, tables and buffers entirely in page 0
;   - one 16 KiB engine loaded at 4000h
;   - KSP_PAGE_SPARSE_OVERLAY, COMPLETE and HYBRID_POOL
;   - HPOL / HPL1 when present
;   - hot pool in up to three mapper segments
;   - warm pool in VRAM at 08000h, with a 32 KiB RAM history window
;   - cold slabs decoded on demand into page 2
;   - PSG + SCC playback, primary SCC slot 0..3
;
; Usage: KSP1PLAY file.ksp [track] [scc-slot]

org 0x0100

BDOS            equ 0x0005
EXTBIO          equ 0xFFCA
DOS_TERM0       equ 0x00
DOS_CONST       equ 0x0B
DOS_OPEN        equ 0x43
DOS_CLOSE       equ 0x45
DOS_READ        equ 0x48
DOS_WRITE       equ 0x49
DOS_SEEK        equ 0x4A
DOS_TERM        equ 0x62

PORT_PPI_A      equ 0xA8
PORT_KEY_IN     equ 0xA9
PORT_KEY_ROW    equ 0xAA
PORT_VDP_DATA   equ 0x98
PORT_VDP_CTRL   equ 0x99

; Page 0 is the only permanently owned CPU address space.  DOS2 keeps page 3.
; The binary must end before KSP_HEADER; build.py enforces this memory map.
DYNAMIC_GATEWAY equ 0x17E0            ; reserved page-0 ABI entry
KSP_HEADER      equ 0x1800            ; 80 bytes
ENGINE_ENTRY    equ 0x1850            ; 64 bytes
TRACK_ENTRY     equ 0x1890            ; 32 bytes
PAGE_ENTRY      equ 0x18B0            ; 24 bytes
RESOURCE_ENTRY  equ 0x18D0            ; 32 bytes / cold descriptor scratch
HPL_HEADER      equ 0x1900            ; 96 bytes
TITLE_BUFFER    equ 0x1980            ; 160 bytes used
IO_BUFFER       equ 0x1B00
IO_BUFFER_SIZE  equ 512
POS_BUFFER      equ 0x1D00
POS_BUFFER_MAX  equ 0x0200
MAP_BUFFER      equ 0x1F00
MAP_BUFFER_MAX  equ 0x1800            ; ends at 3700h
STACK_BOTTOM    equ 0x3700
STACK_TOP       equ 0x3FF0
WARM_VRAM_BASE  equ 0x08000

start:
    ; A COM owns page-0 TPA RAM from 0100h upward.  Keep DOS2 page 3 untouched.
    ; The stack grows down from 3FF0h and has a 2288-byte guard above MAP_BUFFER.
    ld sp,STACK_TOP
    call parse_command_line
    jp c,usage_error
    ld de,msg_banner
    ld bc,msg_banner_end-msg_banner
    call write_stdout

    ld de,filename
    xor a
    ld c,DOS_OPEN
    call BDOS
    jp nz,file_error
    ld a,b
    ld (file_handle),a

    call get_mapper_api
    jp c,mapper_error
    call capture_original_pages

    xor a
    ld hl,0
    ld de,KSP_HEADER
    ld bc,80
    call read_at
    jp nz,file_error
    call validate_header
    jp c,format_error
    call load_engine_zero
    jp c,format_error
    call validate_engine_profile
    jp c,profile_error
    xor a
    ld (hybrid_ready),a
    call find_hpol_resource
    jr c,start_no_hpol
    call load_hpl_header
    jp c,format_error
    call allocate_hot_segments
    jp c,memory_error
    ld a,4
    ld (decode_stage),a
    call preload_hybrid_pool
    jp c,decode_error
    ld a,1
    ld (hybrid_ready),a
start_no_hpol:

    ld hl,(selected_track)
    call select_track
    jp c,track_error
    call show_current_title
    call install_current_track
    jp c,decode_error

main_loop:
    ei
    halt
    di
    call call_play
    call read_controls
    cp 1
    jp z,clean_exit
    cp 2
    jr nz,main_loop
    call next_track
    jp c,track_error
    jr main_loop

usage_error:
    ld de,msg_usage
    ld bc,msg_usage_end-msg_usage
    call write_stdout
    jp terminate_error_no_file
format_error:
    ld de,msg_format
    ld bc,msg_format_end-msg_format
    jr fatal_with_file
profile_error:
    ld de,msg_profile
    ld bc,msg_profile_end-msg_profile
    jr fatal_with_file
mapper_error:
    ld de,msg_mapper
    ld bc,msg_mapper_end-msg_mapper
    jr fatal_with_file
memory_error:
    ld de,msg_memory
    ld bc,msg_memory_end-msg_memory
    jr fatal_with_file
file_error:
    ld de,msg_file
    ld bc,msg_file_end-msg_file
    jr fatal_with_file
track_error:
    ld de,msg_track
    ld bc,msg_track_end-msg_track
    jr fatal_with_file
decode_error:
    ld a,(decode_stage)
    cp 1
    jr z,decode_template_error
    cp 2
    jr z,decode_sparse_error
    cp 3
    jr z,decode_complete_error
    cp 4
    jr z,decode_hybrid_error
    ld de,msg_decode
    ld bc,msg_decode_end-msg_decode
    jr fatal_with_file
decode_template_error:
    ld de,msg_decode_template
    ld bc,msg_decode_template_end-msg_decode_template
    jr fatal_with_file
decode_sparse_error:
    ld de,msg_decode_sparse
    ld bc,msg_decode_sparse_end-msg_decode_sparse
    jr fatal_with_file
decode_complete_error:
    ld de,msg_decode_complete
    ld bc,msg_decode_complete_end-msg_decode_complete
    jr fatal_with_file
decode_hybrid_error:
    ld de,msg_decode_hybrid
    ld bc,msg_decode_hybrid_end-msg_decode_hybrid
fatal_with_file:
    call write_stdout
    call cleanup
terminate_error_no_file:
    ld b,1
    ld c,DOS_TERM
    call BDOS
    ret

clean_exit:
    call cleanup
    ld b,0
    ld c,DOS_TERM
    call BDOS
    ret

; ---------------------------------------------------------------------------
; Command line
; ---------------------------------------------------------------------------
parse_command_line:
    xor a
    ld (selected_track),a
    ld (selected_track+1),a
    ld a,2
    ld (scc_slot),a
    ld hl,0x0081
    ld a,(0x0080)
    ld (cmd_remaining),a

parse_skip_spaces:
    ld a,(cmd_remaining)
    or a
    jr z,parse_bad
    ld a,(hl)
    cp ' '
    jr nz,parse_filename
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_skip_spaces

parse_bad:
    scf
    ret

parse_filename:
    ld de,filename
    ld c,0
parse_filename_loop:
    ld a,(cmd_remaining)
    or a
    jr z,parse_filename_done
    ld a,(hl)
    cp ' '
    jr z,parse_filename_done
    cp 9
    jr z,parse_filename_done
    ld (de),a
    inc de
    inc hl
    inc c
    ld a,c
    cp 126
    jr nc,parse_bad
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_filename_loop
parse_filename_done:
    xor a
    ld (de),a

parse_track_spaces:
    ld a,(cmd_remaining)
    or a
    jr z,parse_good
    ld a,(hl)
    cp ' '
    jr nz,parse_track_start
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_track_spaces

parse_track_start:
    ld de,0
parse_track_loop:
    ld a,(cmd_remaining)
    or a
    jr z,parse_track_done
    ld a,(hl)
    cp ' '
    jr z,parse_track_done
    cp 9
    jr z,parse_track_done
    cp '0'
    jr c,parse_bad
    cp '9'+1
    jr nc,parse_bad
    sub '0'
    ld c,a
    ; DE = DE * 10 + digit, with overflow detection.
    push hl
    ld h,d
    ld l,e
    add hl,hl
    jr c,parse_overflow
    push hl
    add hl,hl
    jr c,parse_overflow_pop
    add hl,hl
    jr c,parse_overflow_pop
    pop de
    add hl,de
    jr c,parse_overflow
    ld a,l
    add a,c
    ld l,a
    jr nc,parse_track_store
    inc h
    jr z,parse_overflow
parse_track_store:
    ex de,hl
    pop hl
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_track_loop
parse_overflow_pop:
    pop de
parse_overflow:
    pop hl
    jr parse_bad

parse_track_done:
    ld (selected_track),de

parse_slot_spaces:
    ld a,(cmd_remaining)
    or a
    jr z,parse_good
    ld a,(hl)
    cp ' '
    jr nz,parse_slot_start
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_slot_spaces

parse_slot_start:
    ld a,(hl)
    cp '0'
    jr c,parse_bad
    cp '4'
    jr nc,parse_bad
    sub '0'
    ld (scc_slot),a
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    ; Only trailing spaces are permitted.
parse_trailing:
    ld a,(cmd_remaining)
    or a
    jr z,parse_good
    ld a,(hl)
    cp ' '
    jr nz,parse_bad
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_trailing

parse_good:
    or a
    ret

; ---------------------------------------------------------------------------
; DOS and mapper helpers
; ---------------------------------------------------------------------------
write_stdout:
    ; DE buffer, BC count
    ld h,b
    ld l,c
    ld b,1
    ld c,DOS_WRITE
    call BDOS
    ret

read_at:
    ; A:HL absolute 24-bit offset, DE destination, BC count
    push bc
    push de
    ld (tmp_offset_hi),a
    ld (tmp_offset_lo),hl
    ld a,(file_handle)
    ld b,a
    xor a
    ld d,0
    ld a,(tmp_offset_hi)
    ld e,a
    ld hl,(tmp_offset_lo)
    ld c,DOS_SEEK
    call BDOS
    pop de
    pop hl
    ret nz
    ld a,(file_handle)
    ld b,a
    ld c,DOS_READ
    call BDOS
    ret

get_mapper_api:
    xor a
    ld d,4
    ld e,2
    call EXTBIO
    or a
    jr z,get_mapper_fail
    ld (mapper_base),hl
    ld a,c
    ld (mapper_free_count),a
    ld de,0x0000
    add hl,de
    ld (mapper_all),hl
    ld hl,(mapper_base)
    ld de,0x0003
    add hl,de
    ld (mapper_free),hl
    ld hl,(mapper_base)
    ld de,0x001E
    add hl,de
    ld (mapper_put_p1),hl
    ld hl,(mapper_base)
    ld de,0x0024
    add hl,de
    ld (mapper_put_p2),hl
    ld hl,(mapper_base)
    ld de,0x0021
    add hl,de
    ld (mapper_get_p1),hl
    ld hl,(mapper_base)
    ld de,0x0027
    add hl,de
    ld (mapper_get_p2),hl
    or a
    ret
get_mapper_fail:
    scf
    ret

call_hl:
    jp (hl)

capture_original_pages:
    ld hl,(mapper_get_p1)
    call call_hl
    ld (original_p1),a
    ld (mapped_p1),a
    ld hl,(mapper_get_p2)
    call call_hl
    ld (original_p2),a
    ld (mapped_p2),a
    in a,(PORT_PPI_A)
    ld (original_a8),a
    ld a,1
    ld (mapper_ready),a
    ret

map_p1:
    ld (mapped_p1),a
    ld hl,(mapper_put_p1)
    call call_hl
    ret
map_p2:
    ld (mapped_p2),a
    ld hl,(mapper_put_p2)
    call call_hl
    ret
restore_process_pages:
    ld a,(original_a8)
    out (PORT_PPI_A),a
    ld a,(original_p1)
    call map_p1
    ld a,(original_p2)
    call map_p2
    ret

map_scc_page2:
    in a,(PORT_PPI_A)
    and 0xCF
    ld b,a
    ld a,(scc_slot)
    and 3
    rlca
    rlca
    rlca
    rlca
    or b
    out (PORT_PPI_A),a
    ret

allocate_hot_segments:
    ld hl,(hpl_hot_raw)
    ld a,(hpl_hot_raw+2)
    or a
    jr nz,alloc_hot_bad
    ld de,0x3FFF
    add hl,de
    ld a,h
    and 0xC0
    rlca
    rlca
    cp 4
    jr nc,alloc_hot_bad
    ld (hot_needed_count),a
    xor a
    ld (hot_segment_count),a
    ld a,(hot_needed_count)
    ld b,a
    ld hl,hot_segments
alloc_hot_loop:
    ld a,b
    or a
    jr z,alloc_hot_done
    push hl
    push bc
    xor a
    ld b,0
    ld hl,(mapper_all)
    call call_hl
    pop bc
    pop hl
    jr c,alloc_hot_bad
    ld (hl),a
    inc hl
    ld a,(hot_segment_count)
    inc a
    ld (hot_segment_count),a
    djnz alloc_hot_loop
alloc_hot_done:
    or a
    ret
alloc_hot_bad:
    scf
    ret

free_hot_segments:
    ld a,(hot_segment_count)
    ld b,a
    ld hl,hot_segments
free_hot_loop:
    ld a,b
    or a
    ret z
    ld a,(hl)
    inc hl
    push hl
    push bc
    ld b,0
    ld hl,(mapper_free)
    call call_hl
    pop bc
    pop hl
    djnz free_hot_loop
    ret

cleanup:
    di
    ld a,(mapper_ready)
    or a
    jr z,cleanup_close_file
    call stop_engine
    ld a,(original_a8)
    out (PORT_PPI_A),a
    call restore_process_pages
    call free_hot_segments
    xor a
    ld (hot_segment_count),a
    ld (mapper_ready),a
cleanup_close_file:
    ld a,(file_handle)
    or a
    jr z,cleanup_done
    ld b,a
    ld c,DOS_CLOSE
    call BDOS
    xor a
    ld (file_handle),a
cleanup_done:
    ei
    ret

; ---------------------------------------------------------------------------
; KSP parsing
; ---------------------------------------------------------------------------
validate_header:
    ld hl,KSP_HEADER
    ld a,(hl)
    cp 'K'
    jr nz,header_bad
    inc hl
    ld a,(hl)
    cp 'S'
    jr nz,header_bad
    inc hl
    ld a,(hl)
    cp 'P'
    jr nz,header_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,header_bad
    ld hl,(KSP_HEADER+4)
    ld de,80
    or a
    sbc hl,de
    jr nz,header_bad
    ld hl,(KSP_HEADER+6)
    ld a,h
    or l
    jr nz,header_bad
    ld hl,(KSP_HEADER+0x14)
    ld a,h
    or l
    jr z,header_bad
    ld hl,(KSP_HEADER+0x16)
    ld de,64
    or a
    sbc hl,de
    jr c,header_bad
    ld hl,(KSP_HEADER+0x1E)
    ld de,24
    or a
    sbc hl,de
    jr c,header_bad
    ld hl,(KSP_HEADER+0x26)
    ld de,32
    or a
    sbc hl,de
    jr c,header_bad
    ld hl,(KSP_HEADER+0x2E)
    ld de,32
    or a
    sbc hl,de
    jr c,header_bad
    or a
    ret
header_bad:
    scf
    ret

load_engine_zero:
    ld hl,(KSP_HEADER+0x10)
    ld a,(KSP_HEADER+0x12)
    ld de,ENGINE_ENTRY
    ld bc,64
    call read_at
    jr nz,load_engine_bad
    or a
    ret
load_engine_bad:
    scf
    ret

validate_engine_profile:
    ; Engine ABI 1, no dynamic/banked/MWK-required flags in this first COM.
    ld hl,(ENGINE_ENTRY)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+2)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ; Hardware profile: PSG and/or SCC only.
    ld a,(ENGINE_ENTRY+4)
    and 0xFC
    jr nz,engine_profile_bad
    ld a,(ENGINE_ENTRY+5)
    or a
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+6)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+8)
    ld de,1
    or a
    sbc hl,de
    jr nz,engine_profile_bad
    ; Tick frequency is driven by one VBlank call per PLAY tick.
    ld hl,(ENGINE_ENTRY+10)
    ld de,50
    or a
    sbc hl,de
    jr z,engine_tick_ok
    add hl,de
    ld de,60
    or a
    sbc hl,de
    jr nz,engine_profile_bad
engine_tick_ok:
    ld hl,(ENGINE_ENTRY+12)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+14)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+16)
    ld a,h
    cp 0x40
    jr c,engine_profile_bad
    cp 0x80
    jr nc,engine_profile_bad
    ld hl,(ENGINE_ENTRY+18)
    ld a,h
    cp 0x40
    jr c,engine_profile_bad
    cp 0x80
    jr nc,engine_profile_bad
    ; No banks in this hardware profile.
    ld a,(ENGINE_ENTRY+34)
    or a
    jr nz,engine_profile_bad
    ld a,(ENGINE_ENTRY+35)
    or a
    jr nz,engine_profile_bad
    ; Template is either raw or one forward ZX0 stream and must produce 16 KiB.
    ld a,(ENGINE_ENTRY+32)
    cp 2
    jr nc,engine_profile_bad
    ld (template_compression),a
    ; 24-bit MSX profile: top byte of payload offset must be zero.
    ld a,(ENGINE_ENTRY+39)
    or a
    jr nz,engine_profile_bad
    ; Packed template size must fit the 16-bit streaming counter.
    ld hl,(ENGINE_ENTRY+42)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+44)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+46)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ld a,(template_compression)
    or a
    jr nz,engine_template_ok
    ld hl,(ENGINE_ENTRY+40)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,engine_profile_bad
engine_template_ok:
    or a
    ret
engine_profile_bad:
    scf
    ret

find_hpol_resource:
    ld hl,(KSP_HEADER+0x2C)
    ld (resource_count),hl
    ld hl,(KSP_HEADER+0x28)
    ld a,(KSP_HEADER+0x2A)
    ld (resource_cursor_lo),hl
    ld (resource_cursor_hi),a
    xor a
    ld (resource_index),a
    ld (resource_index+1),a
find_hpol_loop:
    ld hl,(resource_count)
    ld a,h
    or l
    jr z,find_hpol_bad
    ld hl,(resource_cursor_lo)
    ld a,(resource_cursor_hi)
    ld de,RESOURCE_ENTRY
    ld bc,32
    call read_at
    jr nz,find_hpol_bad
    ld hl,RESOURCE_ENTRY
    ld a,(hl)
    cp 'H'
    jr nz,find_hpol_next
    inc hl
    ld a,(hl)
    cp 'P'
    jr nz,find_hpol_next
    inc hl
    ld a,(hl)
    cp 'O'
    jr nz,find_hpol_next
    inc hl
    ld a,(hl)
    cp 'L'
    jr nz,find_hpol_next
    ld hl,(RESOURCE_ENTRY+8)
    ld a,(RESOURCE_ENTRY+10)
    ld (hpol_offset_lo),hl
    ld (hpol_offset_hi),a
    ld hl,(RESOURCE_ENTRY+12)
    ld a,(RESOURCE_ENTRY+14)
    ld (hpol_size_lo),hl
    ld (hpol_size_hi),a
    or a
    ret
find_hpol_next:
    ld hl,(resource_cursor_lo)
    ld de,32
    add hl,de
    ld (resource_cursor_lo),hl
    jr nc,find_hpol_no_carry
    ld a,(resource_cursor_hi)
    inc a
    ld (resource_cursor_hi),a
find_hpol_no_carry:
    ld hl,(resource_count)
    dec hl
    ld (resource_count),hl
    ld hl,(resource_index)
    inc hl
    ld (resource_index),hl
    jr find_hpol_loop
find_hpol_bad:
    scf
    ret

load_hpl_header:
    ld hl,(hpol_offset_lo)
    ld a,(hpol_offset_hi)
    ld de,HPL_HEADER
    ld bc,96
    call read_at
    jp nz,hpl_bad
    ld hl,HPL_HEADER
    ld a,(hl)
    cp 'H'
    jp nz,hpl_bad
    inc hl
    ld a,(hl)
    cp 'P'
    jp nz,hpl_bad
    inc hl
    ld a,(hl)
    cp 'L'
    jp nz,hpl_bad
    inc hl
    ld a,(hl)
    cp '1'
    jp nz,hpl_bad
    ld hl,(HPL_HEADER+4)
    ld de,96
    or a
    sbc hl,de
    jp nz,hpl_bad
    ld hl,(HPL_HEADER+6)
    ld de,1
    or a
    sbc hl,de
    jp nz,hpl_bad
    ld hl,(HPL_HEADER+8)
    ld (hpl_block_size),hl
    ld a,h
    or a
    jp nz,hpl_bad
    ld a,l
    cp 64
    jp c,hpl_bad
    ; only power-of-two blocks 64,128,256,512
    cp 64
    jr z,hpl_bs64
    cp 128
    jr z,hpl_bs128
    jr hpl_check_256
hpl_bs64:
    ld a,6
    jr hpl_shift_ready
hpl_bs128:
    ld a,7
    jr hpl_shift_ready
hpl_check_256:
    ld hl,(hpl_block_size)
    ld de,256
    or a
    sbc hl,de
    jr z,hpl_bs256
    ld hl,(hpl_block_size)
    ld de,512
    or a
    sbc hl,de
    jp nz,hpl_bad
    ld a,9
    jr hpl_shift_ready
hpl_bs256:
    ld a,8
hpl_shift_ready:
    ld (hpl_block_shift),a
    ld hl,(HPL_HEADER+10)
    ld (hpl_position_count),hl
    add hl,hl
    ld de,POS_BUFFER_MAX
    or a
    sbc hl,de
    jp nc,hpl_bad
    ld hl,(HPL_HEADER+12)
    ld de,(KSP_HEADER+0x1C)
    or a
    sbc hl,de
    jp nz,hpl_bad
    ld hl,(HPL_HEADER+14)
    ld (hpl_hot_count),hl
    ld hl,(HPL_HEADER+16)
    ld (hpl_warm_count),hl
    ld hl,(HPL_HEADER+18)
    ld (hpl_cold_count),hl
    ld hl,(HPL_HEADER+20)
    ld (hpl_slab_count),hl
    ld hl,(HPL_HEADER+22)
    ld a,h
    or l
    jp nz,hpl_bad
    ; copy all 24-bit offsets and sizes used later
    ld hl,(HPL_HEADER+24)
    ld a,(HPL_HEADER+26)
    ld (hpl_positions_off),hl
    ld (hpl_positions_off+2),a
    ld hl,(HPL_HEADER+28)
    ld a,(HPL_HEADER+30)
    ld (hpl_maps_off),hl
    ld (hpl_maps_off+2),a
    ld hl,(HPL_HEADER+32)
    ld a,(HPL_HEADER+34)
    ld (hpl_maps_packed),hl
    ld (hpl_maps_packed+2),a
    ld hl,(HPL_HEADER+36)
    ld a,(HPL_HEADER+38)
    ld (hpl_maps_raw),hl
    ld (hpl_maps_raw+2),a
    ld hl,(HPL_HEADER+40)
    ld a,(HPL_HEADER+42)
    ld (hpl_hot_off),hl
    ld (hpl_hot_off+2),a
    ld hl,(HPL_HEADER+44)
    ld a,(HPL_HEADER+46)
    ld (hpl_hot_packed),hl
    ld (hpl_hot_packed+2),a
    ld hl,(HPL_HEADER+48)
    ld a,(HPL_HEADER+50)
    ld (hpl_hot_raw),hl
    ld (hpl_hot_raw+2),a
    ld hl,(HPL_HEADER+52)
    ld a,(HPL_HEADER+54)
    ld (hpl_warm_off),hl
    ld (hpl_warm_off+2),a
    ld hl,(HPL_HEADER+56)
    ld a,(HPL_HEADER+58)
    ld (hpl_warm_packed),hl
    ld (hpl_warm_packed+2),a
    ld hl,(HPL_HEADER+60)
    ld a,(HPL_HEADER+62)
    ld (hpl_warm_raw),hl
    ld (hpl_warm_raw+2),a
    ld hl,(HPL_HEADER+64)
    ld a,(HPL_HEADER+66)
    ld (hpl_cold_table_off),hl
    ld (hpl_cold_table_off+2),a
    ; map raw must fit the fixed page-0 map buffer
    ld a,(hpl_maps_raw+2)
    or a
    jp nz,hpl_bad
    ld hl,(hpl_maps_raw)
    ld de,MAP_BUFFER_MAX+1
    or a
    sbc hl,de
    jp nc,hpl_bad
    ; This implementation streams each compressed object with a 16-bit size.
    ld a,(hpl_maps_packed+2)
    or a
    jp nz,hpl_bad
    ld a,(hpl_hot_packed+2)
    or a
    jp nz,hpl_bad
    ld a,(hpl_warm_packed+2)
    or a
    jp nz,hpl_bad

    ; Hot pool <= 48 KiB.
    ld a,(hpl_hot_raw+2)
    or a
    jp nz,hpl_bad
    ld hl,(hpl_hot_raw)
    ld de,0xC001
    or a
    sbc hl,de
    jp nc,hpl_bad
hpl_hot_ok:
    ; Warm pool <= 96 KiB (0x018000).
    ld a,(hpl_warm_raw+2)
    or a
    jr z,hpl_warm_ok
    cp 1
    jp nz,hpl_bad
    ld hl,(hpl_warm_raw)
    ld de,0x8001
    or a
    sbc hl,de
    jp nc,hpl_bad
hpl_warm_ok:
    or a
    ret
hpl_bad:
    scf
    ret

; ---------------------------------------------------------------------------
; Hybrid pool preload
; ---------------------------------------------------------------------------
preload_hybrid_pool:
    ; positions are stored uncompressed
    call make_abs_positions_offset
    ld de,POS_BUFFER
    ld hl,(hpl_position_count)
    add hl,hl
    ld b,h
    ld c,l
    ld hl,(abs_offset_lo)
    ld a,(abs_offset_hi)
    call read_at
    jr nz,preload_bad

    ; maps -> fixed page-0 RAM
    call make_abs_maps_offset
    ld hl,(abs_offset_lo)
    ld a,(abs_offset_hi)
    ld de,(hpl_maps_packed)
    ld b,d
    ld c,e
    call stream_begin
    jr c,preload_bad
    xor a
    ld (zx_mode),a
    ld hl,MAP_BUFFER
    ld (linear_base),hl
    ld hl,(hpl_maps_raw)
    ld a,(hpl_maps_raw+2)
    call zx_set_output_size
    call zx_decode
    jr c,preload_bad

    ; warm first: original page 1 + page 2 are the 32 KiB history ring
    call restore_process_pages
    call make_abs_warm_offset
    ld hl,(abs_offset_lo)
    ld a,(abs_offset_hi)
    ld de,(hpl_warm_packed)
    ld b,d
    ld c,e
    call stream_begin
    jr c,preload_bad
    ld a,1
    ld (zx_mode),a
    call vram_set_warm_base_write
    ld hl,(hpl_warm_raw)
    ld a,(hpl_warm_raw+2)
    call zx_set_output_size
    call zx_decode
    jr c,preload_bad

    ; hot pool into allocated mapper segments
    call make_abs_hot_offset
    ld hl,(abs_offset_lo)
    ld a,(abs_offset_hi)
    ld de,(hpl_hot_packed)
    ld b,d
    ld c,e
    call stream_begin
    jr c,preload_bad
    ld a,2
    ld (zx_mode),a
    ld a,0xFF
    ld (hot_write_mapped),a
    ld (hot_read_mapped),a
    ld hl,(hpl_hot_raw)
    ld a,(hpl_hot_raw+2)
    call zx_set_output_size
    call zx_decode
    jr c,preload_bad
    call restore_process_pages
    or a
    ret
preload_bad:
    call restore_process_pages
    scf
    ret

make_abs_positions_offset:
    ld hl,hpl_positions_off
    jr make_hpol_abs
make_abs_maps_offset:
    ld hl,hpl_maps_off
    jr make_hpol_abs
make_abs_hot_offset:
    ld hl,hpl_hot_off
    jr make_hpol_abs
make_abs_warm_offset:
    ld hl,hpl_warm_off
make_hpol_abs:
    ; HL points to 24-bit relative offset. Result in abs_offset.
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    ld hl,(hpol_offset_lo)
    add hl,de
    ld (abs_offset_lo),hl
    ld a,(hpol_offset_hi)
    adc a,c
    ld (abs_offset_hi),a
    ret

; ---------------------------------------------------------------------------
; Track lookup/materialization/playback
; ---------------------------------------------------------------------------
select_track:
    ; HL public track index
    ld de,(KSP_HEADER+0x24)
    or a
    sbc hl,de
    jr nc,select_track_bad
    add hl,de
    ld (selected_track),hl
    ; offset = track_table + track * entry_size
    ld de,(KSP_HEADER+0x26)
    call mul16x16_24
    ld c,a
    ld de,(KSP_HEADER+0x20)
    add hl,de
    ld a,(KSP_HEADER+0x22)
    adc a,c
    ld de,TRACK_ENTRY
    ld bc,32
    call read_at
    jr nz,select_track_bad
    ld hl,(TRACK_ENTRY)
    ld (current_page),hl
    ld hl,(TRACK_ENTRY+2)
    ld (current_song_id),hl
    ; page descriptor
    ld hl,(current_page)
    ld de,(KSP_HEADER+0x1E)
    call mul16x16_24
    ld c,a
    ld de,(KSP_HEADER+0x18)
    add hl,de
    ld a,(KSP_HEADER+0x1A)
    adc a,c
    ld de,PAGE_ENTRY
    ld bc,24
    call read_at
    jr nz,select_track_bad
    ; This COM currently supports one engine, owned page zero descriptors.
    ld hl,(PAGE_ENTRY)
    ld a,h
    or l
    jr nz,select_track_bad
    ld a,(PAGE_ENTRY+2)
    cp 0
    jr z,select_sparse_page
    cp 1
    jr z,select_complete_page
    cp 4
    jr nz,select_track_bad
    ld a,(hybrid_ready)
    or a
    jr z,select_track_bad
    or a
    ret
select_sparse_page:
    ld hl,(PAGE_ENTRY+4)
    ld a,h
    or l
    jr nz,select_track_bad
    ld a,(PAGE_ENTRY+3)
    cp 2
    jr nc,select_track_bad
    ; Packed and raw page payloads must fit page-2 scratch and 16-bit streams.
    ld hl,(PAGE_ENTRY+14)
    ld a,h
    or l
    jr nz,select_track_bad
    ld hl,(PAGE_ENTRY+18)
    ld a,h
    or l
    jr nz,select_track_bad
    ld hl,(PAGE_ENTRY+16)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,select_track_bad
    or a
    ret
select_complete_page:
    ld hl,(PAGE_ENTRY+4)
    ld a,h
    or l
    jr nz,select_track_bad
    ld a,(PAGE_ENTRY+3)
    cp 2
    jr nc,select_track_bad
    ld hl,(PAGE_ENTRY+14)
    ld a,h
    or l
    jr nz,select_track_bad
    ld hl,(PAGE_ENTRY+16)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,select_track_bad
    ld hl,(PAGE_ENTRY+18)
    ld a,h
    or l
    jr nz,select_track_bad
    or a
    ret
select_track_bad:
    scf
    ret

mul16x16_24:
    ; HL * DE -> A:HL (low 24 bits), shift/add in 16 iterations.
    ld (mul_multiplicand),hl
    xor a
    ld (mul_multiplicand+2),a
    ld (mul_multiplier),de
    ld hl,0
    ld (mul_result),hl
    ld (mul_result+2),a
    ld b,16
mul24_loop:
    ld hl,(mul_multiplier)
    bit 0,l
    jr z,mul24_no_add
    ld hl,(mul_result)
    ld de,(mul_multiplicand)
    add hl,de
    ld (mul_result),hl
    ld a,(mul_result+2)
    ld c,a
    ld a,(mul_multiplicand+2)
    adc a,c
    ld (mul_result+2),a
mul24_no_add:
    ld hl,(mul_multiplicand)
    add hl,hl
    ld (mul_multiplicand),hl
    ld a,(mul_multiplicand+2)
    adc a,a
    ld (mul_multiplicand+2),a
    ld hl,(mul_multiplier)
    srl h
    rr l
    ld (mul_multiplier),hl
    djnz mul24_loop
    ld hl,(mul_result)
    ld a,(mul_result+2)
    ret

; Dedicated small multiplication: HL index, DE entry size/count -> HL.
; Used only when the complete result is already bounded by a page-0 buffer.
mul16_real:
    ld b,h
    ld c,l
    ld hl,0
mul16_real_loop:
    ld a,b
    or c
    ret z
    add hl,de
    dec bc
    jr mul16_real_loop

show_current_title:
    call restore_process_pages
    ld de,msg_track_prefix
    ld bc,msg_track_prefix_end-msg_track_prefix
    call write_stdout
    ld hl,(selected_track)
    call print_u16
    ld de,msg_colon
    ld bc,msg_colon_end-msg_colon
    call write_stdout

    ; 0xFFFFFFFF means no title.
    ld hl,(TRACK_ENTRY+12)
    ld a,h
    and l
    cp 0xFF
    jr nz,show_title_present
    ld hl,(TRACK_ENTRY+14)
    ld a,h
    and l
    cp 0xFF
    jr z,show_title_done
show_title_present:
    ; Clear the fixed read buffer so a short final read remains terminated.
    xor a
    ld hl,TITLE_BUFFER
    ld de,TITLE_BUFFER+1
    ld (hl),a
    ld bc,159
    ldir
    ; title absolute offset = string table + track title offset
    ld hl,(TRACK_ENTRY+12)
    ld a,(TRACK_ENTRY+14)
    ld c,a
    ld de,(KSP_HEADER+0x30)
    add hl,de
    ld a,(KSP_HEADER+0x32)
    adc a,c
    ld de,TITLE_BUFFER
    ld bc,160
    call read_at
    jr nz,show_title_done
    ld hl,TITLE_BUFFER
    ld bc,160
show_title_scan:
    ld a,b
    or c
    jr z,show_title_write
    ld a,(hl)
    or a
    jr z,show_title_write
    ; DOS text output is ASCII-only for now. Never send UTF-8 continuation
    ; bytes or C0 controls to the console because they can move the cursor.
    cp 0x80
    jr nc,show_title_write
    cp 0x20
    jr nc,show_title_ascii
    ld a,'?'
    ld (hl),a
show_title_ascii:
    inc hl
    dec bc
    jr show_title_scan
show_title_write:
    ; HL points one byte past the last printable title byte.
    ld de,TITLE_BUFFER
    or a
    sbc hl,de
    ld b,h
    ld c,l
    call write_stdout
show_title_done:
    ld de,msg_newline
    ld bc,msg_newline_end-msg_newline
    call write_stdout
    ret

install_current_track:
    di
    call stop_engine
    call restore_process_pages
    ld a,(PAGE_ENTRY+2)
    cp 1
    jr z,install_complete

    ; Sparse and hybrid pages start from the common engine template.
    ld a,1
    ld (decode_stage),a
    call load_template_page
    jr c,install_bad
    ld a,(PAGE_ENTRY+2)
    or a
    jr z,install_sparse
    cp 4
    jr nz,install_bad
    ld a,4
    ld (decode_stage),a
    call apply_hybrid_page
    jr c,install_bad
    jr install_start_engine

install_sparse:
    ld a,2
    ld (decode_stage),a
    call apply_sparse_page
    jr c,install_bad
    jr install_start_engine

install_complete:
    ld a,3
    ld (decode_stage),a
    call load_complete_page
    jr c,install_bad

install_start_engine:
    call map_scc_page2
    call call_init
    ld a,1
    ld (engine_running),a
    ei
    or a
    ret
install_bad:
    call restore_process_pages
    scf
    ret

load_template_page:
    ld a,(template_compression)
    or a
    jr z,load_template_raw
    ld hl,(ENGINE_ENTRY+36)
    ld a,(ENGINE_ENTRY+38)
    ld de,(ENGINE_ENTRY+40)
    ld b,d
    ld c,e
    call stream_begin
    ret c
    xor a
    ld (zx_mode),a
    ld hl,0x4000
    ld (linear_base),hl
    ld hl,0x4000
    xor a
    call zx_set_output_size
    jp zx_decode
load_template_raw:
    ld hl,(ENGINE_ENTRY+36)
    ld a,(ENGINE_ENTRY+38)
    ld de,0x4000
    ld bc,0x4000
    call read_at
    jr nz,load_template_bad
    or a
    ret
load_template_bad:
    scf
    ret

load_complete_page:
    ld a,(PAGE_ENTRY+3)
    or a
    jr z,load_complete_raw
    call begin_page_payload_stream
    ret c
    xor a
    ld (zx_mode),a
    ld hl,0x4000
    ld (linear_base),hl
    ld hl,0x4000
    xor a
    call zx_set_output_size
    jp zx_decode
load_complete_raw:
    ld hl,(PAGE_ENTRY+12)
    ld de,0x4000
    or a
    sbc hl,de
    jr nz,load_complete_bad
    ld hl,(PAGE_ENTRY+8)
    ld a,(PAGE_ENTRY+10)
    ld de,0x4000
    ld bc,0x4000
    call read_at
    jr nz,load_complete_bad
    or a
    ret
load_complete_bad:
    scf
    ret

begin_page_payload_stream:
    ld hl,(PAGE_ENTRY+8)
    ld a,(PAGE_ENTRY+10)
    ld de,(PAGE_ENTRY+12)
    ld b,d
    ld c,e
    jp stream_begin

apply_sparse_page:
    ld hl,(PAGE_ENTRY+16)
    ld a,h
    or l
    ret z
    ld a,(PAGE_ENTRY+3)
    or a
    jr z,load_sparse_raw
    call begin_page_payload_stream
    ret c
    xor a
    ld (zx_mode),a
    ld hl,0x8000
    ld (linear_base),hl
    ld hl,(PAGE_ENTRY+16)
    xor a
    call zx_set_output_size
    call zx_decode
    ret c
    jr apply_sparse_records
load_sparse_raw:
    ld hl,(PAGE_ENTRY+12)
    ld de,(PAGE_ENTRY+16)
    or a
    sbc hl,de
    jr nz,sparse_bad
    ld hl,(PAGE_ENTRY+8)
    ld a,(PAGE_ENTRY+10)
    ld de,0x8000
    ld bc,(PAGE_ENTRY+16)
    call read_at
    jr nz,sparse_bad

apply_sparse_records:
    ld hl,0x8000
    ld (overlay_ptr),hl
    ld hl,(PAGE_ENTRY+16)
    ld (overlay_remaining),hl
    ld hl,0
    ld (overlay_previous_end),hl
sparse_record_loop:
    ld hl,(overlay_remaining)
    ld a,h
    or l
    ret z
    ld de,4
    or a
    sbc hl,de
    jr c,sparse_bad
    ld (overlay_remaining),hl

    ld hl,(overlay_ptr)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld (overlay_ptr),hl
    ld (overlay_offset),de
    ld (overlay_length),bc
    ld a,b
    or c
    jr z,sparse_bad

    ; Ordered, non-overlapping destination records.
    ld hl,(overlay_offset)
    ld de,(overlay_previous_end)
    or a
    sbc hl,de
    jr c,sparse_bad

    ; Destination end must not exceed the 16 KiB engine page.
    ld hl,(overlay_offset)
    ld de,(overlay_length)
    add hl,de
    jr c,sparse_bad
    ld (overlay_end),hl
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,sparse_bad

    ; The record data must remain inside the decoded payload.
    ld hl,(overlay_remaining)
    ld bc,(overlay_length)
    or a
    sbc hl,bc
    jr c,sparse_bad
    ld (overlay_remaining),hl

    ; Copy page-2 scratch bytes into their page-1 destination.
    ld hl,(overlay_ptr)
    push hl
    ld hl,0x4000
    ld de,(overlay_offset)
    add hl,de
    ex de,hl
    pop hl
    ld bc,(overlay_length)
    ldir
    ld (overlay_ptr),hl
    ld hl,(overlay_end)
    ld (overlay_previous_end),hl
    jr sparse_record_loop
sparse_bad:
    scf
    ret

apply_hybrid_page:
    ld hl,(current_page)
    ld de,(hpl_position_count)
    call mul16_real
    add hl,hl
    ld de,MAP_BUFFER
    add hl,de
    ld (current_map_ptr),hl
    ld hl,POS_BUFFER
    ld (current_pos_ptr),hl
    ld bc,(hpl_position_count)
apply_page_loop:
    ld a,b
    or c
    ret z
    push bc
    ld hl,(current_pos_ptr)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (current_pos_ptr),hl
    ld hl,(current_map_ptr)
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld (current_map_ptr),hl
    ; DE destination offset, BC global block ID
    push de
    push bc
    call copy_global_block
    pop bc
    pop de
    pop bc
    ret c
    dec bc
    jr apply_page_loop

copy_global_block:
    ; BC global block ID, DE page-relative destination
    ld hl,(hpl_hot_count)
    or a
    sbc hl,bc
    jr c,block_not_hot
    jr z,block_not_hot
    call copy_hot_block
    ret
block_not_hot:
    ld hl,(hpl_hot_count)
    ld a,c
    sub l
    ld c,a
    ld a,b
    sbc a,h
    ld b,a
    ld hl,(hpl_warm_count)
    or a
    sbc hl,bc
    jr c,block_not_warm
    jr z,block_not_warm
    call copy_warm_block
    ret
block_not_warm:
    ld hl,(hpl_warm_count)
    ld a,c
    sub l
    ld c,a
    ld a,b
    sbc a,h
    ld b,a
    call copy_cold_block
    ret

copy_hot_block:
    ; BC hot index, DE destination offset.
    push de
    ld h,b
    ld l,c
    call shift_block_offset
    ; Hot is capped at 48 KiB, so the 24-bit high byte must be zero.
    or a
    jr nz,copy_hot_bad
    push hl
    ld a,h
    and 0xC0
    rlca
    rlca
    ld c,a
    ld b,0
    ld hl,hot_segments
    add hl,bc
    ld a,(hl)
    call map_p2
    pop hl
    ld a,h
    and 0x3F
    or 0x80
    ld h,a
    pop de
    ld a,d
    and 0x3F
    or 0x40
    ld d,a
    ld bc,(hpl_block_size)
    ldir
    or a
    ret
copy_hot_bad:
    pop de
    scf
    ret

copy_warm_block:
    ; BC warm index, DE destination offset
    push de
    ld h,b
    ld l,c
    call shift_block_offset
    ; A:HL relative VRAM offset; add 0x8000
    ld de,0x8000
    add hl,de
    adc a,0
    call vram_set_read_address
    pop de
    ld hl,0x4000
    add hl,de
    ex de,hl
    ld bc,(hpl_block_size)
copy_warm_loop:
    in a,(PORT_VDP_DATA)
    ld (de),a
    inc de
    dec bc
    ld a,b
    or c
    jr nz,copy_warm_loop
    or a
    ret

copy_cold_block:
    ; BC cold block index, DE destination offset. Decode one <=16 KiB slab.
    push de
    ld a,14
    ld d,a
    ld a,(hpl_block_shift)
    ld e,a
    ld a,d
    sub e
    jr c,cold_bad
    ld (cold_div_shift),a
    ld h,b
    ld l,c
cold_div_loop:
    ld a,(cold_div_shift)
    or a
    jr z,cold_div_done
    srl h
    rr l
    dec a
    ld (cold_div_shift),a
    jr cold_div_loop
cold_div_done:
    ; HL is the cold slab index.
    ld de,(cold_cached_slab)
    or a
    sbc hl,de
    jr z,cold_cache_ready
    add hl,de
    push bc
    call load_cold_slab
    pop bc
    jr c,cold_bad
cold_cache_ready:
    ; within-slab offset = cold index * block_size modulo 16 KiB
    ld h,b
    ld l,c
    call shift_block_offset
    ld a,h
    and 0x3F
    or 0x80
    ld h,a
    pop de
    ld a,d
    and 0x3F
    or 0x40
    ld d,a
    ld bc,(hpl_block_size)
    ldir
    or a
    ret
cold_bad:
    pop de
    scf
    ret

load_cold_slab:
    ; HL slab index
    ld (cold_cached_slab),hl
    ; descriptor absolute = HPOL + cold_table_off + index*16
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    ld de,(hpl_cold_table_off)
    add hl,de
    ld a,(hpl_cold_table_off+2)
    adc a,0
    ld de,(hpol_offset_lo)
    add hl,de
    ld c,a
    ld a,(hpol_offset_hi)
    adc a,c
    ld de,RESOURCE_ENTRY
    ld bc,16
    call read_at
    jr nz,load_cold_bad
    ld a,(RESOURCE_ENTRY+10)
    cp 1
    jr nz,load_cold_bad
    ld hl,(RESOURCE_ENTRY+8)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,load_cold_bad
    ; stream offset = HPOL + descriptor packed offset
    ld hl,(RESOURCE_ENTRY)
    ld a,(RESOURCE_ENTRY+2)
    ld de,(hpol_offset_lo)
    add hl,de
    ld c,a
    ld a,(hpol_offset_hi)
    adc a,c
    ld de,(RESOURCE_ENTRY+4)
    ld b,d
    ld c,e
    call stream_begin
    jr c,load_cold_bad
    ld a,(original_p2)
    call map_p2
    xor a
    ld (zx_mode),a
    ld hl,0x8000
    ld (linear_base),hl
    ld hl,(RESOURCE_ENTRY+8)
    xor a
    call zx_set_output_size
    call zx_decode
    jr c,load_cold_bad
    or a
    ret
load_cold_bad:
    scf
    ret

shift_block_offset:
    ; HL index -> A:HL = index << hpl_block_shift
    xor a
    ld b,a
    ld a,(hpl_block_shift)
    ld b,a
    xor a
shift_block_loop:
    add hl,hl
    adc a,a
    djnz shift_block_loop
    ret

next_track:
    di
    call stop_engine
    call restore_process_pages
    ld hl,(selected_track)
    inc hl
    ld de,(KSP_HEADER+0x24)
    or a
    sbc hl,de
    jr c,next_track_in_range
    ld hl,0
    jr next_track_selected
next_track_in_range:
    add hl,de
next_track_selected:
    call select_track
    ret c
    call show_current_title
    call install_current_track
    ret

stop_engine:
    ld a,(engine_running)
    or a
    ret z
    xor a
    ld (engine_running),a
    ld hl,(ENGINE_ENTRY+20)
    ld a,h
    or l
    ret z
    ld (stop_call+1),hl
    call map_scc_page2
stop_call:
    call 0
    ret

call_init:
    ld hl,(ENGINE_ENTRY+16)
    ld (init_call+1),hl
    ld hl,(current_song_id)
    ld a,l
    ld bc,0
    ld de,0
init_call:
    call 0
    ret

call_play:
    ld hl,(ENGINE_ENTRY+18)
    ld (play_call+1),hl
play_call:
    call 0
    ret

read_controls:
    ; returns A=0 none, 1 escape, 2 space edge
    in a,(PORT_KEY_ROW)
    ld d,a
    and 0xF0
    or 7
    out (PORT_KEY_ROW),a
    in a,(PORT_KEY_IN)
    ld e,a
    ld a,d
    out (PORT_KEY_ROW),a
    ld a,e
    bit 2,a
    jr z,control_escape
    in a,(PORT_KEY_ROW)
    ld d,a
    and 0xF0
    or 8
    out (PORT_KEY_ROW),a
    in a,(PORT_KEY_IN)
    ld e,a
    ld a,d
    out (PORT_KEY_ROW),a
    ld a,e
    and 1
    ld b,a
    ld a,(space_previous)
    ld c,a
    ld a,b
    ld (space_previous),a
    or a
    jr nz,control_none
    ld a,c
    or a
    jr z,control_none
    ld a,2
    ret
control_escape:
    ld a,1
    ret
control_none:
    xor a
    ret

; ---------------------------------------------------------------------------
; Streaming ZX0 decoder
; ---------------------------------------------------------------------------
stream_begin:
    ; A:HL absolute offset, DE:BC packed size (DE high word accepted, profile <64K)
    ld (stream_offset_lo),hl
    ld (stream_offset_hi),a
    ld h,b
    ld l,c
    ld (stream_remaining),hl
    xor a
    ld (stream_remaining+2),a
    ld hl,0
    ld (input_count),hl
    ld (input_ptr),hl
    ld (zx_bit_mask),a
    ld (zx_backtrack),a
    ; seek once
    ld a,(file_handle)
    ld b,a
    xor a
    ld d,0
    ld a,(stream_offset_hi)
    ld e,a
    ld hl,(stream_offset_lo)
    ld c,DOS_SEEK
    call BDOS
    jr nz,stream_begin_bad
    or a
    ret
stream_begin_bad:
    scf
    ret

stream_refill:
    ; Preserve current page mappings while DOS gets its normal process pages.
    ld a,(mapped_p1)
    ld (saved_map_p1),a
    ld a,(mapped_p2)
    ld (saved_map_p2),a
    call restore_process_pages
    ld hl,(stream_remaining)
    ld a,(stream_remaining+2)
    or h
    or l
    jr z,refill_eof
    ld de,IO_BUFFER_SIZE
    ld a,(stream_remaining+2)
    or a
    jr nz,refill_use_512
    or a
    sbc hl,de
    jr nc,refill_use_512
    add hl,de
    jr refill_count_ready
refill_use_512:
    ld hl,IO_BUFFER_SIZE
refill_count_ready:
    ld (refill_count),hl
    ld a,(file_handle)
    ld b,a
    ld de,IO_BUFFER
    ld c,DOS_READ
    call BDOS
    jr nz,refill_error
    ld a,h
    or l
    jr z,refill_error
    ld (input_count),hl
    ld d,h
    ld e,l
    ld hl,(stream_remaining)
    or a
    sbc hl,de
    ld (stream_remaining),hl
    ld a,(stream_remaining+2)
    sbc a,0
    ld (stream_remaining+2),a
    ld hl,IO_BUFFER
    ld (input_ptr),hl
    call restore_saved_maps
    or a
    ret
refill_eof:
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
    ld hl,(input_count)
    ld a,h
    or l
    jr nz,zx_read_have
    ; ZX0 keeps gamma values and copy lengths in BC, and callers may also
    ; have live DE/HL values. DOS_READ, DOS_SEEK and mapper callbacks are
    ; allowed to destroy all of them, so preserve them across a refill.
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
    jr z,zx_read_bit_normal
    xor a
    ld (zx_backtrack),a
    ld a,(zx_last_byte)
    and 1
    ret
zx_read_bit_normal:
    ld a,(zx_bit_mask)
    or a
    jr nz,zx_have_mask
    call zx_read_byte
    ret c
    ld (zx_bit_value),a
    ld a,0x80
    ld (zx_bit_mask),a
zx_have_mask:
    ; The Elias value and copy lengths live in BC.  Never use B as a
    ; temporary here: doing so corrupts every gamma value as bits are read.
    push de
    ld e,a
    ld a,(zx_bit_value)
    and e
    jr z,zx_bit_zero
    ld a,1
    jr zx_bit_result
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
    jr zx_gamma
zx_gamma_inverted:
    ld a,1
    ld (gamma_invert),a
zx_gamma:
    ld bc,1
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
    jr zx_gamma_loop

zx_set_output_size:
    ; A:HL raw output size
    ld (zx_remaining),hl
    ld (zx_remaining+2),a
    xor a
    ld (zx_output_pos),a
    ld (zx_output_pos+1),a
    ld (zx_output_pos+2),a
    ret

zx_output_finished:
    ld hl,(zx_remaining)
    ld a,(zx_remaining+2)
    or h
    or l
    ret

zx_decode:
    ld hl,1
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
    jr nz,zx_new_offset
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
    jr nz,zx_new_offset
    call zx_gamma_normal
    ret c
    call zx_copy_literals
    ret c
    jr zx_main_loop
zx_new_offset:
    call zx_gamma_inverted
    ret c
    ld h,b
    ld l,c
    ld de,256
    or a
    sbc hl,de
    jr z,zx_decode_done
    add hl,de
    ; offset = gamma * 128 - (lsb >> 1)
    ld a,7
zx_offset_shift:
    add hl,hl
    dec a
    jr nz,zx_offset_shift
    push hl
    call zx_read_byte
    pop hl
    ret c
    ld e,a
    srl e
    ld d,0
    or a
    sbc hl,de
    ld (zx_last_offset),hl
    ld a,1
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
    jr nz,zx_new_offset
    call zx_gamma_normal
    ret c
    call zx_copy_literals
    ret c
    jr zx_main_loop
zx_decode_done:
    or a
    ret

zx_copy_literals:
    ; BC count
zx_literal_loop:
    ld a,b
    or c
    ret z
    call zx_read_byte
    ret c
    call zx_write_output
    ret c
    dec bc
    jr zx_literal_loop

zx_copy_match:
    ; BC count, zx_last_offset
zx_match_loop:
    ld a,b
    or c
    ret z
    push bc
    ld hl,(zx_last_offset)
    call zx_read_history
    pop bc
    ret c
    call zx_write_output
    ret c
    dec bc
    jr zx_match_loop

zx_write_output:
    push af
    ld a,(zx_mode)
    or a
    jr z,zx_write_linear
    cp 1
    jr z,zx_write_warm
    pop af
    call hot_write_byte
    jr zx_write_account
zx_write_linear:
    pop af
    ld hl,(linear_base)
    ld de,(zx_output_pos)
    add hl,de
    ld (hl),a
    jr zx_write_account
zx_write_warm:
    pop af
    push af
    ; ring address = 4000h + (output_pos & 7FFFh)
    ld hl,(zx_output_pos)
    ld a,h
    and 0x7F
    or 0x40
    ld h,a
    pop af
    ld (hl),a
    out (PORT_VDP_DATA),a
zx_write_account:
    ; Advance 24-bit output position.
    ld hl,(zx_output_pos)
    inc hl
    ld (zx_output_pos),hl
    ld a,h
    or l
    jr nz,zx_position_done
    ld a,(zx_output_pos+2)
    inc a
    ld (zx_output_pos+2),a
zx_position_done:
    ; Refuse output beyond the declared object size.
    ld hl,(zx_remaining)
    ld a,(zx_remaining+2)
    or h
    or l
    jr z,zx_write_overflow
    ld hl,(zx_remaining)
    ld a,h
    or l
    jr nz,zx_remaining_low_nonzero
    ld hl,0xFFFF
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
    ; HL offset; return byte in A
    push hl
    ld de,(zx_output_pos)
    ex de,hl
    pop de
    or a
    sbc hl,de
    ld a,(zx_output_pos+2)
    sbc a,0
    ld (history_pos_lo),hl
    ld (history_pos_hi),a
    ld a,(zx_mode)
    or a
    jr z,zx_read_linear
    cp 1
    jr z,zx_read_warm
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
    and 0x7F
    or 0x40
    ld h,a
    ld a,(hl)
    or a
    ret

hot_write_byte:
    ; A byte, output position selects mapper destination
    push af
    call hot_output_segment
    ld b,a
    ld a,(hot_write_mapped)
    cp b
    jr z,hot_write_seg_ok
    ld a,b
    ld (hot_write_mapped),a
    ld hl,hot_segments
    ld c,a
    ld b,0
    add hl,bc
    ld a,(hl)
    call map_p2
hot_write_seg_ok:
    ld hl,(zx_output_pos)
    ld a,h
    and 0x3F
    or 0x80
    ld h,a
    pop af
    ld (hl),a
    ret

hot_read_byte:
    call hot_history_segment
    ld b,a
    call hot_output_segment
    cp b
    jr nz,hot_read_other
    ld hl,(history_pos_lo)
    ld a,h
    and 0x3F
    or 0x80
    ld h,a
    ld a,(hl)
    or a
    ret
hot_read_other:
    ld a,(hot_read_mapped)
    cp b
    jr z,hot_read_seg_ok
    ld a,b
    ld (hot_read_mapped),a
    ld hl,hot_segments
    ld c,a
    ld b,0
    add hl,bc
    ld a,(hl)
    call map_p1
hot_read_seg_ok:
    ld hl,(history_pos_lo)
    ld a,h
    and 0x3F
    or 0x40
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
    and 3
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
    and 3
    or b
    ret

; ---------------------------------------------------------------------------
; VDP helpers
; ---------------------------------------------------------------------------
vram_set_warm_base_write:
    ld hl,0x8000
    xor a
    call vram_set_write_address
    ret

vram_set_write_address:
    ; A:HL 17-bit address
    ld d,a
    ld a,h
    rlca
    rlca
    and 3
    ld e,a
    ld a,d
    add a,a
    add a,a
    or e
    and 7
    out (PORT_VDP_CTRL),a
    ld a,0x8E
    out (PORT_VDP_CTRL),a
    ld a,l
    out (PORT_VDP_CTRL),a
    ld a,h
    and 0x3F
    or 0x40
    out (PORT_VDP_CTRL),a
    ret

vram_set_read_address:
    ; A:HL 17-bit address
    ld d,a
    ld a,h
    rlca
    rlca
    and 3
    ld e,a
    ld a,d
    add a,a
    add a,a
    or e
    and 7
    out (PORT_VDP_CTRL),a
    ld a,0x8E
    out (PORT_VDP_CTRL),a
    ld a,l
    out (PORT_VDP_CTRL),a
    ld a,h
    and 0x3F
    out (PORT_VDP_CTRL),a
    ret

; ---------------------------------------------------------------------------
; Numeric output
; ---------------------------------------------------------------------------
print_u16:
    ; HL unsigned decimal. UI-only conversion; repeated subtraction is adequate.
    ld de,decimal_buffer+6
    xor a
    ld (de),a
print_u16_loop:
    ; div10_u16 uses DE as its divisor. Preserve the decimal-buffer pointer;
    ; the old code wrote digits to 0009h and corrupted DOS/BIOS low memory.
    push de
    call div10_u16
    pop de
    add a,'0'
    dec de
    ld (de),a
    ld a,h
    or l
    jr nz,print_u16_loop
    push de
    ld hl,decimal_buffer+6
    or a
    sbc hl,de
    ld b,h
    ld c,l
    pop de
    call write_stdout
    ret

; HL / 10 -> HL quotient, A remainder.
div10_u16:
    ld de,10
    ld bc,0
div10_loop:
    or a
    sbc hl,de
    jr c,div10_done
    inc bc
    jr div10_loop
div10_done:
    add hl,de
    ld a,l
    ld h,b
    ld l,c
    ret

; ---------------------------------------------------------------------------
; Variables and messages
; ---------------------------------------------------------------------------
file_handle:            db 0
scc_slot:               db 2
cmd_remaining:          db 0
selected_track:         dw 0
current_page:           dw 0
current_song_id:        dw 0
space_previous:         db 1

mapper_ready:           db 0
engine_running:         db 0
decode_stage:           db 0
hybrid_ready:          db 0
template_compression:   db 0
mapper_base:            dw 0
mapper_all:             dw 0
mapper_free:            dw 0
mapper_put_p1:          dw 0
mapper_put_p2:          dw 0
mapper_get_p1:          dw 0
mapper_get_p2:          dw 0
mapper_free_count:      db 0
original_p1:            db 0
original_p2:            db 0
original_a8:            db 0
mapped_p1:              db 0
mapped_p2:              db 0
saved_map_p1:           db 0
saved_map_p2:           db 0
hot_segments:           db 0,0,0
hot_segment_count:      db 0
hot_needed_count:       db 0
hot_write_mapped:       db 0xFF
hot_read_mapped:        db 0xFF

tmp_offset_lo:          dw 0
mul_multiplicand:       db 0,0,0
mul_multiplier:         dw 0
mul_result:             db 0,0,0
tmp_offset_hi:          db 0
resource_count:         dw 0
resource_index:         dw 0
resource_cursor_lo:     dw 0
resource_cursor_hi:     db 0
hpol_offset_lo:         dw 0
hpol_offset_hi:         db 0
hpol_size_lo:           dw 0
hpol_size_hi:           db 0
abs_offset_lo:          dw 0
abs_offset_hi:          db 0

hpl_block_size:         dw 0
hpl_block_shift:        db 0
hpl_position_count:     dw 0
hpl_hot_count:          dw 0
hpl_warm_count:         dw 0
hpl_cold_count:         dw 0
hpl_slab_count:         dw 0
hpl_positions_off:      db 0,0,0
hpl_maps_off:           db 0,0,0
hpl_maps_packed:        db 0,0,0
hpl_maps_raw:           db 0,0,0
hpl_hot_off:            db 0,0,0
hpl_hot_packed:         db 0,0,0
hpl_hot_raw:            db 0,0,0
hpl_warm_off:           db 0,0,0
hpl_warm_packed:        db 0,0,0
hpl_warm_raw:           db 0,0,0
hpl_cold_table_off:     db 0,0,0
cold_cached_slab:       dw 0xFFFF
cold_div_shift:         db 0
current_map_ptr:        dw 0
current_pos_ptr:        dw 0
overlay_ptr:            dw 0
overlay_remaining:      dw 0
overlay_previous_end:   dw 0
overlay_offset:         dw 0
overlay_length:         dw 0
overlay_end:            dw 0

stream_offset_lo:       dw 0
stream_offset_hi:       db 0
stream_remaining:       db 0,0,0
input_ptr:              dw 0
input_count:            dw 0
refill_count:           dw 0
zx_mode:                db 0
zx_bit_value:           db 0
zx_bit_mask:            db 0
zx_last_byte:           db 0
zx_backtrack:           db 0
gamma_invert:           db 0
zx_last_offset:         dw 1
zx_output_pos:          db 0,0,0
zx_remaining:           db 0,0,0
linear_base:            dw 0
history_pos_lo:         dw 0
history_pos_hi:         db 0

decimal_buffer:         ds 7,0
filename:               ds 128,0

msg_banner: db 'KSP1PLAY 0.6 - KSP 1.0 page player',13,10
msg_banner_end:
msg_usage: db 'Usage: KSP1PLAY file.ksp [track] [SCC primary slot 0-3]',13,10
msg_usage_end:
msg_format: db 'Error: invalid or unsupported KSP 1.0 file.',13,10
msg_format_end:
msg_profile: db 'Error: engine must be a 4000h-7FFFh 16K MSX page.',13,10
msg_profile_end:
msg_mapper: db 'Error: MSX-DOS2 mapper API unavailable.',13,10
msg_mapper_end:
msg_memory: db 'Error: insufficient mapper segments for hot pool.',13,10
msg_memory_end:
msg_file: db 'Error: file access failed.',13,10
msg_file_end:
msg_track: db 'Error: track/page is invalid.',13,10
msg_track_end:
msg_decode: db 'Error: ZX0 or page reconstruction failed.',13,10
msg_decode_end:
msg_decode_template: db 'Error: engine template ZX0 decoding failed.',13,10
msg_decode_template_end:
msg_decode_sparse: db 'Error: sparse overlay decoding or records failed.',13,10
msg_decode_sparse_end:
msg_decode_complete: db 'Error: complete page decoding failed.',13,10
msg_decode_complete_end:
msg_decode_hybrid: db 'Error: hybrid pool decoding or reconstruction failed.',13,10
msg_decode_hybrid_end:
msg_track_prefix: db 'Track '
msg_track_prefix_end:
msg_colon: db ': '
msg_colon_end:
msg_newline: db 13,10
msg_newline_end:

program_end:
