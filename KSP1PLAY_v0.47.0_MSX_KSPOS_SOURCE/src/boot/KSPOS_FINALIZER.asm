KSPOS_RESIDENT_ROMUSE_OPERAND equ 0xC0AB
DISK_ERROR_POINTER equ 0xF323
DISK_ABORT_VECTOR equ 0xF1E6
org FINALIZER_SOURCE
kspos_finalize:
    ; Preserve the DiskROM ROMUSE helper before replacing the boot-sector image.
    ld hl,(0xC0C8)
    push hl

    ; Execute from page 1 while replacing the temporary sector-0 image in page 3.
    ld hl,RESIDENT_SOURCE
    ld de,0xC000
    ld bc,RESIDENT_SIZE
    ldir

    ; Complete the runtime DiskROM callback installation.
    pop hl
    ld (KSPOS_RESIDENT_ROMUSE_OPERAND),hl
    ld hl,0xC0A8
    ld (DISK_ERROR_POINTER),hl
    ld hl,0xC0B8
    ld (DISK_ABORT_VECTOR),hl

    ld a,0xC3
    ld (0x0005),a
    ld hl,0x0060
    ld (0x0006),hl
    xor a
    ld (0x0080),a
    ei
    jp 0x0100
kspos_finalizer_end:
