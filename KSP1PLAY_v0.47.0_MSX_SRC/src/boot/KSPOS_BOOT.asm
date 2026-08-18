DISKROM_CALLF             equ 0F37Dh
MSX_PRIMARY_SLOT_REGISTER equ 0A8h
MAPPER_PAGE1_PORT         equ 0FDh
SECONDARY_SLOT_REGISTER   equ 0FFFFh
BOOT_SYSTEM_STACK         equ 0F51Fh
BOOT_ERROR_STATE          equ 0C100h
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

    ld sp,BOOT_SYSTEM_STACK
    in a,(MAPPER_PAGE1_PORT)
    ld (saved_p1_segment),a
    ld de,fcb
    ld c,0x0F
    call DISKROM_CALLF
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
    call DISKROM_CALLF
    ld hl,KSPBOOT_SIZE
    ld de,fcb
    ld c,0x27
    call DISKROM_CALLF
    or a
    jp nz,error

    ; Re-expose main RAM in page 1, then finish from the loaded page-1 stub.
    ld a,(RAMAD1)
    ld b,a
    bit 7,a
    jp z,map_primary
    ld a,(SECONDARY_SLOT_REGISTER)
    cpl
    and 0xF3
    ld c,a
    ld a,b
    and 0x0C
    or c
    ld (SECONDARY_SLOT_REGISTER),a
map_primary:
    in a,(MSX_PRIMARY_SLOT_REGISTER)
    and 0xF3
    ld c,a
    ld a,b
    and 3
    rlca
    rlca
    or c
    out (MSX_PRIMARY_SLOT_REGISTER),a
    ld a,(saved_p1_segment)
    out (MAPPER_PAGE1_PORT),a
    jp FINALIZER_SOURCE
error:
    ld (BOOT_ERROR_STATE),a
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
