; KSP1PLAY.COM - graphical MSX-DOS1 KSP 1.00/1.01 player v0.20.0
; Generated with tools/z80asm.py. No external assembler required.
;
; Current executable profile:
;   - KSP1 1.00/1.01 header/tables, 16-bit tracks
;   - declarative PAGE2_RUNTIME and private PAGE3_WORKRAM profiles
;   - resident program, stack, tables and buffers entirely in page 0
;   - one 16 KiB engine loaded at 4000h
;   - KSP_PAGE_SPARSE_OVERLAY, COMPLETE and HYBRID_POOL
;   - HPOL / HPL1 when present
;   - sparse-pack file cache in VRAM and common template in mapper RAM
;   - hot pool in up to three mapper segments
;   - warm pool in VRAM at 08000h, with a 32 KiB RAM history window
;   - cold slabs decoded on demand into page 2
;   - PSG + SCC/SCC+ + dual normal SCC + YM2413 + OPL4/MoonSound playback
;
; Usage: KSP1PLAY [file.ksp [track] [scc-a-slot] [scc-b-slot]]
; DOS1 standalone profile: current directory and 8.3 filenames only.

org 0x0100

BDOS            equ 0x0005
DOS_TERM0       equ 0x00
DOS_CONOUT      equ 0x02
DOS_CONST       equ 0x0B
DOS_FOPEN       equ 0x0F
DOS_FCLOSE      equ 0x10
DOS_SFIRST      equ 0x11
DOS_SNEXT       equ 0x12
DOS_SETDTA      equ 0x1A
DOS_RDBLK       equ 0x27

PORT_MAPPER_P0  equ 0xFC
PORT_MAPPER_P1  equ 0xFD
PORT_MAPPER_P2  equ 0xFE
PORT_MAPPER_P3  equ 0xFF

PORT_PPI_A      equ 0xA8
PORT_KEY_IN     equ 0xA9
PORT_KEY_ROW    equ 0xAA
PORT_VDP_DATA   equ 0x98
PORT_VDP_CTRL   equ 0x99
RG9SAV          equ 0xFFE8            ; BIOS shadow of VDP register 9
PORT_PSG_ADDR   equ 0xA0
PORT_PSG_DATA   equ 0xA1
PORT_FM_ADDR    equ 0x7C
PORT_FM_DATA    equ 0x7D
PORT_OPL4_FM0_A equ 0xC4
PORT_OPL4_FM0_D equ 0xC5
PORT_OPL4_FM1_A equ 0xC6
PORT_OPL4_FM1_D equ 0xC7
PORT_OPL4_WAVE_A equ 0x7E
PORT_OPL4_WAVE_D equ 0x7F

 ; Page 0 is the only permanently owned CPU address space. MSX-DOS1 keeps
; page 3; PAGE3_WORKRAM maps a private segment only around engine calls.
; The binary must end before ENGINE_ENTRY; build.py enforces this memory map.
DYNAMIC_GATEWAY equ 0x2000            ; sparse dynamic handler (POS buffer is HPOL-only)
KSP_HEADER      equ 0x1DA0            ; 80 bytes, in the title/IO gap
ENGINE_ENTRY    equ 0x1C00            ; 64 bytes
TRACK_ENTRY     equ 0x1C40            ; 32 bytes
PAGE_ENTRY      equ 0x1C60            ; 24 bytes
RESOURCE_ENTRY  equ 0x1C80            ; 32 bytes / cold descriptor scratch
HPL_HEADER      equ 0x1CA0            ; 96 bytes
TITLE_BUFFER    equ 0x1D00            ; 160 bytes used
IO_BUFFER       equ 0x1E00
IO_BUFFER_SIZE  equ 512
POS_BUFFER      equ 0x3500            ; HPOL position cache, below stack
POS_BUFFER_MAX  equ 0x0200
MAP_ROW_BUFFER  equ 0x3700            ; one HPOL page-map row
UI_MODULE       equ 0x2200            ; Screen 5 menu/player UI
MAP_BUFFER_MAX  equ 0x4000            ; HPOL map matrix lives in one mapper segment
MAPPER_POOL_MAX equ 12                ; standalone DOS1 hidden-segment reserve
STACK_BOTTOM    equ 0x3900
STACK_TOP       equ 0x39F0
WARM_VRAM_BASE  equ 0x08000

start:
    ld sp,STACK_TOP
    call parse_command_line
    jp c,usage_error
    call get_mapper_api
    jp c,mapper_error
    call capture_original_pages
    jp ui_application

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
hardware_error:
    ld a,(hardware_error_code)
    cp 1
    jr nz,hardware_error_opl4
    ld de,msg_scc_slots
    ld bc,msg_scc_slots_end-msg_scc_slots
    jr fatal_with_file
hardware_error_opl4:
    ld de,msg_hardware
    ld bc,msg_hardware_end-msg_hardware
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
    ld de,msg_decode
    ld bc,msg_decode_end-msg_decode
    jr fatal_with_file
fatal_with_file:
    call write_stdout
    call cleanup
terminate_error_no_file:
    ld c,DOS_TERM0
    call BDOS
    ret

clean_exit:
    call cleanup
    ld c,DOS_TERM0
    call BDOS
    ret

; ---------------------------------------------------------------------------
; Command line
; ---------------------------------------------------------------------------
parse_command_line:
    xor a
    ld (filename),a
    ld (selected_track),a
    ld (selected_track+1),a
    ld a,2
    ld (scc_slot),a
    ld a,1
    ld (scc_slot_b),a
    ld hl,0x0081
    ld a,(0x0080)
    ld (cmd_remaining),a

parse_skip_spaces:
    ld a,(cmd_remaining)
    or a
    jr z,parse_good
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
    cp 15
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

parse_slot_b_spaces:
    ld a,(cmd_remaining)
    or a
    jr z,parse_good
    ld a,(hl)
    cp ' '
    jr nz,parse_slot_b_start
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a
    jr parse_slot_b_spaces

parse_slot_b_start:
    ld a,(hl)
    cp '0'
    jr c,parse_bad
    cp '4'
    jr nc,parse_bad
    sub '0'
    ld (scc_slot_b),a
    inc hl
    ld a,(cmd_remaining)
    dec a
    ld (cmd_remaining),a

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
    ; DE buffer, BC count. DOS1 has no handle-based WRITE, so emit characters.
write_stdout_loop:
    ld a,b
    or c
    ret z
    ld a,(de)
    push bc
    push de
    ld e,a
    ld c,DOS_CONOUT
    call BDOS
    pop de
    pop bc
    inc de
    dec bc
    jr write_stdout_loop

fcb_open_current:
    call fcb_prepare_filename
    ret c
    ld de,file_fcb
    ld c,DOS_FOPEN
    call BDOS
    or a
    jr nz,fcb_open_failed
    ld hl,1
    ld (file_fcb+14),hl       ; byte-addressable random-block records
    xor a
    ld (file_fcb+33),a
    ld (file_fcb+34),a
    ld (file_fcb+35),a
    ld (file_fcb+36),a
    ld a,1
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
    ld c,DOS_FCLOSE
    call BDOS
    xor a
    ld (file_open),a
    ret

fcb_set_random_offset:
    ld hl,(tmp_offset_lo)
    ld (file_fcb+33),hl
    ld a,(tmp_offset_hi)
    ld (file_fcb+35),a
    xor a
    ld (file_fcb+36),a
    ret

fcb_read_current:
    ; DE destination, BC byte count. The FCB random position advances itself.
    ld (fcb_request_count),bc
    push bc
    ld c,DOS_SETDTA
    call BDOS
    pop bc
    ld h,b
    ld l,c
    ld de,file_fcb
    ld c,DOS_RDBLK
    call BDOS
    or a
    jr nz,fcb_read_failed
    ld de,(fcb_request_count)
    or a
    sbc hl,de
    jr nz,fcb_read_failed
    xor a
    ret
fcb_read_failed:
    ld a,1
    or a
    ret

read_at:
    ; A:HL absolute 24-bit offset, DE destination, BC count.
    ; Sparse packs can be served entirely from the upper-VRAM file cache.
    ld (tmp_offset_hi),a
    ld (tmp_offset_lo),hl
    ld a,(file_cache_ready)
    or a
    jr z,read_at_disk
    push bc
    push de
    call vdp_irq_begin
    ld hl,(tmp_offset_lo)
    ld de,WARM_VRAM_BASE
    add hl,de
    ld a,(tmp_offset_hi)
    adc a,0
    call vram_set_read_address
    pop de
    pop bc
read_at_vram_loop:
    ld a,b
    or c
    jr z,read_at_vram_done
    in a,(PORT_VDP_DATA)
    ld (de),a
    inc de
    dec bc
    jr read_at_vram_loop
read_at_vram_done:
    call vdp_irq_end
    xor a
    ret
read_at_disk:
    call mute_fmpac_before_disk_io
    call fcb_set_random_offset
    call fcb_read_current
    ret

; ---------------------------------------------------------------------------
; Sparse-pack preload cache
; ---------------------------------------------------------------------------
preload_file_cache:
    xor a
    ; Cache the complete KSP at VRAM 08000h.  This area is used only when
    ; HPOL is absent.  Maximum size is 96 KiB, leaving low VRAM for the UI.
    ld a,(KSP_HEADER+0x0F)
    or a
    jr nz,preload_file_cache_bad
    ld a,(KSP_HEADER+0x0E)
    cp 2
    jr nc,preload_file_cache_bad
    or a
    jr z,preload_file_cache_size_ok
    ld hl,(KSP_HEADER+0x0C)
    ld de,0x8001
    or a
    sbc hl,de
    jr nc,preload_file_cache_bad
preload_file_cache_size_ok:
    ld hl,(KSP_HEADER+0x0C)
    ld (cache_remaining),hl
    ld a,(KSP_HEADER+0x0E)
    ld (cache_remaining+2),a
    ld (file_cache_size),hl
    ld (file_cache_size+2),a

    ; Transfer the file in random-block chunks. Every chunk re-establishes
    ; its absolute DOS1 FCB byte offset and absolute VRAM destination.
    xor a
    ld (cache_written),a
    ld (cache_written+1),a
    ld (cache_written+2),a
preload_file_cache_loop:
    ld hl,(cache_remaining)
    ld a,(cache_remaining+2)
    or h
    or l
    jr z,preload_file_cache_done
    ld de,IO_BUFFER_SIZE
    ld a,(cache_remaining+2)
    or a
    jr nz,preload_file_cache_512
    or a
    sbc hl,de
    jr nc,preload_file_cache_512
    add hl,de
    jr preload_file_cache_count
preload_file_cache_512:
    ld hl,IO_BUFFER_SIZE
preload_file_cache_count:
    ld (cache_chunk),hl
    ld hl,(cache_written)
    ld a,(cache_written+2)
    ld de,IO_BUFFER
    ld bc,(cache_chunk)
    call read_at
    jr nz,preload_file_cache_bad
    ; Re-establish the VRAM destination for this chunk.  Keep interrupts
    ; disabled only during the short 512-byte VDP burst, never during BDOS.
    call vdp_irq_begin
    ld hl,(cache_written)
    ld de,WARM_VRAM_BASE
    add hl,de
    ld a,(cache_written+2)
    adc a,0
    call vram_set_write_address
    ld bc,(cache_chunk)
    ld hl,IO_BUFFER
preload_file_cache_write:
    ld a,b
    or c
    jr z,preload_file_cache_written
    ld a,(hl)
    out (PORT_VDP_DATA),a
    inc hl
    dec bc
    jr preload_file_cache_write
preload_file_cache_written:
    call vdp_irq_end
    ld hl,(cache_written)
    ld de,(cache_chunk)
    add hl,de
    ld (cache_written),hl
    ld a,(cache_written+2)
    adc a,0
    ld (cache_written+2),a
    ld hl,(cache_remaining)
    ld de,(cache_chunk)
    or a
    sbc hl,de
    ld (cache_remaining),hl
    ld a,(cache_remaining+2)
    sbc a,0
    ld (cache_remaining+2),a
    jr preload_file_cache_loop
preload_file_cache_done:
    ld a,1
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
    ret z
    call mapper_alloc_user_primary
    ret c
    ld (engine_p3_segment),a
    ld a,1
    ld (engine_p3_segment_allocated),a
    ; Initialize the private work page once per opened package. Keep DOS1's
    ; page 3 unmapped for the shortest possible interval. FFFFh is the
    ; secondary-slot register on expanded slots, so clear through FFFEh.
    di
    ld a,(engine_p3_segment)
    out (0xFF),a
    xor a
    ld hl,0xC000
    ld (hl),a
    ld de,0xC001
    ld bc,0x3FFE
    ldir
    ld a,(original_p3)
    out (0xFF),a
    or a
    ret

free_page3_workram_segment:
    ld a,(engine_p3_segment_allocated)
    or a
    ret z
    ld a,(original_p3)
    out (0xFF),a
    ld a,(engine_p3_segment)
    call mapper_free_primary
    xor a
    ld (engine_p3_segment_allocated),a
    ret

allocate_template_segment:
    call mapper_alloc_user_primary
    ret c
    ld (template_segment),a
    ld a,1
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
    ; Decode the common 16 KiB page once into a dedicated mapper segment.
    call restore_process_pages
    ld a,(template_segment)
    call map_p1
    call decode_template_page
    push af
    call restore_process_pages
    pop af
    ret c
    ld a,1
    ld (template_cache_ready),a
    or a
    ret

get_mapper_api:
    ; MSX-DOS1 has no mapper allocation API. Detect the primary mapper size
    ; without writing to candidate segments, then reserve high hidden segments.
    ; Mapper sizes are standardized powers of two from 4 through 256 segments.
    di
    in a,(PORT_MAPPER_P1)
    ld (probe_original_p1),a
    ld e,a
    ld b,4
mapper_probe_loop:
    ; Read the candidate byte first and choose a marker guaranteed to differ.
    ld a,e
    add a,b
    ld d,a
    out (PORT_MAPPER_P1),a
    ld a,(0x4000)
    cpl
    ld (probe_marker),a

    ; Write the marker only to the currently active page-1 segment.
    ld a,e
    out (PORT_MAPPER_P1),a
    ld a,(0x4000)
    ld (probe_base_byte),a
    ld a,(probe_marker)
    ld (0x4000),a

    ; If base+N aliases the base segment, N is the mapper segment count.
    ld a,d
    out (PORT_MAPPER_P1),a
    ld a,(0x4000)
    ld c,a
    ld a,e
    out (PORT_MAPPER_P1),a
    ld a,(probe_base_byte)
    ld (0x4000),a
    ld a,c
    ld c,a
    ld a,(probe_marker)
    cp c
    jr z,mapper_probe_found
    sla b
    jr nz,mapper_probe_loop
    ld a,0xFF                  ; no alias through 128 => 256 segments
    jr mapper_probe_ready
mapper_probe_found:
    ld a,b
    dec a                      ; store highest valid segment number
mapper_probe_ready:
    ld (mapper_segment_mask),a
    ld a,(probe_original_p1)
    out (PORT_MAPPER_P1),a
    ei
    ; 128 KiB (8 segments) is the minimum useful standalone configuration.
    ld a,(mapper_segment_mask)
    cp 7
    jr c,get_mapper_fail
    or a
    ret
get_mapper_fail:
    scf
    ret

capture_original_pages:
    in a,(PORT_MAPPER_P0)
    ld (original_p0),a
    in a,(PORT_MAPPER_P1)
    ld (original_p1),a
    ld (mapped_p1),a
    in a,(PORT_MAPPER_P2)
    ld (original_p2),a
    ld (mapped_p2),a
    in a,(PORT_MAPPER_P3)
    ld (original_p3),a
    in a,(PORT_PPI_A)
    ld (original_a8),a
    call mapper_build_pool
    ld a,1
    ld (mapper_ready),a
    ret

mapper_build_pool:
    xor a
    ld (mapper_pool_count),a
    ld a,(mapper_segment_mask)
    ld b,a
mapper_pool_scan:
    ld a,b
    call mapper_segment_is_process
    jr z,mapper_pool_next
    ld a,(mapper_pool_count)
    cp MAPPER_POOL_MAX
    ret nc
    ld e,a
    ld d,0
    ld hl,mapper_pool
    add hl,de
    ld (hl),b
    inc a
    ld (mapper_pool_count),a
mapper_pool_next:
    ld a,b
    or a
    ret z
    dec b
    jr mapper_pool_scan

mapper_segment_is_process:
    ; B = candidate. Z when currently owned by DOS/program pages 0..3.
    ld a,(original_p0)
    cp b
    ret z
    ld a,(original_p1)
    cp b
    ret z
    ld a,(original_p2)
    cp b
    ret z
    ld a,(original_p3)
    cp b
    ret

mapper_alloc_user_primary:
    ld a,(mapper_pool_count)
    or a
    jr z,mapper_alloc_failed
    dec a
    ld (mapper_pool_count),a
    ld e,a
    ld d,0
    ld hl,mapper_pool
    add hl,de
    ld a,(hl)
    or a
    ret
mapper_alloc_failed:
    xor a
    scf
    ret

mapper_free_primary:
    ld b,a
    ld a,(mapper_pool_count)
    cp MAPPER_POOL_MAX
    ret nc
    ld e,a
    ld d,0
    ld hl,mapper_pool
    add hl,de
    ld (hl),b
    inc a
    ld (mapper_pool_count),a
    or a
    ret

map_p1:
    ld (mapped_p1),a
    out (PORT_MAPPER_P1),a
    ret
map_p2:
    ld (mapped_p2),a
    out (PORT_MAPPER_P2),a
    ret
restore_process_pages:
    ; PAGE3_WORKRAM is never visible while DOS, BIOS or UI code runs.
    ld a,(original_p3)
    out (PORT_MAPPER_P3),a
    ld a,(original_a8)
    out (PORT_PPI_A),a
    ld a,(original_p1)
    call map_p1
    ld a,(original_p2)
    call map_p2
    ret

map_scc_page2:
    ld a,(scc_slot)
map_primary_slot_page2:
    and 3
    rlca
    rlca
    rlca
    rlca
    ld b,a
    in a,(PORT_PPI_A)
    and 0xCF
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
    call mapper_alloc_user_primary
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
    call mapper_free_primary
    pop bc
    pop hl
    djnz free_hot_loop
    ret

cleanup:
    di
    call restore_refresh_rate
    ld a,(mapper_ready)
    or a
    jr z,cleanup_close_file
    call stop_and_mute
    ld a,(original_a8)
    out (PORT_PPI_A),a
    call restore_process_pages
    call free_hot_segments
    call free_template_segment
    call free_page3_workram_segment
    call free_mwk_segment
    call free_hpol_map_segment
    ; Mapper functions and cartridge muting are allowed to touch the visible
    ; page/slot state. Re-assert the original process mappings after the final
    ; free so the next package always starts from a clean DOS1 layout.
    call restore_process_pages
cleanup_close_file:
    call fcb_close_current
cleanup_done:
    call ui_reset_package_state
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
    ; Accept backward-compatible KSP 1.00 and 1.01 only.
    ld hl,(KSP_HEADER+6)
    ld a,h
    or a
    jr nz,header_bad
    ld a,l
    cp 2
    jr nc,header_bad
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
    xor a
    ld (dynamic_profile),a
    ld (page2_runtime_profile),a
    ld (page3_workram_profile),a
    ; ABI 1 supports DYNAMIC_PAGES, MWK_REQUIRED, PAGE2_RUNTIME and
    ; PAGE3_WORKRAM. Banked engines remain outside this constrained
    ; one-page standalone MSX-DOS1 implementation.
    ld hl,(ENGINE_ENTRY+2)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY)
    ld a,h
    or a
    jr nz,engine_profile_bad
    ld a,l
    and 0xE2                    ; reject BANKED_DATA and bits 5-7
    jr nz,engine_profile_bad
    ld a,l
    and 0x18                    ; 1.01-only memory-layout flags
    jr z,engine_minor_flags_ok
    ld a,(KSP_HEADER+6)
    cp 1
    jr nz,engine_profile_bad
engine_minor_flags_ok:
    ld a,l
    and 0x08
    jr z,engine_page2_flag_done
    ld a,1
    ld (page2_runtime_profile),a
engine_page2_flag_done:
    ld a,l
    and 0x10
    jr z,engine_page3_flag_done
    ld a,1
    ld (page3_workram_profile),a
engine_page3_flag_done:
    ld a,l
    and 1
    ld (dynamic_profile),a

    ; Supported hardware: PSG, SCC, SCC+, dual normal SCC, YM2413 and OPL4.
    ; Y8950, SN76489, Game Gear stereo and higher reserved bits are rejected.
    ld a,(ENGINE_ENTRY+4)
    and 0xA0
    jr nz,engine_profile_bad
    ld a,(ENGINE_ENTRY+5)
    or a
    jr nz,engine_profile_bad
    ld hl,(ENGINE_ENTRY+6)
    ld a,h
    or l
    jr nz,engine_profile_bad
    ; PAGE2_RUNTIME aliases writable mapper RAM into page 2 and therefore
    ; cannot coexist with SCC cartridge address space.
    ld a,(page2_runtime_profile)
    or a
    jr z,engine_page2_hardware_ok
    ld a,(ENGINE_ENTRY+4)
    and 0x0E
    jr nz,engine_profile_bad
engine_page2_hardware_ok:
    ; DUAL_SCC currently means two normal SCC devices, not two SCC+ devices.
    ld a,(ENGINE_ENTRY+4)
    and 0x0C
    cp 0x0C
    jr z,engine_profile_bad

    ld hl,(ENGINE_ENTRY+8)
    ld de,1
    or a
    sbc hl,de
    jr nz,engine_profile_bad
    ; Select 50/60 Hz VDP timing from this field, then use one VBlank per PLAY tick.
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
    ; Constrained MSX profile: one 16 KiB engine page at 4000h-7FFFh.
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

    ; Dynamic packages declare their original call target and a protected code
    ; prefix. The player relocates CALL operands generically into page 0.
    ld a,(dynamic_profile)
    or a
    jr z,engine_no_dynamic
    ld hl,(ENGINE_ENTRY+22)
    ld a,h
    or l
    jr z,engine_profile_bad
    ld hl,(ENGINE_ENTRY+24)
    ld de,0x4000
    or a
    sbc hl,de
    jr c,engine_profile_bad
    ld hl,(ENGINE_ENTRY+24)
    ld de,0x8000
    or a
    sbc hl,de
    jr nc,engine_profile_bad
    jr engine_dynamic_valid
engine_no_dynamic:
    ld hl,(ENGINE_ENTRY+22)
    ld a,h
    or l
    jr nz,engine_profile_bad
engine_dynamic_valid:
    ; No banked data in this runtime profile.
    ld a,(ENGINE_ENTRY+34)
    or a
    jr nz,engine_profile_bad
    ld a,(ENGINE_ENTRY+35)
    or a
    jr nz,engine_profile_bad
    ; Template is raw or one forward ZX0 stream and expands to exactly 16 KiB.
    ld a,(ENGINE_ENTRY+32)
    cp 2
    jr nc,engine_profile_bad
    ld (template_compression),a
    ld a,(ENGINE_ENTRY+39)
    or a
    jr nz,engine_profile_bad
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
    ; The complete map matrix is kept in one dedicated mapper segment.
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

    ; maps -> dedicated mapper segment, leaving 2200h-38FFh for the UI.
    call make_abs_maps_offset
    ld hl,(abs_offset_lo)
    ld a,(abs_offset_hi)
    ld de,(hpl_maps_packed)
    ld b,d
    ld c,e
    call stream_begin
    jr c,preload_bad
    ld a,(hpol_map_segment)
    call map_p2
    xor a
    ld (zx_mode),a
    ld hl,0x8000
    ld (linear_base),hl
    ld hl,(hpl_maps_raw)
    ld a,(hpl_maps_raw+2)
    call zx_set_output_size
    call zx_decode_stream
    jr c,preload_bad
    call restore_process_pages

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
    call zx_decode_stream
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
    call zx_decode_stream
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
    call stop_and_mute
    call restore_process_pages
    call upload_current_mwk
    jr c,install_bad
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
    call patch_engine_gateways
    jr c,install_bad
    call prepare_engine_page2
    call prepare_opl4_init
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

patch_engine_gateways:
    xor a
    ld (gateway_patch_flags),a
    ld hl,(ENGINE_ENTRY+24)
    ld de,(ENGINE_ENTRY+12)
    or a
    sbc hl,de
    jr c,patch_gateways_bad
    ld b,h
    ld c,l
    ld hl,(ENGINE_ENTRY+12)
patch_gateways_loop:
    ld a,b
    or c
    jr z,patch_gateways_validate
    ld a,(hl)
    cp 0xCD                    ; ABI gateways are invoked with CALL.
    jr nz,patch_gateways_next
    ld a,b
    or a
    jr nz,patch_gateways_have_operand
    ld a,c
    cp 3
    jr c,patch_gateways_validate
patch_gateways_have_operand:
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    push hl
    push bc

    ld a,(dynamic_profile)
    or a
    jr z,patch_gateways_dual
    push de
    ld hl,(ENGINE_ENTRY+22)
    or a
    sbc hl,de
    pop de
    jr nz,patch_gateways_dual
    pop bc
    pop hl
    ld (hl),DYNAMIC_GATEWAY >> 8
    dec hl
    ld (hl),DYNAMIC_GATEWAY & 0xFF
    ld a,(gateway_patch_flags)
    or 1
    ld (gateway_patch_flags),a
    inc hl
    jr patch_gateways_consumed

patch_gateways_dual:
    ld a,(ENGINE_ENTRY+4)
    and 0x08
    jr z,patch_gateways_no_match
    ld a,d
    cp 0xD9
    jr nz,patch_gateways_no_match
    ld a,e
    cp 0x00
    jr z,patch_gateway_a
    cp 0x04
    jr z,patch_gateway_b
    cp 0x08
    jr z,patch_gateway_ram
patch_gateways_no_match:
    pop bc
    pop hl
    jr patch_gateways_consumed
patch_gateway_a:
    ld de,dual_scc_select_a
    ld a,2
    jr patch_gateway_store
patch_gateway_b:
    ld de,dual_scc_select_b
    ld a,4
    jr patch_gateway_store
patch_gateway_ram:
    ld de,dual_scc_restore_ram
    ld a,8
patch_gateway_store:
    pop bc
    pop hl
    ld (hl),d
    dec hl
    ld (hl),e
    ld e,a
    ld a,(gateway_patch_flags)
    or e
    ld (gateway_patch_flags),a
    inc hl
patch_gateways_consumed:
    ; HL points at the high operand. Consume the complete three-byte CALL.
    inc hl
    dec bc
    dec bc
    dec bc
    jr patch_gateways_loop
patch_gateways_next:
    inc hl
    dec bc
    jr patch_gateways_loop

patch_gateways_validate:
    ld a,(dynamic_profile)
    or a
    jr z,patch_gateways_validate_dual
    ld a,(gateway_patch_flags)
    and 1
    jr z,patch_gateways_bad
patch_gateways_validate_dual:
    ld a,(ENGINE_ENTRY+4)
    and 0x08
    jr z,patch_gateways_ok
    ld a,(gateway_patch_flags)
    and 0x0E
    cp 0x0E
    jr nz,patch_gateways_bad
patch_gateways_ok:
    or a
    ret
patch_gateways_bad:
    scf
    ret

load_template_page:
    ld a,(template_cache_ready)
    or a
    jr z,decode_template_page
    ; Cached template is mapped in page 2 and copied into active page 1.
    ld a,(template_segment)
    call map_p2
    ld hl,0x8000
    ld de,0x4000
    ld bc,0x4000
    ldir
    ld a,(original_p2)
    call map_p2
    or a
    ret

decode_template_page:
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
    jp zx_decode_stream
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
    jp zx_decode_stream
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
    call zx_decode_stream
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
    jr z,sparse_done
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

    ; Destination end must not exceed the declared engine image.
    ld hl,(overlay_offset)
    ld de,(overlay_length)
    add hl,de
    jr c,sparse_bad
    ld (overlay_end),hl
    ld de,(ENGINE_ENTRY+14)
    inc de
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

    ; Dynamic switches may replace only replace_start..page_end.
    ld a,(dynamic_install_active)
    or a
    jr z,sparse_dynamic_range_ok
    ld hl,(overlay_offset)
    ld de,(ENGINE_ENTRY+12)
    add hl,de
    ld de,(ENGINE_ENTRY+24)
    or a
    sbc hl,de
    jr c,sparse_bad
sparse_dynamic_range_ok:
    ; Copy page-2 scratch bytes into the active engine destination.
    ld hl,(overlay_ptr)
    push hl
    ld de,(overlay_offset)
    ld hl,0x4000
    add hl,de
    ex de,hl
    pop hl
    ld bc,(overlay_length)
    ldir
    ld (overlay_ptr),hl
    ld hl,(overlay_end)
    ld (overlay_previous_end),hl
    jr sparse_record_loop
sparse_done:
    or a
    ret
sparse_bad:
    scf
    ret

apply_hybrid_page:
    ; Cache only this page's map row (position_count * 2 <= 512 bytes).
    ld hl,(current_page)
    ld de,(hpl_position_count)
    call mul16_real
    add hl,hl
    ld de,0x8000
    add hl,de
    push hl
    ld a,(hpol_map_segment)
    call map_p2
    pop hl
    ld de,MAP_ROW_BUFFER
    ld bc,(hpl_position_count)
    sla c
    rl b
    ldir
    ld a,(original_p2)
    call map_p2
    ld hl,MAP_ROW_BUFFER
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
    call zx_decode_stream
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
    call restore_process_pages
    call ui_clear_bios_keyboard_buffer
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
    ld a,(page3_workram_profile)
    or a
    jr z,stop_call
    ld a,(engine_p3_segment)
    out (0xFF),a
stop_call:
    call 0
    di
    ld a,(page3_workram_profile)
    or a
    ret z
    ld a,(original_p3)
    out (0xFF),a
    ret

stop_and_mute:
    call stop_engine
    call hard_mute_audio
    ret

prepare_engine_page2:
    ld a,(page2_runtime_profile)
    or a
    jr z,prepare_engine_page2_hardware
    ; Alias the active page-1 mapper segment into page 2. This supplies
    ; the KSP 1.01 writable 8000h-BFFFh runtime image before INIT and PLAY.
    ld a,(mapped_p1)
    jp map_p2
prepare_engine_page2_hardware:
    ld a,(ENGINE_ENTRY+4)
    and 0x08
    jp nz,map_ram_page2
    ld a,(ENGINE_ENTRY+4)
    and 0x06
    ret z
    jp map_scc_page2

hard_mute_audio:
    ; Recreate a deterministic hardware state before INIT and on exit.
    push af
    push bc
    push de
    push hl

    ; Clear PSG tone/noise periods (R0-R6).
    ld d,0
    ld b,7
hard_reset_psg_0_6:
    ld a,d
    out (PORT_PSG_ADDR),a
    xor a
    out (PORT_PSG_DATA),a
    inc d
    djnz hard_reset_psg_0_6

    ; Disable all tone/noise outputs while preserving MSX I/O direction bits.
    ld a,7
    out (PORT_PSG_ADDR),a
    ld a,0xBF
    out (PORT_PSG_DATA),a

    ; Clear PSG volumes and envelope registers (R8-R13).
    ld d,8
    ld b,6
hard_reset_psg_8_13:
    ld a,d
    out (PORT_PSG_ADDR),a
    xor a
    out (PORT_PSG_DATA),a
    inc d
    djnz hard_reset_psg_8_13

    ld a,(engine_ready)
    or a
    jr z,hard_mute_done
    ld a,(ENGINE_ENTRY+4)
    and 0x10
    call nz,hard_reset_ym2413
    ld a,(ENGINE_ENTRY+4)
    and 0x40
    call nz,hard_reset_opl4

    ld a,(ENGINE_ENTRY+4)
    and 0x08
    jr z,hard_reset_single_scc
    call dual_scc_select_a
    call hard_reset_normal_scc_selected
    call dual_scc_select_b
    call hard_reset_normal_scc_selected
    call map_ram_page2
    jr hard_mute_done

hard_reset_single_scc:
    ld a,(ENGINE_ENTRY+4)
    and 0x06
    jr z,hard_mute_done
    call map_scc_page2
    ld a,(ENGINE_ENTRY+4)
    and 0x04
    jr nz,hard_reset_sccplus_selected
    call hard_reset_normal_scc_selected
    jr hard_mute_done

hard_reset_normal_scc_selected:
    ld a,0x3F
    ld (0x9000),a
    xor a
    ld hl,0x9800
    ld b,0x90
hard_reset_normal_scc_loop:
    ld (hl),a
    inc hl
    djnz hard_reset_normal_scc_loop
    ret

hard_reset_sccplus_selected:
    ld a,0x20
    ld (0xBFFF),a
    ld a,0x80
    ld (0xB000),a
    xor a
    ld hl,0xB800
    ld b,0x00
hard_reset_sccplus_loop:
    ld (hl),a
    inc hl
    djnz hard_reset_sccplus_loop
    jr hard_mute_done

; Key off MSX-MUSIC before a blocking DOS seek/read. SCC engines are
; disconnected when page 2 is restored for DOS, but YM2413 is port-mapped and
; would otherwise hold the last note for the complete disk-access interval.
; Do not alter instrument/volume registers here: live dynamic-page playback can
; continue naturally as soon as the engine writes its next key-on event.
mute_fmpac_before_disk_io:
    push af
    push bc
    push de
    ld a,(engine_running)
    or a
    jr z,mute_fmpac_disk_done
    ld a,(engine_ready)
    or a
    jr z,mute_fmpac_disk_done
    ld a,(ENGINE_ENTRY+4)
    and 0x10
    jr z,mute_fmpac_disk_done

    ; Disable rhythm mode and all five rhythm key bits.
    ld d,0x0E
    xor a
    call write_ym2413_register

    ; Key off all nine melodic channels. F-number/instrument/volume state is
    ; deliberately left intact so the next engine event can resume cleanly.
    ld d,0x20
    ld b,9
mute_fmpac_disk_keyoff_loop:
    xor a
    call write_ym2413_register
    inc d
    djnz mute_fmpac_disk_keyoff_loop
mute_fmpac_disk_done:
    pop de
    pop bc
    pop af
    ret

write_ym2413_register:
    ; D = register, A = value. Preserve the value across the address write.
    ld e,a
    ld a,d
    out (PORT_FM_ADDR),a
    nop
    nop
    ld a,e
    out (PORT_FM_DATA),a
    push bc
    ld b,32
write_ym2413_wait:
    djnz write_ym2413_wait
    pop bc
    ret

hard_reset_ym2413:
    ; Clear user instrument, rhythm, frequency/key and volume registers.
    ld d,0
hard_reset_ym2413_loop:
    xor a
    call write_ym2413_register
    inc d
    ld a,d
    cp 0x39
    jr c,hard_reset_ym2413_loop
    ret
hard_mute_done:
    pop hl
    pop de
    pop bc
    pop af
    ret

call_init:
    ld hl,(ENGINE_ENTRY+16)
    ld (init_call+1),hl
    ld a,(page3_workram_profile)
    or a
    jr z,call_init_parameters
    ld a,(engine_p3_segment)
    out (0xFF),a
call_init_parameters:
    ld hl,(current_song_id)
    ld a,l
    ld bc,0
    ld de,0
init_call:
    call 0
    di
    ld a,(page3_workram_profile)
    or a
    ret z
    ld a,(original_p3)
    out (0xFF),a
    ret

call_play:
    ld hl,(ENGINE_ENTRY+18)
    ld (play_call+1),hl
    ld a,(page3_workram_profile)
    or a
    jr z,play_call
    ld a,(engine_p3_segment)
    out (0xFF),a
play_call:
    call 0
    di
    ld a,(page3_workram_profile)
    or a
    ret z
    ld a,(original_p3)
    out (0xFF),a
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
    ; A:HL absolute offset, DE:BC packed size (profile streams are <64 KiB).
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
    ld (stream_vdp_guard),a
    ld a,(file_cache_ready)
    or a
    jr z,stream_begin_disk
    ld a,1
    ld (stream_source),a
    ld (stream_vdp_guard),a
    call vdp_irq_begin
    ld hl,(stream_offset_lo)
    ld de,WARM_VRAM_BASE
    add hl,de
    ld a,(stream_offset_hi)
    adc a,0
    call vram_set_read_address
    or a
    ret
stream_begin_disk:
    call mute_fmpac_before_disk_io
    xor a
    ld (stream_source),a
    ld hl,(stream_offset_lo)
    ld (tmp_offset_lo),hl
    ld a,(stream_offset_hi)
    ld (tmp_offset_hi),a
    call fcb_set_random_offset
    or a
    ret
stream_begin_bad:
    scf
    ret

stream_end:
    ld a,(stream_vdp_guard)
    or a
    ret z
    xor a
    ld (stream_vdp_guard),a
    call vdp_irq_end
    ret

zx_decode_stream:
    call zx_decode
    push af
    call stream_end
    pop af
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
    ld de,IO_BUFFER
    ld b,h
    ld c,l
    call fcb_read_current
    jr nz,refill_error
    ld hl,(refill_count)
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
    ld a,(stream_source)
    or a
    jr z,zx_read_byte_disk
    ld hl,(stream_remaining)
    ld a,(stream_remaining+2)
    or h
    or l
    jr z,zx_read_cache_eof
    in a,(PORT_VDP_DATA)
    ld (zx_last_byte),a
    ld hl,(stream_remaining)
    ld a,h
    or l
    jr nz,zx_read_cache_low
    ld hl,0xFFFF
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
    jr nz,zx_read_have
    ; ZX0 keeps gamma values and copy lengths in BC, and callers may also
    ; have live DE/HL values. FCB disk reads and mapper callbacks are
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
    add a,0x40
    ld h,a
    pop af
    ld (hl),a
    out (PORT_VDP_DATA),a
    jr zx_write_account
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
    add a,0x40
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
; VDP refresh-rate control
; ---------------------------------------------------------------------------
configure_engine_refresh:
    ; KSP tick_hz is 50 or 60 after validation. Preserve every original R#9
    ; bit, then change only bit 1 (0 = 60 Hz, 1 = 50 Hz).
    ld a,(RG9SAV)
    ld (original_vdp_r9),a
    ld b,a
    ld hl,(ENGINE_ENTRY+10)
    ld a,l
    cp 50
    ld a,b
    jr nz,configure_refresh_60
    or 0x02
    jr configure_refresh_write
configure_refresh_60:
    and 0xFD
configure_refresh_write:
    call write_vdp_r9
    ld a,1
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
    ; A = complete R#9 value. Keep the BIOS shadow and hardware synchronized.
    ld b,a
    call vdp_irq_begin
    ld a,b
    ld (RG9SAV),a
    out (PORT_VDP_CTRL),a
    ld a,0x89
    out (PORT_VDP_CTRL),a
    jp vdp_irq_end

; ---------------------------------------------------------------------------
; VDP helpers
; ---------------------------------------------------------------------------
vdp_irq_begin:
    ; Preserve IFF2 while a sequential VDP transfer owns ports 98h/99h.
    ; VBlank BIOS handlers may otherwise replace R14 and the current address.
    ld a,i
    jp po,vdp_irq_was_disabled
    ld a,1
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
file_open:              db 0
file_fcb:               ds 37,0
fcb_request_count:      dw 0
scc_slot:               db 2
scc_slot_b:             db 1
cmd_remaining:          db 0
selected_track:         dw 0
current_page:           dw 0
current_song_id:        dw 0
space_previous:         db 1

mapper_ready:           db 0
engine_ready:           db 0
engine_running:         db 0
decode_stage:           db 0
hybrid_ready:          db 0
file_cache_ready:       db 0
template_cache_ready:   db 0
template_segment_allocated: db 0
template_segment:       db 0
dynamic_profile:        db 0
page2_runtime_profile:  db 0
page3_workram_profile:  db 0
engine_p3_segment_allocated: db 0
engine_p3_segment:      db 0
dynamic_page:           dw 0
dynamic_result:         db 0
dynamic_saved_p3:      db 0
dynamic_install_active: db 0
gateway_patch_flags:    db 0
hardware_error_code:    db 0
stream_source:          db 0
stream_vdp_guard:       db 0
vdp_saved_iff:          db 0
refresh_saved:          db 0
original_vdp_r9:        db 0
template_compression:   db 0
mapper_segment_mask:    db 0
mapper_pool_count:      db 0
mapper_pool:            ds MAPPER_POOL_MAX,0
probe_original_p1:      db 0
probe_base_byte:        db 0
probe_marker:           db 0
original_p0:            db 0
original_p1:            db 0
original_p2:            db 0
original_p3:            db 0
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
hpol_map_segment:       db 0
hpol_map_allocated:     db 0
menu_launch:             db 0
ui_error_code:           db 0

tmp_offset_lo:          dw 0
mul_multiplicand:       db 0,0,0
mul_multiplier:         dw 0
mul_result:             db 0,0,0
tmp_offset_hi:          db 0
file_cache_size:        db 0,0,0
cache_remaining:        db 0,0,0
cache_written:          db 0,0,0
cache_chunk:            dw 0
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
filename:               ds 16,0

msg_format: db 'Error: invalid or unsupported KSP 1.x file.',13,10
msg_format_end:
msg_profile: db 'Error: unsupported hardware or engine layout.',13,10
msg_profile_end:
msg_mapper: db 'Error: DOS1 standalone mode needs a 128K+ memory mapper.',13,10
msg_mapper_end:
msg_memory: db 'Error: insufficient mapper segments.',13,10
msg_memory_end:
msg_file: db 'Error: file access failed.',13,10
msg_file_end:
msg_track: db 'Error: track/page is invalid.',13,10
msg_track_end:
msg_decode: db 'Error: ZX0 or page reconstruction failed.',13,10
msg_decode_end:
msg_track_prefix: db 'Track '
msg_track_prefix_end:
msg_colon: db ': '
msg_colon_end:
msg_newline: db 13,10
msg_newline_end:
msg_banner: db 'KSP1PLAY 0.20.0 - MSX-DOS1 standalone',13,10
msg_banner_end:
msg_usage: db 'Usage: KSP1PLAY [8.3-file.ksp [track] [SCC-A 0-3] [SCC-B 0-3]]',13,10
msg_usage_end:
msg_hardware: db 'Error: MoonSound/OPL4 not detected.',13,10
msg_hardware_end:
msg_scc_slots: db 'Error: dual SCC slots must be different.',13,10
msg_scc_slots_end:

; Incremental Screen 5 navigation helpers live in the remaining resident-core
; gap so the graphical module stays below the fixed HPOL caches at 3500h.
ui_menu_store_selection:
    ; A = new file index. Preserve the static frame and update only the
    ; affected rows unless the visible directory window has to scroll.
    ld d,a
    ld a,(ui_menu_selected)
    ld e,a
    ld a,(ui_menu_top)
    ld c,a
    ld a,d
    ld (ui_menu_selected),a
    call ui_adjust_menu_top
    ld a,(ui_menu_top)
    cp c
    jr nz,ui_menu_store_redraw_page
    ld a,e
    call ui_draw_menu_index
    ld a,(ui_menu_selected)
    jp ui_draw_menu_index
ui_menu_store_redraw_page:
    jp ui_draw_menu_rows

; A = global package index. Redraw its row only when currently visible.
ui_draw_menu_index:
    ld c,a
    ld a,(ui_menu_top)
    ld e,a
    ld a,c
    sub e
    ret c
    cp UI_VISIBLE_ROWS
    ret nc
    add a,4
    ld (ui_draw_row),a
    ld a,c
    call ui_name_pointer
    ld a,(ui_menu_selected)
    cp c
    ld b,7
    jr nz,ui_draw_menu_index_colour_ready
    ld b,15
ui_draw_menu_index_colour_ready:
    ld a,(ui_draw_row)
    jp ui_text_line

ui_remember_player_selection:
    ld hl,(selected_track)
    ld (ui_previous_track),hl
    ld hl,(ui_track_top)
    ld (ui_previous_top),hl
    ret

; Track installation may be expensive, but it must not be followed by a full
; SCREEN 5 repaint. Keep the package/engine frame intact. Redraw the selected
; title and two list rows when the viewport is unchanged; redraw only the
; track pane when it scrolls.
ui_update_player_selection:
    call restore_process_pages
    call ui_adjust_track_top
    ld hl,(ui_track_top)
    ld de,(ui_previous_top)
    or a
    sbc hl,de
    jr nz,ui_update_player_page
    call ui_draw_selected_track_title
    ld hl,(ui_previous_track)
    ld b,7
    call ui_draw_player_track_index
    ld hl,(selected_track)
    ld b,15
    call ui_draw_player_track_index
    call prepare_engine_page2
    ret
ui_update_player_page:
    call ui_ensure_track_cache
    call ui_draw_selected_track_title
    ld a,9
    ld b,UI_PLAYER_TRACK_ROWS
    call ui_draw_cached_tracks
    call prepare_engine_page2
    ret


program_end:

 ; ---------------------------------------------------------------------------
; Dynamic sparse-page callback workspace and dual-SCC gateways
; ---------------------------------------------------------------------------
; This lives in POS_BUFFER, which is used only by the mutually-exclusive HPOL
; profile. Gateway CALL operands are relocated generically from the addresses
; declared by the package into this resident page-0 code.
org DYNAMIC_GATEWAY
    ld (dynamic_page),hl
    ; A dynamic callback may be entered while PAGE3_WORKRAM is mapped.
    ; DOS/file reconstruction needs the process page, but the engine must
    ; receive the exact same page-3 segment again before the callback RET.
    in a,(0xFF)
    ld (dynamic_saved_p3),a
    ld a,i
    push af
    di
    push bc
    push de
    push hl
    db 0xDD,0xE5                 ; PUSH IX
    db 0xFD,0xE5                 ; PUSH IY
    exx
    push bc
    push de
    push hl
    exx
    ex af,af'
    push af
    ex af,af'

    call dynamic_install_page
    ld a,0
    adc a,0
    ld (dynamic_result),a
    ld a,(dynamic_saved_p3)
    out (0xFF),a

    ex af,af'
    pop af
    ex af,af'
    exx
    pop hl
    pop de
    pop bc
    exx
    db 0xFD,0xE1                 ; POP IY
    db 0xDD,0xE1                 ; POP IX
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
    ld hl,(dynamic_page)
    ld de,(ENGINE_ENTRY+28)
    or a
    sbc hl,de
    jr nc,dynamic_install_bad
    add hl,de
    ld de,(ENGINE_ENTRY+26)
    add hl,de
    jr c,dynamic_install_bad
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
    jr nz,dynamic_install_bad

    ; This player currently owns engine zero and supports bounded sparse pages
    ; during live switching. Other encodings still work for initial loading.
    ld hl,(PAGE_ENTRY)
    ld a,h
    or l
    jr nz,dynamic_install_bad
    ld a,(PAGE_ENTRY+2)
    or a
    jr nz,dynamic_install_bad
    ld a,(PAGE_ENTRY+3)
    cp 2
    jr nc,dynamic_install_bad
    ld hl,(PAGE_ENTRY+4)
    ld a,h
    or l
    jr nz,dynamic_install_bad
    ld hl,(PAGE_ENTRY+14)
    ld a,h
    or l
    jr nz,dynamic_install_bad
    ld hl,(PAGE_ENTRY+18)
    ld a,h
    or l
    jr nz,dynamic_install_bad
    ld hl,(PAGE_ENTRY+16)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,dynamic_install_bad
    ld a,(template_cache_ready)
    or a
    jr z,dynamic_install_bad

    ; Restore only replace_start..7FFFh from the pristine template.
    ld hl,(ENGINE_ENTRY+24)
    ld de,(ENGINE_ENTRY+12)
    or a
    sbc hl,de
    push hl
    ld a,(template_segment)
    call map_p2
    pop de
    ld hl,0x8000
    add hl,de
    ld de,(ENGINE_ENTRY+24)
    push hl
    ld hl,0x8000
    or a
    sbc hl,de
    ld b,h
    ld c,l
    pop hl
    ldir
    ld a,(original_p2)
    call map_p2

    ld a,1
    ld (dynamic_install_active),a
    call apply_sparse_page
    push af
    xor a
    ld (dynamic_install_active),a
    call prepare_engine_page2
    pop af
    ret

dynamic_install_bad:
    xor a
    ld (dynamic_install_active),a
    call prepare_engine_page2
    scf
    ret

; ABI-1 dual-SCC CALL tokens D900h/D904h/D908h are relocated into these
; page-0 handlers. The callbacks preserve all normal registers. Page 3
; remains on the DOS mapping except during declared PAGE3_WORKRAM engine calls.
dual_scc_select_a:
    push af
    push bc
    ld a,(scc_slot)
    jr dual_scc_select_common
dual_scc_select_b:
    push af
    push bc
    ld a,(scc_slot_b)
dual_scc_select_common:
    call map_primary_slot_page2
    ld a,0x3F
    ld (0x9000),a
    pop bc
    pop af
    ret

dual_scc_restore_ram:
    push af
    push bc
    push de
    push hl
    db 0xDD,0xE5                 ; PUSH IX
    db 0xFD,0xE5                 ; PUSH IY
    call map_ram_page2
    db 0xFD,0xE1                 ; POP IY
    db 0xDD,0xE1                 ; POP IX
    pop hl
    pop de
    pop bc
    pop af
    ret

map_ram_page2:
    in a,(PORT_PPI_A)
    and 0xCF
    ld b,a
    ld a,(original_a8)
    and 0x30
    or b
    out (PORT_PPI_A),a
    ld a,(original_p2)
    jp map_p2

dynamic_gateway_end:

; DOS1-only 8.3 FCB builder uses the otherwise idle gateway/UI gap.
fcb_prepare_filename:
    ; Convert filename ASCIIZ to a DOS1 8.3 FCB. Paths are intentionally absent.
    ld hl,file_fcb
    xor a
    ld (hl),a
    ld de,file_fcb+1
    ld b,11
    ld a,' '
fcb_clear_name:
    ld (de),a
    inc de
    djnz fcb_clear_name
    xor a
    ld b,25
fcb_clear_tail:
    ld (de),a
    inc de
    djnz fcb_clear_tail

    ld hl,filename
    ld a,(hl)
    or a
    jr z,fcb_prepare_bad
    inc hl
    ld a,(hl)
    cp ':'
    dec hl
    jr nz,fcb_prepare_name
    ld a,(hl)
    and 0xDF
    sub 'A'-1
    cp 1
    jr c,fcb_prepare_bad
    cp 9
    jr nc,fcb_prepare_bad
    ld (file_fcb),a
    inc hl
    inc hl
fcb_prepare_name:
    ld de,file_fcb+1
    ld b,8
fcb_prepare_name_loop:
    ld a,(hl)
    or a
    jr z,fcb_prepare_ok
    cp '.'
    jr z,fcb_prepare_ext_start
    cp ':'
    jr z,fcb_prepare_bad
    cp '/'
    jr z,fcb_prepare_bad
    cp 0x5C
    jr z,fcb_prepare_bad
    ld c,a
    ld a,b
    or a
    jr z,fcb_prepare_bad
    ld a,c
    cp 'a'
    jr c,fcb_prepare_name_store
    cp 'z'+1
    jr nc,fcb_prepare_name_store
    and 0xDF
fcb_prepare_name_store:
    ld (de),a
    inc de
    inc hl
    dec b
    jr fcb_prepare_name_loop
fcb_prepare_ext_start:
    inc hl
    ld de,file_fcb+9
    ld b,3
fcb_prepare_ext_loop:
    ld a,(hl)
    or a
    jr z,fcb_prepare_ok
    cp '.'
    jr z,fcb_prepare_bad
    cp ':'
    jr z,fcb_prepare_bad
    cp '/'
    jr z,fcb_prepare_bad
    cp 0x5C
    jr z,fcb_prepare_bad
    ld c,a
    ld a,b
    or a
    jr z,fcb_prepare_bad
    ld a,c
    cp 'a'
    jr c,fcb_prepare_ext_store
    cp 'z'+1
    jr nc,fcb_prepare_ext_store
    and 0xDF
fcb_prepare_ext_store:
    ld (de),a
    inc de
    inc hl
    dec b
    jr fcb_prepare_ext_loop
fcb_prepare_ok:
    or a
    ret
fcb_prepare_bad:
    scf
    ret

dos1_overlay_end:


; ---------------------------------------------------------------------------
; Screen 5 graphical shell and HPOL map-segment support
; ---------------------------------------------------------------------------
org UI_MODULE

BIOS_CALSLT     equ 0x001C
BIOS_INITXT     equ 0x006C
EXPTBL          equ 0xFCC1
PUTPNT          equ 0xF3F8
GETPNT          equ 0xF3FA
RG0SAV          equ 0xF3DF
RG1SAV          equ 0xF3E0
RG2SAV          equ 0xF3E1
RG3SAV          equ 0xF3E2
RG4SAV          equ 0xF3E3
RG5SAV          equ 0xF3E4
RG6SAV          equ 0xF3E5
RG7SAV          equ 0xF3E6
RG8SAV          equ 0xFFE7
RG18SA          equ 0xFFF1
RG23SA          equ 0xFFF6
LINL40          equ 0xF3AE
LINLEN          equ 0xF3B0
CRTCNT          equ 0xF3B1
CSRY            equ 0xF3DC
CSRX            equ 0xF3DD

UI_VISIBLE_ROWS equ 18
UI_TRACK_ROWS   equ 15
UI_PLAYER_TRACK_ROWS equ 13
UI_TEXT_COLS    equ 64
UI_TRACK_CACHE_COLS equ 48
UI_MAX_FILES    equ 40

ui_application:
    call ui_screen5_init
    ld a,(filename)
    or a
    jr z,ui_menu_loop
    xor a
    ld (menu_launch),a
    call ui_load_pack
    jr c,ui_load_error
    jr ui_play_screen

ui_menu_loop:
    call ui_menu
    jr c,ui_final_exit
    ld a,1
    ld (menu_launch),a
    call ui_load_pack
    jr c,ui_load_error
    call ui_clear_bios_keyboard_buffer
    call ui_track_menu
    jr c,ui_track_menu_cancel
    call ui_clear_bios_keyboard_buffer
    call ui_install_selected_track
    jr c,ui_load_error
    jr ui_play_screen
ui_track_menu_cancel:
    call cleanup
    call ui_wait_keys_released
    call ui_clear_bios_keyboard_buffer
    call ui_screen5_init
    jr ui_menu_loop
ui_play_screen:
    call ui_draw_player_screen
ui_play_loop:
    ei
    halt
    di
    call call_play
    call ui_poll_action
    cp 1
    jr z,ui_back_to_menu
    cp 3
    jr z,ui_previous_action
    cp 5
    jr z,ui_previous_action
    cp 4
    jr z,ui_next_action
    cp 6
    jr z,ui_next_action
    cp 7
    jr z,ui_next_action
    jr ui_play_loop
ui_next_action:
    call ui_remember_player_selection
    call next_track
    jr c,ui_runtime_error
    call ui_update_player_selection
    jr ui_play_loop
ui_previous_action:
    call ui_remember_player_selection
    call previous_track
    jr c,ui_runtime_error
    call ui_update_player_selection
    jr ui_play_loop
ui_back_to_menu:
    call cleanup
    call ui_wait_keys_released
    call ui_clear_bios_keyboard_buffer
    call ui_screen5_init
    jr ui_menu_loop
ui_runtime_error:
    ld a,7
    jr ui_load_error_code
ui_load_error:
    ld a,(ui_error_code)
ui_load_error_code:
    push af
    call cleanup
    call ui_wait_keys_released
    call ui_clear_bios_keyboard_buffer
    call ui_screen5_init
    pop af
    call ui_show_error
    jr ui_menu_loop
ui_final_exit:
    call cleanup
    call ui_wait_keys_released
    call ui_restore_screen0
    call ui_clear_bios_keyboard_buffer
    xor a
    ld (mapper_ready),a
    ld c,DOS_TERM0
    call BDOS
    ret

; Open and prepare the filename selected by the menu or supplied on the CLI.
ui_load_pack:
    ei
    xor a
    ld (ui_error_code),a
    ld (engine_ready),a
    ld (engine_running),a
    ld (hybrid_ready),a
    ld (file_cache_ready),a
    ld (template_cache_ready),a
    ld (refresh_saved),a
    call fcb_open_current
    jr c,ui_load_file_bad
    xor a
    ld hl,0
    ld de,KSP_HEADER
    ld bc,80
    call read_at
    jr nz,ui_load_file_bad
    call validate_header
    jr c,ui_load_format_bad
    ld hl,(KSP_HEADER+0x24)
    ld a,h
    or l
    jr z,ui_load_track_bad
    call load_engine_zero
    jr c,ui_load_format_bad
    call validate_engine_profile
    jr c,ui_load_profile_bad
    call validate_required_hardware
    jr c,ui_load_hardware_bad
    call allocate_page3_workram_segment
    jr c,ui_load_memory_bad
    call configure_engine_refresh
    ld a,1
    ld (engine_ready),a
    call find_hpol_resource
    jr c,ui_load_sparse
    call load_hpl_header
    jr c,ui_load_format_bad
    call allocate_hpol_map_segment
    jr c,ui_load_memory_bad
    call allocate_hot_segments
    jr c,ui_load_memory_bad
    ld a,4
    ld (decode_stage),a
    call preload_hybrid_pool
    jr c,ui_load_decode_bad
    ld a,1
    ld (hybrid_ready),a
    jr ui_load_profile_ready
ui_load_sparse:
    call preload_file_cache
    call allocate_template_segment
    jr c,ui_load_memory_bad
    ld a,1
    ld (decode_stage),a
    call preload_template_page
    jr c,ui_load_decode_bad
ui_load_profile_ready:
    ld a,(menu_launch)
    or a
    jr z,ui_load_track_selected
    ld hl,(KSP_HEADER+0x38)
    ld (selected_track),hl
    or a
    ret
ui_load_track_selected:
    call ui_install_selected_track
    ret

ui_install_selected_track:
    ld hl,(selected_track)
    call select_track
    jr c,ui_load_track_bad
    call install_current_track
    jr c,ui_load_decode_bad
    or a
    ret
ui_load_file_bad:
    ld a,1
    jr ui_load_fail
ui_load_format_bad:
    ld a,2
    jr ui_load_fail
ui_load_profile_bad:
    ld a,3
    jr ui_load_fail
ui_load_hardware_bad:
    ld a,4
    jr ui_load_fail
ui_load_memory_bad:
    ld a,5
    jr ui_load_fail
ui_load_track_bad:
    ld a,6
    jr ui_load_fail
ui_load_decode_bad:
    ld a,7
ui_load_fail:
    ld (ui_error_code),a
    scf
    ret

allocate_hpol_map_segment:
    call mapper_alloc_user_primary
    ret c
    ld (hpol_map_segment),a
    ld a,1
    ld (hpol_map_allocated),a
    or a
    ret
free_hpol_map_segment:
    ld a,(hpol_map_allocated)
    or a
    ret z
    ld a,(hpol_map_segment)
    call mapper_free_primary
    xor a
    ld (hpol_map_allocated),a
    ret

previous_track:
    di
    call restore_process_pages
    call ui_clear_bios_keyboard_buffer
    ld hl,(selected_track)
    ld a,h
    or l
    jr nz,previous_track_dec
    ld hl,(KSP_HEADER+0x24)
    dec hl
    jr previous_track_select
previous_track_dec:
    dec hl
previous_track_select:
    call select_track
    ret c
    call install_current_track
    ret

; --------------------------- Track selector ------------------------------
; The visible title rows are cached in ui_file_names while a package is open.
; Returning to the package menu rescans the directory and rebuilds that buffer.
ui_track_menu:
    ld hl,(selected_track)
    ld de,(KSP_HEADER+0x24)
    push hl
    or a
    sbc hl,de
    pop hl
    jr c,ui_track_menu_index_ok
    ld hl,0
    ld (selected_track),hl
ui_track_menu_index_ok:
    ld hl,0xFFFF
    ld (ui_track_cache_top),hl
    call ui_adjust_track_top
    call ui_draw_track_menu
    call ui_capture_keys
ui_track_menu_wait:
    ei
    halt
    di
    call ui_poll_action
    or a
    jr z,ui_track_menu_wait
    cp 1
    jr z,ui_track_menu_cancel_select
    cp 2
    jr z,ui_track_menu_choose
    cp 7
    jr z,ui_track_menu_choose
    cp 3
    jr z,ui_track_menu_up
    cp 4
    jr z,ui_track_menu_down
    cp 5
    jr z,ui_track_menu_page_up
    cp 6
    jr z,ui_track_menu_page_down
    jr ui_track_menu_wait
ui_track_menu_up:
    ld hl,(selected_track)
    ld a,h
    or l
    jr nz,ui_track_menu_up_dec
    ld hl,(KSP_HEADER+0x24)
    dec hl
    jr ui_track_menu_store
ui_track_menu_up_dec:
    dec hl
    jr ui_track_menu_store
ui_track_menu_down:
    ld hl,(selected_track)
    inc hl
    push hl
    ld de,(KSP_HEADER+0x24)
    or a
    sbc hl,de
    pop hl
    jr c,ui_track_menu_store
    ld hl,0
    jr ui_track_menu_store
ui_track_menu_page_up:
    ld hl,(selected_track)
    ld de,UI_TRACK_ROWS
    or a
    sbc hl,de
    jr nc,ui_track_menu_store
    ld hl,0
    jr ui_track_menu_store
ui_track_menu_page_down:
    ld hl,(selected_track)
    ld de,UI_TRACK_ROWS
    add hl,de
    push hl
    ld de,(KSP_HEADER+0x24)
    or a
    sbc hl,de
    pop hl
    jr c,ui_track_menu_store
    ld hl,(KSP_HEADER+0x24)
    dec hl
ui_track_menu_store:
    ; Keep the static package information on screen. If the selection remains
    ; in the current window, repaint only the old/new title rows. Scrolling
    ; repaints only the title pane, never the complete SCREEN 5 page.
    ld de,(selected_track)
    push de
    ld de,(ui_track_top)
    push de
    ld (selected_track),hl
    call ui_adjust_track_top
    pop de
    ld hl,(ui_track_top)
    or a
    sbc hl,de
    jr nz,ui_track_menu_redraw_page
    pop hl
    call ui_redraw_track_selection
    jr ui_track_menu_wait
ui_track_menu_redraw_page:
    pop hl
    call ui_redraw_track_page
    jr ui_track_menu_wait
ui_track_menu_choose:
    or a
    ret
ui_track_menu_cancel_select:
    scf
    ret

; Keep the active track one row above the bottom of the 13-row playback
; pane whenever a following track exists. The 15-row selector uses the same
; viewport, so it naturally shows up to three following tracks.
ui_adjust_track_top:
    ld hl,(selected_track)
    ld de,(ui_track_top)
    or a
    sbc hl,de
    jr c,ui_track_top_to_selected
    ld de,UI_PLAYER_TRACK_ROWS-1
    or a
    sbc hl,de
    ret c
    ld hl,(selected_track)
    ld de,UI_PLAYER_TRACK_ROWS-2
    or a
    sbc hl,de
ui_track_top_to_selected:
    ld (ui_track_top),hl
    ret

ui_draw_track_menu:
    call restore_process_pages
    call ui_clear_screen
    ld a,0
    ld b,15
    ld hl,filename
    call ui_text_line
    ld hl,(ENGINE_ENTRY+52)
    ld a,(ENGINE_ENTRY+54)
    call ui_read_ksp_string
    ld a,1
    ld b,7
    ld hl,ui_string_buffer
    call ui_text_line
    call ui_build_hardware_line
    ld a,2
    ld b,11
    ld hl,ui_line_buffer
    call ui_text_line
    call ui_build_track_select_line
    ld a,4
    ld b,15
    ld hl,ui_line_buffer
    call ui_text_line
    call ui_ensure_track_cache
    ld a,7
    ld b,UI_TRACK_ROWS
    call ui_draw_cached_tracks
    ld a,23
    ld b,7
    ld hl,ui_track_select_help
    call ui_text_line
    ld a,25
    ld b,8
    ld hl,ui_track_select_escape
    call ui_text_line
    ret


ui_redraw_track_heading:
    call ui_build_track_select_line
    ld a,4
    ld b,15
    ld hl,ui_line_buffer
    jp ui_text_line

; HL = previous global track index. Repaint only the two affected rows.
ui_redraw_track_selection:
    push hl
    call ui_redraw_track_heading
    pop hl
    ld b,7
    call ui_draw_track_index
    ld hl,(selected_track)
    ld b,15
    jp ui_draw_track_index

; Repaint the visible title pane after its top index changes.
ui_redraw_track_page:
    call ui_redraw_track_heading
    call ui_ensure_track_cache
    ld a,7
    ld b,UI_TRACK_ROWS
    jp ui_draw_cached_tracks

; HL = global track index, B = colour. The current selection gets a marker.
ui_draw_track_index:
    ld c,7
    ld d,UI_TRACK_ROWS
    jr ui_draw_track_index_common
ui_draw_player_track_index:
    ld c,9
    ld d,UI_PLAYER_TRACK_ROWS
ui_draw_track_index_common:
    push de
    push bc
    ld de,(ui_track_top)
    or a
    sbc hl,de
    pop bc
    pop de
    ret c
    ld a,h
    or a
    ret nz
    ld a,l
    cp d
    ret nc
    push af
    push bc
    call ui_track_cache_pointer
    pop bc
    pop af
    add a,c
    push hl
    ld c,a
    ld a,b
    cp 15
    jr nz,ui_draw_track_index_plain
    ld (hl),'>'
ui_draw_track_index_plain:
    ld a,c
    call ui_text_line
    pop hl
    ld (hl),' '
    ret

ui_build_track_select_line:
    call ui_line_clear
    ld hl,ui_track_select_heading
    call ui_line_append_string
    ld hl,(selected_track)
    inc hl
    call ui_line_append_u16
    ld hl,ui_track_select_of
    call ui_line_append_string
    ld hl,(KSP_HEADER+0x24)
    call ui_line_append_u16
    call ui_line_terminate
    ret

ui_ensure_track_cache:
    ld hl,(ui_track_top)
    ld de,(ui_track_cache_top)
    or a
    sbc hl,de
    ret z
    ld hl,(ui_track_top)
    ld (ui_track_cache_top),hl
    ld (ui_track_index),hl
    xor a
    ld (ui_draw_index),a
    ld b,UI_TRACK_ROWS
ui_fill_track_cache_loop:
    push bc
    ld hl,(ui_track_index)
    ld de,(KSP_HEADER+0x24)
    push hl
    or a
    sbc hl,de
    pop hl
    jr nc,ui_fill_track_cache_empty
    call ui_read_track_title
    jr ui_fill_track_cache_copy
ui_fill_track_cache_empty:
    call ui_line_fill_spaces
ui_fill_track_cache_copy:
    ld a,(ui_draw_index)
    call ui_track_cache_pointer
    ex de,hl
    ld hl,ui_line_buffer
    ld bc,UI_TRACK_CACHE_COLS
    ldir
    xor a
    ld (de),a
    ld hl,(ui_track_index)
    inc hl
    ld (ui_track_index),hl
    ld a,(ui_draw_index)
    inc a
    ld (ui_draw_index),a
    pop bc
    djnz ui_fill_track_cache_loop
    ret

ui_track_cache_pointer:
    ; A row -> HL = ui_file_names + row*49.
    ld e,a
    ld d,0
    ld h,d
    ld l,e
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl                  ; 16 * row
    push hl
    add hl,hl                  ; 32 * row
    pop de
    add hl,de                  ; 48 * row
    ld e,a
    ld d,0
    add hl,de                  ; 49 * row
    ld de,ui_file_names
    add hl,de
    ret

; --------------------------- Directory menu -------------------------------
ui_menu:
    call ui_scan_files
    xor a
    ld (ui_menu_selected),a
    ld (ui_menu_top),a
    call ui_draw_menu
    call ui_capture_keys
ui_menu_wait:
    ei
    halt
    di
    call ui_poll_action
    or a
    jr z,ui_menu_wait
    cp 1
    jr z,ui_menu_cancel
    cp 2
    jr z,ui_menu_choose
    cp 3
    jr z,ui_menu_up
    cp 5
    jr z,ui_menu_up
    cp 4
    jr z,ui_menu_down
    cp 6
    jr z,ui_menu_down
    jr ui_menu_wait
ui_menu_up:
    ld a,(ui_file_count)
    or a
    jr z,ui_menu_wait
    ld a,(ui_menu_selected)
    or a
    jr nz,ui_menu_up_dec
    ld a,(ui_file_count)
    dec a
    jr ui_menu_up_store
ui_menu_up_dec:
    dec a
ui_menu_up_store:
    call ui_menu_store_selection
    jr ui_menu_wait
ui_menu_down:
    ld a,(ui_file_count)
    or a
    jr z,ui_menu_wait
    ld b,a
    ld a,(ui_menu_selected)
    inc a
    cp b
    jr c,ui_menu_down_store
    xor a
ui_menu_down_store:
    call ui_menu_store_selection
    jr ui_menu_wait
ui_menu_choose:
    ld a,(ui_file_count)
    or a
    jr z,ui_menu_wait
    ld a,(ui_menu_selected)
    call ui_name_pointer
    ld de,filename
    ld b,13
ui_menu_copy_name:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jr z,ui_menu_name_done
    djnz ui_menu_copy_name
    xor a
    ld (de),a
ui_menu_name_done:
    or a
    ret
ui_menu_cancel:
    scf
    ret

ui_scan_files:
    xor a
    ld (ui_file_count),a
    ; Prepare a DOS1 ambiguous FCB for ????????.KSP.
    ld hl,ui_fib
    ld de,ui_fib+1
    ld bc,36
    ld (hl),0
    ldir
    ld hl,ui_fib+1
    ld b,8
    ld a,'?'
ui_scan_wild_name:
    ld (hl),a
    inc hl
    djnz ui_scan_wild_name
    ld (hl),'K'
    inc hl
    ld (hl),'S'
    inc hl
    ld (hl),'P'

    ld de,IO_BUFFER
    ld c,DOS_SETDTA
    call BDOS
    ld de,ui_fib
    ld c,DOS_SFIRST
    call BDOS
    or a
    jr nz,ui_scan_done
ui_scan_store:
    ld a,(ui_file_count)
    cp UI_MAX_FILES
    jr nc,ui_scan_done
    push af
    call ui_name_pointer
    ex de,hl                    ; DE destination 13-byte ASCIIZ slot
    ld hl,IO_BUFFER+1           ; drive byte precedes the 8.3 directory name
    ld b,8
ui_scan_copy_base:
    ld a,(hl)
    inc hl
    cp ' '
    jr z,ui_scan_skip_base_tail
    ld (de),a
    inc de
    djnz ui_scan_copy_base
    jr ui_scan_add_dot
ui_scan_skip_base_tail:
    dec b
    jr z,ui_scan_add_dot
ui_scan_skip_base_tail_advance:
    inc hl
    djnz ui_scan_skip_base_tail_advance
ui_scan_add_dot:
    ld a,'.'
    ld (de),a
    inc de
    ld b,3
ui_scan_copy_ext:
    ld a,(hl)
    inc hl
    cp ' '
    jr z,ui_scan_finish_name
    ld (de),a
    inc de
    djnz ui_scan_copy_ext
ui_scan_finish_name:
    xor a
    ld (de),a
    pop af
    inc a
    ld (ui_file_count),a
    ld c,DOS_SNEXT
    call BDOS
    or a
    jr z,ui_scan_store
ui_scan_done:
    ret

ui_name_pointer:
    ; A index -> HL = ui_file_names + index*13 (8 + 4 + 1).
    ld e,a
    ld d,0
    ld h,d
    ld l,e
    add hl,hl
    add hl,hl
    push hl
    add hl,hl
    pop de
    add hl,de
    ld e,a
    ld d,0
    add hl,de
    ld de,ui_file_names
    add hl,de
    ret

ui_adjust_menu_top:
    ld a,(ui_menu_selected)
    ld b,a
    ld a,(ui_menu_top)
    cp b
    jr c,ui_adjust_check_bottom
    jr z,ui_adjust_done
    ld a,b
    ld (ui_menu_top),a
    ret
ui_adjust_check_bottom:
    add a,UI_VISIBLE_ROWS
    cp b
    jr nc,ui_adjust_done
    ld a,b
    sub UI_VISIBLE_ROWS-1
    ld (ui_menu_top),a
ui_adjust_done:
    ret

ui_draw_menu:
    call ui_clear_screen
    ld a,0
    ld b,15
    ld hl,ui_menu_title
    call ui_text_line
    ld a,1
    ld b,7
    ld hl,ui_menu_subtitle
    call ui_text_line
    ld a,(ui_file_count)
    or a
    jr nz,ui_draw_menu_have_files
    ld a,10
    ld b,8
    ld hl,ui_no_files
    call ui_text_line
    jr ui_draw_menu_footer
ui_draw_menu_have_files:
    call ui_draw_menu_rows
ui_draw_menu_footer:
    ld a,23
    ld b,7
    ld hl,ui_menu_help
    call ui_text_line
    ld a,25
    ld b,8
    ld hl,ui_menu_exit
    call ui_text_line
    ret

; Redraw only the directory-list pane. Empty rows are explicitly erased so
; scrolling from the end of a longer page cannot leave stale filenames.
ui_draw_menu_rows:
    ld a,(ui_menu_top)
    ld (ui_draw_index),a
    ld a,4
    ld (ui_draw_row),a
    ld b,UI_VISIBLE_ROWS
ui_draw_menu_rows_loop:
    push bc
    ld a,(ui_draw_index)
    ld c,a
    ld a,(ui_file_count)
    cp c
    jr z,ui_draw_menu_rows_empty
    jr c,ui_draw_menu_rows_empty
    ld a,c
    call ui_name_pointer
    ld a,(ui_menu_selected)
    cp c
    ld b,7
    jr nz,ui_draw_menu_rows_render
    ld b,15
    jr ui_draw_menu_rows_render
ui_draw_menu_rows_empty:
    ld hl,ui_empty
    ld b,7
ui_draw_menu_rows_render:
    ld a,(ui_draw_row)
    call ui_text_line
    ld a,(ui_draw_index)
    inc a
    ld (ui_draw_index),a
    ld a,(ui_draw_row)
    inc a
    ld (ui_draw_row),a
    pop bc
    djnz ui_draw_menu_rows_loop
    ret

; -------------------------- Playback screen -------------------------------
ui_draw_player_screen:
    call restore_process_pages
    call ui_adjust_track_top
    call ui_ensure_track_cache
    call ui_clear_screen
    ld a,0
    ld b,15
    ld hl,filename
    call ui_text_line

    ; Engine name from its string-table-relative offset.
    ld hl,(ENGINE_ENTRY+52)
    ld a,(ENGINE_ENTRY+54)
    call ui_read_ksp_string
    ld a,1
    ld b,7
    ld hl,ui_string_buffer
    call ui_text_line

    call ui_build_hardware_line
    ld a,2
    ld b,11
    ld hl,ui_line_buffer
    call ui_text_line
    call ui_build_counts_line
    ld a,3
    ld b,11
    ld hl,ui_line_buffer
    call ui_text_line
    call ui_build_size_line
    ld a,4
    ld b,11
    ld hl,ui_line_buffer
    call ui_text_line

    ; Keep the chosen track visible after INIT and while playback is active.
    call ui_draw_selected_track_title

    ld a,7
    ld b,7
    ld hl,ui_tracks_heading
    call ui_text_line
    ld a,9
    ld b,UI_PLAYER_TRACK_ROWS
    call ui_draw_cached_tracks

    ld a,23
    ld b,7
    ld hl,ui_play_help
    call ui_text_line
    ld a,25
    ld b,8
    ld hl,ui_play_escape
    call ui_text_line
    call prepare_engine_page2
    ret

ui_draw_selected_track_title:
    call ui_selected_track_cache_pointer
    ld (hl),'>'
    push hl
    ld a,6
    ld b,15
    call ui_text_line
    pop hl
    ld (hl),' '
    ret

ui_selected_track_cache_pointer:
    ld hl,(selected_track)
    ld de,(ui_track_top)
    or a
    sbc hl,de
    ld a,l
    jp ui_track_cache_pointer

; A = first text row, B = number of cached tracks to draw.
ui_draw_cached_tracks:
    ld (ui_draw_row),a
    ld hl,(ui_track_top)
    ld (ui_track_index),hl
    xor a
    ld (ui_draw_index),a
ui_draw_cached_tracks_loop:
    push bc
    ld a,(ui_draw_index)
    call ui_track_cache_pointer
    ld de,(ui_track_index)
    push hl
    ld hl,(selected_track)
    or a
    sbc hl,de
    pop hl
    ld b,7
    jr nz,ui_draw_cached_tracks_normal
    ld (hl),'>'
    ld b,15
ui_draw_cached_tracks_normal:
    ld a,(ui_draw_row)
    push hl
    call ui_text_line
    pop hl
    ld (hl),' '
    ld hl,(ui_track_index)
    inc hl
    ld (ui_track_index),hl
    ld a,(ui_draw_index)
    inc a
    ld (ui_draw_index),a
    ld a,(ui_draw_row)
    inc a
    ld (ui_draw_row),a
    pop bc
    djnz ui_draw_cached_tracks_loop
    ret

ui_read_track_title:
    ; Build " index title" in ui_line_buffer without touching active TRACK_ENTRY.
    call ui_line_clear
    ld a,' '
    call ui_line_append_char
    ld hl,(ui_track_index)
    call ui_line_append_u16
    ld a,' '
    call ui_line_append_char
    ld hl,(ui_track_index)
    ld de,(KSP_HEADER+0x26)
    call mul16x16_24
    ld c,a
    ld de,(KSP_HEADER+0x20)
    add hl,de
    ld a,(KSP_HEADER+0x22)
    adc a,c
    ld de,ui_track_entry
    ld bc,32
    call read_at
    jr nz,ui_track_title_done
    ld hl,(ui_track_entry+12)
    ld a,(ui_track_entry+14)
    call ui_read_ksp_string
    ld hl,ui_string_buffer
ui_track_append_title:
    ld a,(hl)
    or a
    jr z,ui_track_title_done
    call ui_line_append_char
    inc hl
    jr ui_track_append_title
ui_track_title_done:
    ld a,(ui_line_pos)
    ld e,a
    ld d,0
    ld hl,ui_line_buffer
    add hl,de
    xor a
    ld (hl),a
    ret

ui_read_ksp_string:
    ; A:HL string-relative 24-bit offset. Result is sanitized ASCIIZ.
    ld c,a
    ld de,(KSP_HEADER+0x30)
    add hl,de
    ld a,(KSP_HEADER+0x32)
    adc a,c
    ld de,ui_string_buffer
    ld bc,UI_TEXT_COLS
    call read_at
    jr nz,ui_string_empty
    ld hl,ui_string_buffer
    ld b,UI_TEXT_COLS-1
ui_string_sanitize:
    ld a,(hl)
    or a
    ret z
    cp 0x20
    jr nc,ui_string_printable
    ; Some source playlists left a trailing CR before the NUL terminator.
    ; Treat control bytes as the end of the display string.
    xor a
    ld (hl),a
    ret
ui_string_printable:
    cp 0x80
    jr c,ui_string_next
    ld (hl),'?'
ui_string_next:
    inc hl
    djnz ui_string_sanitize
    xor a
    ld (hl),a
    ret
ui_string_empty:
    xor a
    ld (ui_string_buffer),a
    ret

ui_build_hardware_line:
    call ui_line_clear
    ld hl,ui_label_hardware
    call ui_line_append_string
    ld a,(ENGINE_ENTRY+4)
    bit 0,a
    call nz,ui_append_psg
    ld a,(ENGINE_ENTRY+4)
    bit 3,a
    jr z,ui_hw_single_scc
    ld hl,ui_hw_dualscc
    call ui_line_append_string
    jr ui_hw_after_scc
ui_hw_single_scc:
    bit 2,a
    jr z,ui_hw_normal_scc
    ld hl,ui_hw_sccplus
    call ui_line_append_string
    jr ui_hw_after_scc
ui_hw_normal_scc:
    bit 1,a
    jr z,ui_hw_after_scc
    ld hl,ui_hw_scc
    call ui_line_append_string
ui_hw_after_scc:
    ld a,(ENGINE_ENTRY+4)
    bit 4,a
    call nz,ui_append_fmpac
    ld a,(ENGINE_ENTRY+4)
    bit 6,a
    call nz,ui_append_opl4
    ld hl,ui_hw_sep
    call ui_line_append_string
    ld hl,(ENGINE_ENTRY+10)
    call ui_line_append_u16
    ld hl,ui_hw_hz
    call ui_line_append_string
    call ui_line_terminate
    ret
ui_append_psg:
    ld hl,ui_hw_psg
    jp ui_line_append_string
ui_append_fmpac:
    ld hl,ui_hw_fmpac
    jp ui_line_append_string
ui_append_opl4:
    ld hl,ui_hw_opl4
    jp ui_line_append_string

ui_build_counts_line:
    call ui_line_clear
    ld hl,ui_label_tracks
    call ui_line_append_string
    ld hl,(KSP_HEADER+0x24)
    call ui_line_append_u16
    ld hl,ui_label_pages
    call ui_line_append_string
    ld hl,(KSP_HEADER+0x1C)
    call ui_line_append_u16
    call ui_line_terminate
    ret
ui_build_size_line:
    call ui_line_clear
    ld hl,ui_label_size
    call ui_line_append_string
    ld hl,(KSP_HEADER+0x0C)
    ld a,(KSP_HEADER+0x0E)
    ; approximate KiB = (24-bit size + 1023) >> 10
    ld de,1023
    add hl,de
    adc a,0
    ld b,10
ui_size_shift:
    srl a
    rr h
    rr l
    djnz ui_size_shift
    call ui_line_append_u16
    ld hl,ui_label_kib
    call ui_line_append_string
    call ui_line_terminate
    ret

; ------------------------------ Errors ------------------------------------
ui_show_error:
    ld (ui_error_code),a
    call ui_clear_screen
    ld a,5
    ld b,8
    ld hl,ui_error_title
    call ui_text_line
    ld a,(ui_error_code)
    cp 1
    ld hl,ui_err_file
    jr z,ui_error_draw
    cp 2
    ld hl,ui_err_format
    jr z,ui_error_draw
    cp 3
    ld hl,ui_err_profile
    jr z,ui_error_draw
    cp 4
    ld hl,ui_err_hardware
    jr z,ui_error_draw
    cp 5
    ld hl,ui_err_memory
    jr z,ui_error_draw
    cp 6
    ld hl,ui_err_track
    jr z,ui_error_draw
    ld hl,ui_err_decode
ui_error_draw:
    ld a,9
    ld b,15
    call ui_text_line
    ld a,20
    ld b,7
    ld hl,ui_error_return
    call ui_text_line
    call ui_capture_keys
ui_error_wait:
    ei
    halt
    di
    call ui_poll_action
    or a
    jr z,ui_error_wait
    ret

; ---------------------------- Keyboard ------------------------------------
ui_capture_keys:
    call ui_read_keyboard
    ld a,(ui_keys7_now)
    ld (ui_keys7_prev),a
    ld a,(ui_keys8_now)
    ld (ui_keys8_prev),a
    ret
ui_poll_action:
    call ui_read_keyboard
    ld a,(ui_keys7_prev)
    cpl
    ld b,a
    ld a,(ui_keys7_now)
    and b
    ld c,a
    ld a,(ui_keys7_now)
    ld (ui_keys7_prev),a
    ld a,(ui_keys8_prev)
    cpl
    ld b,a
    ld a,(ui_keys8_now)
    and b
    ld d,a
    ld a,(ui_keys8_now)
    ld (ui_keys8_prev),a
    bit 2,c
    jr nz,ui_action_escape
    bit 7,c
    jr nz,ui_action_enter
    bit 5,d
    jr nz,ui_action_up
    bit 6,d
    jr nz,ui_action_down
    bit 4,d
    jr nz,ui_action_left
    bit 7,d
    jr nz,ui_action_right
    bit 0,d
    jr nz,ui_action_space
    xor a
    ret
ui_action_escape: ld a,1
    jr ui_action_finish
ui_action_enter: ld a,2
    jr ui_action_finish
ui_action_up: ld a,3
    jr ui_action_finish
ui_action_down: ld a,4
    jr ui_action_finish
ui_action_left: ld a,5
    jr ui_action_finish
ui_action_right: ld a,6
    jr ui_action_finish
ui_action_space: ld a,7
ui_action_finish:
    push af
    ld a,(engine_running)
    or a
    call z,ui_clear_bios_keyboard_buffer
    pop af
    ret
ui_read_keyboard:
    in a,(PORT_KEY_ROW)
    ld e,a
    and 0xF0
    or 7
    out (PORT_KEY_ROW),a
    in a,(PORT_KEY_IN)
    cpl
    and 0x84
    ld (ui_keys7_now),a
    ld a,e
    out (PORT_KEY_ROW),a
    in a,(PORT_KEY_ROW)
    ld e,a
    and 0xF0
    or 8
    out (PORT_KEY_ROW),a
    in a,(PORT_KEY_IN)
    cpl
    and 0xF1
    ld (ui_keys8_now),a
    ld a,e
    out (PORT_KEY_ROW),a
    ret

; ---------------------------- Screen 5 ------------------------------------
ui_screen5_init:
    di
    ld a,0x06
    ld c,0
    call ui_write_vdp_register
    ld a,0x60
    ld c,1
    call ui_write_vdp_register
    ld a,0x1F
    ld c,2
    call ui_write_vdp_register
    xor a
    ld c,7
    call ui_write_vdp_register
    ld a,(RG8SAV)
    or 0x02
    ld c,8
    call ui_write_vdp_register
    ld a,(RG9SAV)
    and 0x02
    or 0x80
    ld c,9
    call ui_write_vdp_register
    xor a
    ld c,18
    call ui_write_vdp_register
    xor a
    ld c,23
    call ui_write_vdp_register
    call ui_clear_screen
    ei
    ret

ui_clear_screen:
    call vdp_irq_begin
    ld hl,0
    xor a
    call vram_set_write_address
    ld bc,0x6A00
ui_clear_vram_loop:
    xor a
    out (PORT_VDP_DATA),a
    dec bc
    ld a,b
    or c
    jr nz,ui_clear_vram_loop
    jp vdp_irq_end

ui_restore_screen0:
    ; KSP1PLAY requires MSX2 for SCREEN 5, so native 80-column SCREEN 0 is
    ; always available. Ask the main BIOS to initialize it instead of leaving
    ; DOS with the player's compact graphics font and hand-built 40-column mode.
    di
    call restore_process_pages
    ld a,80
    ld (LINL40),a
    db 0xDD,0xE5              ; PUSH IX
    db 0xFD,0xE5              ; PUSH IY
    db 0xDD,0x21              ; LD IX,BIOS_INITXT
    dw BIOS_INITXT
    call ui_call_main_bios
    db 0xFD,0xE1              ; POP IY
    db 0xDD,0xE1              ; POP IX
    di
    ld a,80
    ld (LINLEN),a
    ld a,24
    ld (CRTCNT),a
    xor a
    ld (CSRX),a
    ld (CSRY),a
    ei
    ret

ui_call_main_bios:
    db 0xFD,0x2A              ; LD IY,(EXPTBL-1)
    dw EXPTBL-1
    jp BIOS_CALSLT

ui_clear_bios_keyboard_buffer:
    ; Do not enter CALSLT from the live Screen-5/menu path. Depending on the
    ; Avoid BIOS slot switching underneath the live resident player.
    ; Empty the BIOS ring buffer directly by making the read pointer catch up
    ; with the write pointer. PUTPNT/GETPNT are stable BIOS work-area words.
    push hl
    ld hl,(PUTPNT)
    ld (GETPNT),hl
    pop hl
    ret

; Wait for the physical key that triggered ESC/ENTER to be released. Otherwise
 ; COMMAND.COM can receive a fresh key-repeat after screen exit and execute
; stray input at the prompt.
ui_wait_keys_released:
    ei
ui_wait_keys_released_loop:
    halt
    di
    call ui_read_keyboard
    ld a,(ui_keys7_now)
    ld b,a
    ld a,(ui_keys8_now)
    or b
    jr nz,ui_wait_keys_released_more
    xor a
    ld (ui_keys7_prev),a
    ld (ui_keys8_prev),a
    ei
    ret
ui_wait_keys_released_more:
    ei
    jr ui_wait_keys_released_loop

 ; Reset every package-owned FCB/cache/profile after its corresponding free.
; Mapper API pointers and the captured DOS process pages intentionally survive
; so another package can be opened without re-probing the mapper.
ui_write_vdp_register:
    ; A value, C register. Synchronize the BIOS shadows used by the interrupt handler.
    push af
    push bc
    ld b,a
    ld a,c
    cp 8
    jr nc,ui_vdp_shadow_high
    ld hl,RG0SAV
    ld e,c
    ld d,0
    add hl,de
    ld (hl),b
    jr ui_vdp_write_hw
ui_vdp_shadow_high:
    cp 8
    jr nz,ui_vdp_shadow_r9
    ld a,b
    ld (RG8SAV),a
    jr ui_vdp_write_hw
ui_vdp_shadow_r9:
    cp 9
    jr nz,ui_vdp_shadow_r18
    ld a,b
    ld (RG9SAV),a
    jr ui_vdp_write_hw
ui_vdp_shadow_r18:
    cp 18
    jr nz,ui_vdp_shadow_r23
    ld a,b
    ld (RG18SA),a
    jr ui_vdp_write_hw
ui_vdp_shadow_r23:
    cp 23
    jr nz,ui_vdp_write_hw
    ld a,b
    ld (RG23SA),a
ui_vdp_write_hw:
    ld a,b
    out (PORT_VDP_CTRL),a
    ld a,c
    or 0x80
    out (PORT_VDP_CTRL),a
    pop bc
    pop af
    ret

; Render one padded 64-character row in Screen 5. Each 3x5 glyph uses a
; four-pixel cell (one blank column) and has three blank scanlines below it.
; A=row, B=foreground colour.
ui_text_line:
    ld (ui_text_row),a
    ld a,b
    and 0x0F
    ld (ui_text_fg),a
    push hl
    call ui_line_fill_spaces
    pop hl
    ld de,ui_line_buffer
    ld b,UI_TEXT_COLS
ui_text_copy:
    ld a,(hl)
    or a
    jr z,ui_text_copy_done
    cp 0x20
    ; CR, LF and every other control byte terminate the rendered line.
    ; Do not convert them to the fallback question-mark glyph.
    jr c,ui_text_copy_done
    cp 0x80
    jr c,ui_text_store
    ld a,'?'
ui_text_store:
    ld (de),a
    inc hl
    inc de
    djnz ui_text_copy
ui_text_copy_done:
    ; The destination row was prefilled with spaces. Keep the first padding
    ; cell as a space: the fixed-width glyph pass renders every cell, and a
    ; NUL here would be mapped to the fallback question-mark glyph.
    ld a,' '
    ld (de),a
    xor a
    ld (ui_glyph_scan),a
ui_text_scan_loop:
    ; address = row*1024 + scan*128
    ld a,(ui_text_row)
    ld h,a
    ld l,0
    add hl,hl
    add hl,hl
    ld a,(ui_glyph_scan)
    or a
    jr z,ui_text_address_ready
    ld e,a
    ld d,0
ui_text_add_scan:
    ld bc,0x0080
    add hl,bc
    dec e
    jr nz,ui_text_add_scan
ui_text_address_ready:
    call vdp_irq_begin
    xor a
    call vram_set_write_address
    ld hl,ui_line_buffer
    ld b,UI_TEXT_COLS
ui_text_glyph_loop:
    push bc
    ld a,(hl)
    inc hl
    push hl
    call ui_get_font_pointer
    ld a,(ui_glyph_scan)
    cp 5
    jr nc,ui_text_blank_scan
    ld e,a
    ld d,0
    add hl,de
    ld a,(hl)
    jr ui_text_have_scan
ui_text_blank_scan:
    xor a
ui_text_have_scan:
    pop hl
    call ui_write_small_glyph_row
    pop bc
    djnz ui_text_glyph_loop
    call vdp_irq_end
    ld a,(ui_glyph_scan)
    inc a
    ld (ui_glyph_scan),a
    cp 8
    jr c,ui_text_scan_loop
    ret

; Map lowercase to uppercase and return HL = six-byte 4x6 glyph.
ui_get_font_pointer:
    cp 'a'
    jr c,ui_font_not_lower
    cp 'z'+1
    jr nc,ui_font_not_lower
    sub 32
ui_font_not_lower:
    cp 32
    jr c,ui_font_question
    cp 96
    jr c,ui_font_ascii_ok
ui_font_question:
    ld a,'?'
ui_font_ascii_ok:
    sub 32
    ld e,a
    ld d,0
    ld h,d
    ld l,e
    add hl,hl
    add hl,hl
    add hl,de
    ld de,ui_font
    add hl,de
    ret

ui_write_small_glyph_row:
    and 0x07
    rlca
    rlca
    rlca
    rlca
    rlca
    ld c,a
    ld a,(ui_text_fg)
    ld b,a
    rlca
    rlca
    rlca
    rlca
    ld d,a
    call ui_write_pixel_pair
    call ui_write_pixel_pair
    ret

ui_write_pixel_pair:
    xor a
    sla c
    jr nc,ui_pair_first_zero
    or d
ui_pair_first_zero:
    sla c
    jr nc,ui_pair_second_zero
    or b
ui_pair_second_zero:
    out (PORT_VDP_DATA),a
    ret

ui_expand_font_row:
    and 0x07
    ld e,a
    ld d,0
    ld hl,ui_expand_table
    add hl,de
    ld a,(hl)
    ret

; -------------------------- Line construction -----------------------------
ui_line_clear:
    xor a
    ld (ui_line_pos),a
    ld (ui_line_buffer),a
    ret
ui_line_fill_spaces:
    ld hl,ui_line_buffer
    ld b,UI_TEXT_COLS
    ld a,' '
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
    cp UI_TEXT_COLS-1
    jr nc,ui_line_append_char_done
    ld l,a
    ld h,0
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
    jr ui_line_append_string
ui_line_terminate:
    ld a,(ui_line_pos)
    ld l,a
    ld h,0
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
    add a,'0'
    dec de
    ld (de),a
    ld a,h
    or l
    jr nz,ui_u16_digits
    ex de,hl
    call ui_line_append_string
    ret

; ------------------------------ Data --------------------------------------
ui_file_count:      db 0
ui_menu_selected:   db 0
ui_menu_top:        db 0
ui_draw_index:      db 0
ui_draw_row:        db 0
ui_track_index:     dw 0
ui_track_top:       dw 0
ui_track_cache_top: dw 0xFFFF
ui_previous_track:  dw 0
ui_previous_top:    dw 0
ui_text_row:        db 0
ui_text_fg:         db 15
ui_glyph_scan:      db 0
ui_restore_char:    db 32
ui_line_pos:        db 0
ui_keys7_now:       db 0
ui_keys8_now:       db 0
ui_keys7_prev:      db 0
ui_keys8_prev:      db 0
ui_num_buffer:      ds 6,0
ui_line_buffer:     ds 65,0
ui_string_buffer:   ds 65,0
ui_track_entry:     ds 32,0
ui_fib:             ds 64,0
ui_file_names:      ds 735,0
ui_pattern:         db '*.KSP',0
ui_empty:           db 0
ui_menu_title:      db 'KSP1 0.20 DOS1',0
ui_menu_subtitle:   db 'SELECT A KSP PACKAGE',0
ui_no_files:        db 'NO KSP FILES FOUND',0
ui_menu_help:       db 'UP/DOWN  ENTER: PLAY',0
ui_menu_exit:       db 'ESC: EXIT TO MSX-DOS',0
ui_tracks_heading:  db 'TRACKS',0
ui_track_select_heading: db 'SELECT TRACK ',0
ui_track_select_of:      db ' OF ',0
ui_track_select_help:    db 'UP/DOWN: TRACK   LEFT/RIGHT: PAGE',0
ui_track_select_escape:  db 'ENTER/SPACE: PLAY   ESC: PACKAGE MENU',0
ui_play_help:       db 'UP/DOWN OR LEFT/RIGHT: CHANGE TRACK',0
ui_play_escape:     db 'SPACE: NEXT TRACK   ESC: PACKAGE MENU',0
ui_label_hardware:  db 'HARDWARE ',0
ui_label_tracks:    db 'TRACKS ',0
ui_label_pages:     db '  PAGES ',0
ui_label_size:      db 'PACKAGE ',0
ui_label_kib:       db ' KIB',0
ui_hw_psg:          db 'PSG ',0
ui_hw_scc:          db 'SCC ',0
ui_hw_sccplus:      db 'SCC+ ',0
ui_hw_dualscc:      db 'DUAL-SCC ',0
ui_hw_fmpac:        db 'FMPAC ',0
ui_hw_opl4:         db 'OPL4 ',0
ui_hw_sep:          db ' @ ',0
ui_hw_hz:           db 'HZ',0
ui_error_title:     db 'COULD NOT PLAY PACKAGE',0
ui_err_file:        db 'FILE ACCESS FAILED',0
ui_err_format:      db 'INVALID KSP 1.x FILE',0
ui_err_profile:     db 'UNSUPPORTED ENGINE LAYOUT',0
ui_err_hardware:    db 'REQUIRED HARDWARE NOT FOUND',0
ui_err_memory:      db 'NOT ENOUGH MAPPER MEMORY',0
ui_err_track:       db 'TRACK OR PAGE IS INVALID',0
ui_err_decode:      db 'PAGE DECOMPRESSION FAILED',0
ui_error_return:    db 'PRESS ANY KEY FOR MENU',0

ui_font:
    db 0x00,0x00,0x00,0x00,0x00,0x02,0x02,0x02,0x00,0x02,0x05,0x05,0x00,0x00,0x00,0x05,0x07,0x05,0x07,0x05
    db 0x03,0x06,0x02,0x03,0x06,0x05,0x01,0x02,0x04,0x05,0x02,0x05,0x02,0x05,0x03,0x02,0x02,0x00,0x00,0x00
    db 0x01,0x02,0x02,0x02,0x01,0x04,0x02,0x02,0x02,0x04,0x00,0x05,0x02,0x05,0x00,0x00,0x02,0x07,0x02,0x00
    db 0x00,0x00,0x00,0x02,0x04,0x00,0x00,0x07,0x00,0x00,0x00,0x00,0x00,0x00,0x02,0x01,0x01,0x02,0x04,0x04
    db 0x07,0x05,0x05,0x05,0x07,0x02,0x06,0x02,0x02,0x07,0x06,0x01,0x07,0x04,0x07,0x06,0x01,0x07,0x01,0x06
    db 0x05,0x05,0x07,0x01,0x01,0x07,0x04,0x06,0x01,0x06,0x03,0x04,0x07,0x05,0x07,0x07,0x01,0x02,0x02,0x02
    db 0x07,0x05,0x07,0x05,0x07,0x07,0x05,0x07,0x01,0x06,0x00,0x02,0x00,0x02,0x00,0x00,0x02,0x00,0x02,0x04
    db 0x01,0x02,0x04,0x02,0x01,0x00,0x07,0x00,0x07,0x00,0x04,0x02,0x01,0x02,0x04,0x06,0x01,0x02,0x00,0x02
    db 0x07,0x05,0x07,0x04,0x07,0x02,0x05,0x07,0x05,0x05,0x06,0x05,0x06,0x05,0x06,0x03,0x04,0x04,0x04,0x03
    db 0x06,0x05,0x05,0x05,0x06,0x07,0x04,0x06,0x04,0x07,0x07,0x04,0x06,0x04,0x04,0x03,0x04,0x05,0x05,0x03
    db 0x05,0x05,0x07,0x05,0x05,0x07,0x02,0x02,0x02,0x07,0x01,0x01,0x01,0x05,0x02,0x05,0x05,0x06,0x05,0x05
    db 0x04,0x04,0x04,0x04,0x07,0x05,0x07,0x07,0x05,0x05,0x05,0x07,0x07,0x07,0x05,0x02,0x05,0x05,0x05,0x02
    db 0x06,0x05,0x06,0x04,0x04,0x02,0x05,0x05,0x07,0x03,0x06,0x05,0x06,0x05,0x05,0x03,0x04,0x02,0x01,0x06
    db 0x07,0x02,0x02,0x02,0x02,0x05,0x05,0x05,0x05,0x07,0x05,0x05,0x05,0x05,0x02,0x05,0x05,0x07,0x07,0x05
    db 0x05,0x05,0x02,0x05,0x05,0x05,0x05,0x02,0x02,0x02,0x07,0x01,0x02,0x04,0x07,0x03,0x02,0x02,0x02,0x03
    db 0x04,0x04,0x02,0x01,0x01,0x06,0x02,0x02,0x02,0x06,0x02,0x05,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x07

ui_expand_table:
    db 0x00,0x0C,0x30,0x3C,0xC0,0xCC,0xF0,0xFC

ui_code_end:
org 0x3500
hpol_position_cache: ds 512,0
hpol_map_row_cache:  ds 512,0
ui_module_end:

; ---------------------------------------------------------------------------
; MoonSound / OPL4 support
; ---------------------------------------------------------------------------
; Permanent high-page-0 helper code. STACK_TOP is below this region.
org 0x3A00

validate_required_hardware:
    xor a
    ld (opl4_present),a
    ld (hardware_error_code),a
    ld a,(ENGINE_ENTRY+4)
    and 0x08
    jr z,validate_hardware_opl4
    ld a,(scc_slot)
    ld b,a
    ld a,(scc_slot_b)
    cp b
    jr nz,validate_hardware_opl4
    ld a,1
    ld (hardware_error_code),a
    jr validate_hardware_bad
validate_hardware_opl4:
    ld a,(ENGINE_ENTRY+4)
    and 0x40
    ret z
    call detect_opl4
    ret c
    ld a,1
    ld (opl4_present),a
    or a
    ret
validate_hardware_bad:
    scf
    ret

detect_opl4:
    ; OPL4 wave register 02h returns device ID 20h in bits 7..5.
    ld a,0x02
    out (PORT_OPL4_WAVE_A),a
    call opl4_wave_wait
    in a,(PORT_OPL4_WAVE_D)
    and 0xE0
    cp 0x20
    ret z
    scf
    ret

upload_current_mwk:
    ld a,(ENGINE_ENTRY+4)
    and 0x40
    ret z

    ; Track MWK overrides the engine default.
    ld hl,(TRACK_ENTRY+6)
    ld a,h
    cp 0xFF
    jr nz,mwk_ref_ready
    ld a,l
    cp 0xFF
    jr nz,mwk_ref_ready
    ld hl,(ENGINE_ENTRY+30)
mwk_ref_ready:
    ld a,h
    cp 0xFF
    jr nz,mwk_have_ref
    ld a,l
    cp 0xFF
    jr nz,mwk_have_ref
    ld a,(ENGINE_ENTRY)
    and 0x04
    ret z
    scf
    ret

mwk_have_ref:
    call mwk_load_resource_entry
    ret c
    ld a,(RESOURCE_ENTRY+6)
    or a
    jr z,mwk_upload_none
    cp 1
    jr z,mwk_upload_zx0
    cp 2
    jr z,mwk_upload_blocks
    scf
    ret

mwk_upload_none:
    call mwk_begin_stream
    ret c
    xor a
    ld (mwk_source_mode),a
    call mwk_parse
    push af
    call stream_end
    call restore_process_pages
    pop af
    ret

mwk_upload_zx0:
    call mwk_validate_scratch_size
    ret c
    call ensure_mwk_segment
    ret c
    call mwk_begin_stream
    ret c
    ld a,(mwk_segment)
    call map_p2
    xor a
    ld (zx_mode),a
    ld hl,0x8000
    ld (linear_base),hl
    ld hl,(RESOURCE_ENTRY+16)
    ld a,(RESOURCE_ENTRY+18)
    call zx_set_output_size
    call zx_decode_stream
    jr c,mwk_upload_restore_bad
    ld a,1
    ld (mwk_source_mode),a
    ld hl,0x8000
    ld (mwk_buffer_ptr),hl
    ld hl,(RESOURCE_ENTRY+16)
    ld (mwk_buffer_left),hl
    call mwk_parse
    push af
    call restore_process_pages
    pop af
    ret

mwk_upload_blocks:
    call ensure_mwk_segment
    ret c
    ld hl,(RESOURCE_ENTRY+8)
    ld a,(RESOURCE_ENTRY+10)
    ld de,IO_BUFFER
    ld bc,16
    call read_at
    jr nz,mwk_upload_bad
    ld hl,IO_BUFFER
    ld a,(hl)
    cp 'K'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp 'Z'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp 'B'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp '1'
    jr nz,mwk_upload_bad
    ld hl,(IO_BUFFER+4)
    ld de,16
    or a
    sbc hl,de
    jr nz,mwk_upload_bad
    ld hl,(IO_BUFFER+6)
    ld (mwk_block_count),hl
    ld a,h
    or l
    jr z,mwk_upload_bad
    ld hl,(IO_BUFFER+8)
    ld de,(RESOURCE_ENTRY+16)
    or a
    sbc hl,de
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+10)
    ld b,a
    ld a,(RESOURCE_ENTRY+18)
    cp b
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+11)
    or a
    jr nz,mwk_upload_bad
    ld hl,(IO_BUFFER+12)
    ld (mwk_block_table),hl
    ld a,(IO_BUFFER+14)
    ld (mwk_block_table+2),a
    ld a,(IO_BUFFER+15)
    or a
    jr nz,mwk_upload_bad
    xor a
    ld (mwk_block_index),a
    ld (mwk_block_index+1),a
    ld (mwk_buffer_left),a
    ld (mwk_buffer_left+1),a
    ld a,2
    ld (mwk_source_mode),a
    call mwk_parse
    push af
    call restore_process_pages
    pop af
    ret

mwk_upload_restore_bad:
    call restore_process_pages
mwk_upload_bad:
    scf
    ret

mwk_load_resource_entry:
    push hl
    ld de,(KSP_HEADER+0x2C)
    or a
    sbc hl,de
    pop hl
    jr nc,mwk_upload_bad
    ld de,32
    call mul16x16_24
    ld c,a
    ld de,(KSP_HEADER+0x28)
    add hl,de
    ld a,(KSP_HEADER+0x2A)
    adc a,c
    ld de,RESOURCE_ENTRY
    ld bc,32
    call read_at
    jr nz,mwk_upload_bad
    ld hl,RESOURCE_ENTRY
    ld a,(hl)
    cp 'M'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp 'W'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp 'K'
    jr nz,mwk_upload_bad
    inc hl
    ld a,(hl)
    cp ' '
    jr nz,mwk_upload_bad
    ld a,(RESOURCE_ENTRY+7)
    or a
    jr nz,mwk_upload_bad
    ld a,(RESOURCE_ENTRY+11)
    or a
    jr nz,mwk_upload_bad
    ld a,(RESOURCE_ENTRY+15)
    or a
    jr nz,mwk_upload_bad
    ld a,(RESOURCE_ENTRY+19)
    or a
    jr nz,mwk_upload_bad
    or a
    ret

mwk_begin_stream:
    call restore_process_pages
    ld hl,(RESOURCE_ENTRY+8)
    ld a,(RESOURCE_ENTRY+10)
    ld de,(RESOURCE_ENTRY+12)
    ld b,d
    ld c,e
    call stream_begin
    ret c
    ld a,(RESOURCE_ENTRY+14)
    ld (stream_remaining+2),a
    or a
    ret

mwk_validate_scratch_size:
    ld a,(RESOURCE_ENTRY+18)
    or a
    jr nz,mwk_upload_bad
    ld hl,(RESOURCE_ENTRY+16)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,mwk_upload_bad
    or a
    ret

ensure_mwk_segment:
    ld a,(mwk_segment_allocated)
    or a
    ret nz
    call mapper_alloc_user_primary
    ret c
    ld (mwk_segment),a
    ld a,1
    ld (mwk_segment_allocated),a
    or a
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

mwk_load_next_block:
    ld hl,(mwk_block_index)
    ld de,(mwk_block_count)
    or a
    sbc hl,de
    jr nc,mwk_upload_bad
    add hl,de
    ld de,16
    call mul16x16_24
    ld c,a
    ld de,(mwk_block_table)
    add hl,de
    ld a,(mwk_block_table+2)
    adc a,c
    ld de,(RESOURCE_ENTRY+8)
    add hl,de
    ld c,a
    ld a,(RESOURCE_ENTRY+10)
    adc a,c
    call restore_process_pages
    ld de,IO_BUFFER
    ld bc,16
    call read_at
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+3)
    or a
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+7)
    or a
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+10)
    or a
    jr nz,mwk_upload_bad
    ld a,(IO_BUFFER+11)
    or a
    jr nz,mwk_upload_bad
    ld hl,(IO_BUFFER+8)
    ld de,0x4001
    or a
    sbc hl,de
    jr nc,mwk_upload_bad
    add hl,de
    ld a,h
    or l
    jr z,mwk_upload_bad
    ld hl,(IO_BUFFER)
    ld a,(IO_BUFFER+2)
    ld de,(RESOURCE_ENTRY+8)
    add hl,de
    ld c,a
    ld a,(RESOURCE_ENTRY+10)
    adc a,c
    ld de,(IO_BUFFER+4)
    ld b,d
    ld c,e
    call stream_begin
    jr c,mwk_upload_bad
    ld a,(IO_BUFFER+6)
    ld (stream_remaining+2),a
    ld a,(mwk_segment)
    call map_p2
    xor a
    ld (zx_mode),a
    ld hl,0x8000
    ld (linear_base),hl
    ld hl,(IO_BUFFER+8)
    xor a
    call zx_set_output_size
    call zx_decode_stream
    jr c,mwk_upload_restore_bad
    ld hl,0x8000
    ld (mwk_buffer_ptr),hl
    ld hl,(IO_BUFFER+8)
    ld (mwk_buffer_left),hl
    ld hl,(mwk_block_index)
    inc hl
    ld (mwk_block_index),hl
    or a
    ret

mwk_get:
    push bc
    push de
    push hl
    call mwk_get_raw
    pop hl
    pop de
    pop bc
    ret

mwk_get_raw:
    ld a,(mwk_source_mode)
    or a
    jp z,zx_read_byte
    ld hl,(mwk_buffer_left)
    ld a,h
    or l
    jr nz,mwk_get_buffered
    ld a,(mwk_source_mode)
    cp 2
    jr nz,mwk_get_eof
    call mwk_load_next_block
    ret c
mwk_get_buffered:
    ld hl,(mwk_buffer_ptr)
    ld a,(hl)
    inc hl
    ld (mwk_buffer_ptr),hl
    ld hl,(mwk_buffer_left)
    dec hl
    ld (mwk_buffer_left),hl
    or a
    ret
mwk_get_eof:
    scf
    ret

mwk_skip_hl:
    ld a,h
    or l
    ret z
    call mwk_get
    ret c
    dec hl
    jr mwk_skip_hl

mwk_parse:
    xor a
    ld (mwk_write_enabled),a
    ld hl,mwk_signature
    ld b,5
mwk_sig_loop:
    call mwk_get
    jr c,mwk_parse_fail
    cp (hl)
    jr nz,mwk_parse_fail
    inc hl
    djnz mwk_sig_loop
    call mwk_get
    jr c,mwk_parse_fail
    cp 0x0C
    jr z,mwk_mode_edit
    cp 0x0D
    jr nz,mwk_parse_fail
    xor a
    jr mwk_mode_ready
mwk_mode_edit:
    ld a,1
mwk_mode_ready:
    ld (mwk_edit),a
    ld hl,3
    call mwk_skip_hl
    jr c,mwk_parse_fail
    call mwk_get
    jr c,mwk_parse_fail
    cp 49
    jr nc,mwk_parse_fail
    ld (mwk_wave_count),a
    ld hl,TITLE_BUFFER
    ld b,64
mwk_flags_loop:
    call mwk_get
    jr c,mwk_parse_fail
    ld (hl),a
    inc hl
    djnz mwk_flags_loop
    ld a,(mwk_wave_count)
    ld b,a
mwk_skip_patch_loop:
    ld a,b
    or a
    jr z,mwk_patch_done
    ld hl,25
    call mwk_skip_hl
    jr c,mwk_parse_fail
    djnz mwk_skip_patch_loop
mwk_patch_done:
    ld a,(mwk_edit)
    or a
    jr z,mwk_tables_done
    ld a,(mwk_wave_count)
    ld b,a
mwk_skip_edit_loop:
    ld a,b
    or a
    jr z,mwk_tables_done
    ld hl,16
    call mwk_skip_hl
    jr c,mwk_parse_fail
    djnz mwk_skip_edit_loop
mwk_tables_done:
    ld a,2
    ld e,0x11
    call opl4_write_wave
    ld a,1
    ld (mwk_write_enabled),a
    ld hl,0x0300
    ld (mwk_sample_addr),hl
    ld a,0x20
    ld (mwk_sample_addr+2),a
    ld hl,0
    ld (mwk_header_addr),hl
    ld hl,TITLE_BUFFER
    ld (mwk_flag_ptr),hl
    ld a,64
    ld (mwk_tones_left),a
mwk_tone_loop:
    ld hl,(mwk_flag_ptr)
    ld a,(hl)
    inc hl
    ld (mwk_flag_ptr),hl
    ld (mwk_flag),a
    and 1
    jr z,mwk_next_tone
    ld a,(mwk_edit)
    or a
    jr z,mwk_read_header
    ld hl,16
    call mwk_skip_hl
    jr c,mwk_parse_fail_enabled
mwk_read_header:
    ld hl,TITLE_BUFFER+64
    ld b,13
mwk_header_loop:
    call mwk_get
    jr c,mwk_parse_fail_enabled
    ld (hl),a
    inc hl
    djnz mwk_header_loop
    ld a,(mwk_sample_addr+1)
    ld (TITLE_BUFFER+81),a
    ld a,(mwk_sample_addr)
    ld (TITLE_BUFFER+82),a
    ld a,(mwk_flag)
    and 0x20
    jr nz,mwk_rom_header
    ld a,(mwk_sample_addr+2)
    and 0x3F
    ld b,a
    ld a,(mwk_flag)
    and 0xC0
    or b
    ld (TITLE_BUFFER+80),a
    ld hl,(TITLE_BUFFER+75)
    ld (mwk_sample_size),hl
    jr mwk_header_tail
mwk_rom_header:
    ld a,(TITLE_BUFFER+76)
    ld b,a
    ld a,(mwk_flag)
    and 0xC0
    or b
    ld (TITLE_BUFFER+80),a
    ld hl,0
    ld (mwk_sample_size),hl
mwk_header_tail:
    ld hl,TITLE_BUFFER+66
    ld de,TITLE_BUFFER+83
    ld bc,9
    ldir
    ld hl,(mwk_header_addr)
    ld a,0x20
    call opl4_set_memory_address
    ld hl,TITLE_BUFFER+80
    ld b,12
mwk_write_header_loop:
    ld a,(hl)
    out (PORT_OPL4_WAVE_D),a
    inc hl
    djnz mwk_write_header_loop
    ld hl,(mwk_sample_size)
    ld a,h
    or l
    jr z,mwk_next_tone
    ld hl,(mwk_sample_addr)
    ld a,(mwk_sample_addr+2)
    call opl4_set_memory_address
    ld hl,(mwk_sample_size)
mwk_sample_loop:
    ld a,h
    or l
    jr z,mwk_sample_done
    call mwk_get
    jr c,mwk_parse_fail_enabled
    out (PORT_OPL4_WAVE_D),a
    dec hl
    jr mwk_sample_loop
mwk_sample_done:
    ld hl,(mwk_sample_addr)
    ld de,(mwk_sample_size)
    add hl,de
    ld (mwk_sample_addr),hl
    ld a,(mwk_sample_addr+2)
    adc a,0
    ld (mwk_sample_addr+2),a
    cp 0x40
    jr c,mwk_next_tone
    jr nz,mwk_parse_fail_enabled
    ld a,h
    or l
    jr nz,mwk_parse_fail_enabled
mwk_next_tone:
    ld hl,(mwk_header_addr)
    ld de,12
    add hl,de
    ld (mwk_header_addr),hl
    ld a,(mwk_tones_left)
    dec a
    ld (mwk_tones_left),a
    jr nz,mwk_tone_loop
    call mwk_disable_write
    or a
    ret
mwk_parse_fail_enabled:
    call mwk_disable_write
mwk_parse_fail:
    scf
    ret

mwk_disable_write:
    xor a
    ld (mwk_write_enabled),a
    ld a,2
    ld e,0x10
    jp opl4_write_wave

opl4_set_memory_address:
    ld d,a
    and 0x3F
    ld e,a
    ld a,3
    call opl4_write_wave
    ld e,h
    ld a,4
    call opl4_write_wave
    ld e,l
    ld a,5
    call opl4_write_wave
    ld a,6
    out (PORT_OPL4_WAVE_A),a
    jp opl4_wave_wait

prepare_opl4_init:
    ld a,(opl4_present)
    or a
    ret z
    ld a,(ENGINE_ENTRY+4)
    and 0x40
    ret z
    ld a,0xF8
    ld e,0
    call opl4_write_wave
    ld a,0xF9
    ld e,0
    jp opl4_write_wave

hard_reset_opl4:
    ld a,(opl4_present)
    or a
    ret z
    ; Disable OPL4 FM timer IRQs.
    ld a,0x04
    out (PORT_OPL4_FM0_A),a
    ld a,0x80
    out (PORT_OPL4_FM0_D),a
    call opl4_fm_wait

    ; Mute OPL4 FM and PCM mixers.
    ld a,0xF8
    ld e,0x3F
    call opl4_write_wave
    ld a,0xF9
    ld e,0x3F
    call opl4_write_wave

    ; Key off all 18 OPL3-compatible FM channels.
    ld d,0xB0
    ld b,9
opl4_mute_fm0:
    ld a,d
    out (PORT_OPL4_FM0_A),a
    xor a
    out (PORT_OPL4_FM0_D),a
    call opl4_fm_wait
    inc d
    djnz opl4_mute_fm0
    ld d,0xB0
    ld b,9
opl4_mute_fm1:
    ld a,d
    out (PORT_OPL4_FM1_A),a
    xor a
    out (PORT_OPL4_FM1_D),a
    call opl4_fm_wait
    inc d
    djnz opl4_mute_fm1

    ; Attenuate and damp all 24 wave slots.
    ld d,0x50
    ld b,24
opl4_mute_wave_level:
    ld a,d
    ld e,0xFF
    call opl4_write_wave
    inc d
    djnz opl4_mute_wave_level
    ld d,0x68
    ld b,24
opl4_mute_wave_key:
    ld a,d
    ld e,0x40
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
    ld b,16
opl4_wave_wait_loop:
    in a,(PORT_OPL4_WAVE_A)
    djnz opl4_wave_wait_loop
    pop bc
    ret

opl4_fm_wait:
    push bc
    ld b,16
opl4_fm_wait_loop:
    in a,(PORT_OPL4_FM0_A)
    djnz opl4_fm_wait_loop
    pop bc
    ret

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
mwk_signature:         db 'M','B','M','S',0x10
opl4_present: db 0

; Package lifecycle reset lives in the remaining high page-0 helper space.
ui_reset_package_state:
    xor a
    ld (file_open),a
    ld (hot_segment_count),a
    ld (hot_needed_count),a
    ld (engine_ready),a
    ld (engine_running),a
    ld (hybrid_ready),a
    ld (file_cache_ready),a
    ld (template_cache_ready),a
    ld (template_segment_allocated),a
    ld (engine_p3_segment_allocated),a
    ld (hpol_map_allocated),a
    ld (mwk_segment_allocated),a
    ld (dynamic_profile),a
    ld (page2_runtime_profile),a
    ld (page3_workram_profile),a
    ld (dynamic_install_active),a
    ld (gateway_patch_flags),a
    ld (refresh_saved),a
    ld (stream_source),a
    ld (stream_vdp_guard),a
    ld (current_page),a
    ld (current_page+1),a
    ld (current_song_id),a
    ld (current_song_id+1),a
    ld a,0xFF
    ld (hot_write_mapped),a
    ld (hot_read_mapped),a
    ld hl,0xFFFF
    ld (ui_track_cache_top),hl
    ret

opl4_module_end:
