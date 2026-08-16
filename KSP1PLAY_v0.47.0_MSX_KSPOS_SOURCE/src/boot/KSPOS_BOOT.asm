RAMAD1 equ 0xF342
DISK_ABORT_VECTOR equ 0xF1E6
org 0xC01E
entry:
    ret nc

    ; DiskROM boot contract:
    ;   DE = ROMUSE helper address
    ;   HL = address where the boot sector installs its disk-error callback.
    ld (saved_romuse),de
    ld (boot_diskrom_operand),de
    push hl
    ld de,boot_disk_error
    pop hl
    ld (hl),e
    inc hl
    ld (hl),d
    ld hl,boot_disk_abort
    ld (DISK_ABORT_VECTOR),hl

    ld sp,0xF51F
    in a,(0xFD)
    ld (saved_p1_segment),a
    ld de,fcb
    ld c,0x0F
    call 0xF37D
    or a
    jp nz,error
    ld hl,1
    ld (fcb+14),hl
    xor a
    ld (fcb+33),a
    ld (fcb+34),a
    ld (fcb+35),a
    ld (fcb+36),a
    ld de,0x0060
    ld c,0x1A
    call 0xF37D
    ld hl,KSPBOOT_SIZE
    ld de,fcb
    ld c,0x27
    call 0xF37D
    or a
    jp nz,error

    ; Re-expose main RAM in page 1, then finish from the loaded page-1 stub.
    ld a,(RAMAD1)
    ld b,a
    bit 7,a
    jp z,map_primary
    ld a,(0xFFFF)
    cpl
    and 0xF3
    ld c,a
    ld a,b
    and 0x0C
    or c
    ld (0xFFFF),a
map_primary:
    in a,(0xA8)
    and 0xF3
    ld c,a
    ld a,b
    and 3
    rlca
    rlca
    or c
    out (0xA8),a
    ld a,(saved_p1_segment)
    out (0xFD),a
    jp FINALIZER_SOURCE
error:
    ld (0xC100),a
    di
hang:
    halt
    jp hang
saved_p1_segment: db 0

; Handler used while the boot sector itself is resident.
org 0xC0A8
boot_disk_error:
    ld e,b
    ret nz
    db 0xCD
boot_diskrom_operand:
    dw 0
    ld c,2
    ret
org 0xC0B8
boot_disk_abort:
    jp error

org 0xC0C8
saved_romuse: dw 0

org 0xC0D0
fcb:
    db 0,'KSPBOOT ','BIN'
    ds 25,0
end:
