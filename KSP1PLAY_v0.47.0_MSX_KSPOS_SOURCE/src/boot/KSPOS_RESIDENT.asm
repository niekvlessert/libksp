; KSPOS_RESIDENT.asm - readable source for KSP1PLAY v0.47.0
;
; Provenance:
;   Recovered byte-for-byte from KSPBOOT.BIN on KSP1PLAY_v0.47.1_BASE.DSK.
;   The disk identifies its executable core as KSP1PLAY v0.47.0.
;
; IMPORTANT:
;   Symbol names below are descriptive names, not claimed to be
;   the original development labels.  Comments describe observed behavior.
;
; Build target: 369 bytes, loaded at C000h.

org 0xC000

KSPOS_DISK_STACK equ 0xC200
PORT_VDP_CTRL    equ 0x99
PORT_VDP_PALETTE equ 0x9A

; ---------------------------------------------------------------------------
; DOS1 / DiskROM bridge
; ---------------------------------------------------------------------------
; This block is byte-identical to the earlier KSPOS resident implementation.
; F37Dh performs the inter-slot call to the master DiskROM.  The player stack
; is moved out of page 0 because CALLF/DiskROM activity can temporarily remap it.
kspos_disk_call:
    ld (saved_input_hl),hl
    ld hl,0
    add hl,sp
    ld (saved_player_sp),hl
    ld hl,(saved_input_hl)
    ld sp,KSPOS_DISK_STACK
    call 0xF37D
    ld (saved_result_hl),hl
    ld hl,(saved_player_sp)
    ld sp,hl
    ld hl,(saved_result_hl)
    ret

; Two stable entry points added by the later player.  Their exact callers live
; in the v0.47 COM.  They enter the VDP synchronization/state routines below.
org 0xC01E
kspos_vdp_begin:
    jp kspos_vdp_begin_impl

org 0xC027
kspos_vdp_sync:
    jp kspos_vdp_sync_impl

; C04Ch: wait for the VDP-side transition to become safe, then restore R#0=4.
; The EI here is part of the exact reference binary and deliberately occurs only
; after the VDP state has been restored.
org 0xC04C
kspos_vdp_restore_text2_r0:
    call kspos_vdp_wait_safe
    ld a,0x04
    ld c,0
    call kspos_vdp_write_reg
    ei
    ret

; HL -> 32-byte palette payload.  Select palette index 0 (R#16=0), then stream
; all 16 two-byte palette entries to port 9Ah.
kspos_vdp_upload_palette32:
    xor a
    ld c,0x10
    call kspos_vdp_write_reg
    ld b,0x20
kspos_vdp_upload_palette32_loop:
    ld a,(hl)
    out (PORT_VDP_PALETTE),a
    inc hl
    djnz kspos_vdp_upload_palette32_loop
    ret

; Program the intermediate VDP state used by the transition/synchronization
; path.  The value at C0D1h is the retained R#7 foreground/background byte.
kspos_vdp_set_intermediate_mode:
    ld a,0x16
    ld c,0
    call kspos_vdp_write_reg
    ld a,0x60
    ld c,1
    call kspos_vdp_write_reg
    ld a,0x3F
    ld c,2
    call kspos_vdp_write_reg
    ld a,(kspos_vdp_r7_value)
    ld c,7
    jp kspos_vdp_write_reg

; Kept as a stable call slot in the resident ABI.
kspos_vdp_wait_safe:
    jp kspos_vdp_wait_safe_impl

; C087h: direct V99x8 register write.  A=value, C=register number.
kspos_vdp_write_reg:
    out (PORT_VDP_CTRL),a
    ld a,c
    or 0x80
    out (PORT_VDP_CTRL),a
    ret

; ---------------------------------------------------------------------------
; DiskROM callbacks and reboot path (same ABI locations as older KSPOS)
; ---------------------------------------------------------------------------
org 0xC0A8
kspos_disk_error:
    ld e,b
    ret nz
    db 0xCD
diskrom_romuse_operand:
    dw 0
    ld c,2
    ret

org 0xC0B8
kspos_disk_abort:
    ld a,0xFF
    scf
    ld hl,(saved_player_sp)
    ld sp,hl
    ret

org 0xC0C0
kspos_exit:
    di
    in a,(0xA8)
    and 0xFC
    out (0xA8),a
    jp 0x0000

; C0D1h is written/read by the VDP transition code as the R#7 value.
; C0D2h is a one-byte first-sync/armed state flag.
org 0xC0D1
kspos_vdp_r7_value: db 0
kspos_vdp_sync_state: db 0

; Keep the original DiskROM bridge workspace ABI fixed.
org 0xC0E0
saved_player_sp: dw 0
saved_input_hl:  dw 0
saved_result_hl: dw 0

; ---------------------------------------------------------------------------
; Later VDP synchronization code
; ---------------------------------------------------------------------------
org 0xC100
kspos_vdp_begin_impl:
    ; Select VDP status register 3, clear local synchronization state, disable
    ; interrupts, then enter the intermediate display mode.
    ld c,0x13
    call kspos_vdp_write_reg
    xor a
    ld (kspos_vdp_sync_state),a
    di
    jp kspos_vdp_set_intermediate_mode

kspos_vdp_sync_impl:
    ; On calls after the first one, select status register 0 and wait for bit 7
    ; before reprogramming the intermediate mode.  The first call only arms the
    ; state byte and proceeds to the second phase.
    ld a,(kspos_vdp_sync_state)
    or a
    jp z,kspos_vdp_sync_first
    xor a
    ld c,0x0F
    call kspos_vdp_write_reg
    in a,(PORT_VDP_CTRL)
kspos_vdp_wait_status0_bit7:
    in a,(PORT_VDP_CTRL)
    and 0x80
    jp z,kspos_vdp_wait_status0_bit7
    call kspos_vdp_set_intermediate_mode
    jp kspos_vdp_sync_phase2

kspos_vdp_sync_first:
    inc a
    ld (kspos_vdp_sync_state),a

kspos_vdp_sync_phase2:
    ; Select status register 1 and wait for bit 0, then wait for the additional
    ; VDP-safe condition at C141h.
    ld a,1
    ld c,0x0F
    call kspos_vdp_write_reg
    in a,(PORT_VDP_CTRL)
kspos_vdp_wait_status1_bit0:
    in a,(PORT_VDP_CTRL)
    and 1
    jp z,kspos_vdp_wait_status1_bit0
    call kspos_vdp_wait_safe
    ret

kspos_vdp_wait_safe_impl:
    ; Select status register 2 and wait for bit 5.  Once safe, restore the VDP
    ; registers used by KSP1PLAY's 80-column TEXT 2 presentation and restore
    ; status register selection to 0.
    ld a,2
    ld c,0x0F
    call kspos_vdp_write_reg
kspos_vdp_wait_status2_bit5:
    in a,(PORT_VDP_CTRL)
    and 0x20
    jp z,kspos_vdp_wait_status2_bit5

    ld a,0x14
    ld c,0
    call kspos_vdp_write_reg
    ld a,0x70
    ld c,1
    call kspos_vdp_write_reg
    ld a,0x03
    ld c,2
    call kspos_vdp_write_reg
    ld a,0xF0
    ld c,7
    call kspos_vdp_write_reg
    xor a
    ld c,0x0F
    jp kspos_vdp_write_reg

kspos_resident_end:
