BOOT_SAVED_ROMUSE         equ 0C0C8h
KSPOS_RUNTIME_DESTINATION equ 0C000h
KSPOS_DISK_ERROR_ENTRY    equ 0C0A8h
KSPOS_DISK_ABORT_ENTRY    equ 0C0B8h
BDOS_VECTOR_OPCODE        equ 00005h
BDOS_VECTOR_TARGET        equ 00006h
DEFAULT_FCB_DRIVE         equ 00080h
KSPOS_GATEWAY_ENTRY       equ 00060h
PLAYER_ENTRY              equ 00100h
KSPOS_RESIDENT_ROMUSE_OPERAND equ 0xC0AB
DISK_ERROR_POINTER equ 0xF323
DISK_ABORT_VECTOR equ 0xF1E6
org FINALIZER_SOURCE
kspos_finalize:
    ; Preserve the DiskROM ROMUSE helper before replacing the boot-sector image.
    ld hl,(BOOT_SAVED_ROMUSE)
    push hl

    ; Execute from page 1 while replacing the temporary sector-0 image in page 3.
    ld hl,RESIDENT_SOURCE
    ld de,KSPOS_RUNTIME_DESTINATION
    ld bc,RESIDENT_SIZE
    ldir

    ; Complete the runtime DiskROM callback installation.
    pop hl
    ld (KSPOS_RESIDENT_ROMUSE_OPERAND),hl
    ld hl,KSPOS_DISK_ERROR_ENTRY
    ld (DISK_ERROR_POINTER),hl
    ld hl,KSPOS_DISK_ABORT_ENTRY
    ld (DISK_ABORT_VECTOR),hl

    ld a,0xC3
    ld (BDOS_VECTOR_OPCODE),a
    ld hl,KSPOS_GATEWAY_ENTRY
    ld (BDOS_VECTOR_TARGET),hl
    xor a
    ld (DEFAULT_FCB_DRIVE),a
    ei
    jp PLAYER_ENTRY
kspos_finalizer_end:
