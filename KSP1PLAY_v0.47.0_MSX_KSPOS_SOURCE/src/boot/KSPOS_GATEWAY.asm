org 0x0060
kspos_bdos:
    ld a,c
    or a
    jp z,0xC0C0
    jp 0xC000

org 0x006B
kspos_info:
    db 'KPOS'
kspos_api_version:    db 1
kspos_flags:          db 0
kspos_total_segments: db 0
kspos_free_segments:  db 0
kspos_player_p0:      db 0
kspos_runtime_p0:     db 0
kspos_original_p3:    db 0
kspos_engine_p3:      db 0
kspos_unavail_count:  db 1
kspos_range0_start:   dw 0x0000
kspos_range0_end:     dw 0x01FF
kspos_range1_start:   dw 0xFFFF
kspos_range1_end:     dw 0xFFFF

org 0x0081
kspos_call_init:
    ex af,af'
    exx
    ld b,0
    jp kspos_call_common
kspos_call_play:
    ex af,af'
    exx
    ld b,1
    jp kspos_call_common
kspos_call_stop:
    ex af,af'
    exx
    ld b,2
kspos_call_common:
    ld hl,0
    add hl,sp
    ld (kspos_saved_player_sp),hl
    ld sp,0x0200
    ld a,(kspos_runtime_p0)
    out (0xFC),a
    ld (kspos_saved_player_sp),hl
    ld a,(kspos_flags)
    and 1
    jp z,kspos_page3_ready
    ld a,(kspos_engine_p3)
    out (0xFF),a
kspos_page3_ready:
    ld hl,kspos_after_engine
    push hl
    ld a,b
    or a
    jp z,kspos_target_init_select
    dec a
    jp z,kspos_target_play_select
    ld hl,(kspos_target_stop)
    jp kspos_target_ready
kspos_target_init_select:
    ld hl,(kspos_target_init)
    jp kspos_target_ready
kspos_target_play_select:
    ld hl,(kspos_target_play)
kspos_target_ready:
    push hl
    exx
    ex af,af'
    ret
kspos_after_engine:
    di
    ld a,(kspos_flags)
    and 1
    jp z,kspos_page3_restored
    ld a,(kspos_original_p3)
    out (0xFF),a
kspos_page3_restored:
    ld hl,(kspos_saved_player_sp)
    ld a,(kspos_player_p0)
    out (0xFC),a
    ld sp,hl
    ret

org 0x00F0
kspos_target_init:     dw 0
kspos_target_play:     dw 0
kspos_target_stop:     dw 0
kspos_saved_player_sp: dw 0
kspos_gateway_end:
