
        org 04000h

STREAM_PAGE     equ 06800h
STREAM_DATA     equ 06802h
HEADER_SIZE     equ 39
DYNAMIC_GATEWAY equ 07FF0h

; Global state, preserved by the dynamic-page gateway.
PTR             equ 05F00h
PAGE_END        equ 05F02h
PAGE_INDEX      equ 05F04h
TEMPO           equ 05F06h
ACCUM           equ 05F08h
SPEED           equ 05F0Ah
ROW_TICK        equ 05F0Bh
ENDED           equ 05F0Ch
CUR_CH          equ 05F0Dh
TICK_NOW        equ 05F0Eh
PITCH_DIRTY     equ 05F0Fh
OUT_PERIOD      equ 05F10h
EV_NOTE_KIND    equ 05F12h
EV_TONE         equ 05F13h
EV_PERIOD       equ 05F14h
EV_PLO          equ 05F16h
EV_PHI          equ 05F17h
EV_DVOL         equ 05F18h
EV_DELAY        equ 05F19h
EV_TOKEN        equ 05F1Ah
EV_HAS_VOL      equ 05F1Bh
EV_NOTE_PRESENT equ 05F20h
SECOND_FX       equ 05F1Ch
FX_SLOT         equ 05F1Dh
FAST_VOL        equ 05F1Eh
ROW_COUNT_TMP   equ 05F1Fh
LINEAR_XM       equ 05F21h
RETRIG_COUNT    equ 05F22h      ; 24 bytes: IT Qxy countdowns
PAT_DELAY       equ 05F3Ah
TICK_DELAY      equ 05F3Bh
HOLD_ROW        equ 05F3Ch

PERIOD_Q        equ 06000h      ; 24 words
TARGET_Q        equ 06030h      ; 24 words
VOLUME          equ 06060h      ; 24 bytes
WAVE            equ 06078h      ; 24 bytes, custom tone 0..63
KEYSTATE        equ 06090h      ; 24 bytes
CMD1            equ 060A8h
PAR1            equ 060C0h
CMD2            equ 060D8h
PAR2            equ 060F0h
VIBSPD          equ 06108h
VIBDEP          equ 06120h
VIBPH           equ 06138h
ARP1            equ 06150h      ; 24 words
ARP2            equ 06180h      ; 24 words
PAN             equ 061B0h
DELAY_TICK      equ 061C8h      ; FF = none
PEND_KIND       equ 061E0h
PEND_TONE       equ 061F8h
PEND_PERIOD     equ 06210h      ; 24 words
PEND_PLO        equ 06240h
PEND_PHI        equ 06258h
PEND_VOL        equ 06270h
TREMOR_COUNT    equ 06400h
TREMSPD         equ 06418h
TREMDEP         equ 06430h
TREMPH          equ 06448h
TREMTYPE        equ 06460h
VIBTYPE         equ 06478h
GLISS           equ 06490h
PAGE_TOTAL_CFG  equ 063FCh      ; patched by converter
STATE_CLEAR     equ 05F00h
STATE_CLEAR_END equ 06288h
EXT_STATE_END   equ 064A8h

CMD_A           equ 1
CMD_D           equ 4
CMD_E           equ 5
CMD_F           equ 6
CMD_G           equ 7
CMD_H           equ 8
CMD_I           equ 9
CMD_J           equ 10
CMD_O           equ 15
CMD_Q           equ 17
CMD_R           equ 18
CMD_T           equ 20
CMD_X           equ 24
CMD_CUT         equ 27
CMD_GLISS       equ 30
CMD_ST3_PATDELAY equ 35
CMD_ST3_VIBWAVE equ 36
CMD_ST3_TREMWAVE equ 37
CMD_ST3_FINETUNE equ 38
CMD_ST3_TICKDELAY equ 39

init:
        xor a
        ld hl,STATE_CLEAR
        ld de,STATE_CLEAR+1
        ld bc,STATE_CLEAR_END-STATE_CLEAR-1
        ld (hl),a
        ldir
        xor a
        ld hl,TREMOR_COUNT
        ld de,TREMOR_COUNT+1
        ld bc,EXT_STATE_END-TREMOR_COUNT-1
        ld (hl),a
        ldir
        ld hl,DELAY_TICK
        ld b,24
        ld a,0FFh
init_delay_ff:
        ld (hl),a
        inc hl
        djnz init_delay_ff
        ld hl,0000h
        ld (PAGE_INDEX),hl
        ld hl,STREAM_DATA+HEADER_SIZE
        ld (PTR),hl
        call set_page_end
        ld a,(STREAM_DATA+6)
        or a
        jr nz,init_speed_ok
        inc a
init_speed_ok:
        ld (SPEED),a
        ld a,(STREAM_DATA+7)
        ld b,a
        and 1
        ld (FAST_VOL),a
        ld a,b
        and 2
        ld (LINEAR_XM),a
        ld hl,(STREAM_DATA+8)
        ld (TEMPO),hl
        ld hl,STREAM_DATA+14
        ld de,PAN
        ld bc,24
        ldir
        call apply_init_aliases
        ; OPL4 memory/header bank and mixer setup.
        ld d,02h
        ld e,10h
        call opl4_write_de
        ld d,0F8h
        ld e,00h
        call opl4_write_de
        ld d,0F9h
        ld e,00h
        call opl4_write_de
        ret

play:
        ld a,(ENDED)
        or a
        ret nz
        ld hl,(ACCUM)
        ld de,(TEMPO)
        add hl,de
        ld (ACCUM),hl
play_loop:
        ld hl,(ACCUM)
        ld de,150
        or a
        sbc hl,de
        jr c,play_done
        ld (ACCUM),hl
        call process_tick
        ld a,(ENDED)
        or a
        ret nz
        jr play_loop
play_done:
        ret

stop:
        ld a,1
        ld (ENDED),a
        call silence
        ret

process_tick:
        ld a,(ROW_TICK)
        or a
        jr nz,process_have_row
        ld a,(HOLD_ROW)
        or a
        jr z,process_parse_new_row
        xor a
        ld (HOLD_ROW),a
        jr process_have_row
process_parse_new_row:
        call parse_row
        ld a,(ENDED)
        or a
        ret nz
process_have_row:
        ld a,(ROW_TICK)
        ld (TICK_NOW),a
        call process_all_channels
        ld a,(ROW_TICK)
        inc a
        ld b,a
        ld a,(SPEED)
        ld c,a
        ld a,(TICK_DELAY)
        add a,c
        cp b
        jr c,process_row_done
        jr z,process_row_done
        ld a,b
        ld (ROW_TICK),a
        ret
process_row_done:
        ld a,(PAT_DELAY)
        or a
        jr z,process_row_really_done
        dec a
        ld (PAT_DELAY),a
        ld a,1
        ld (HOLD_ROW),a
        xor a
        ld (ROW_TICK),a
        ret
process_row_really_done:
        xor a
        ld (ROW_TICK),a
        ld (TICK_DELAY),a
        ret

parse_row:
        ; Clear row-local effects and expire delayed actions from a malformed prior row.
        xor a
        ld (PAT_DELAY),a
        ld (TICK_DELAY),a
        ld hl,CMD1
        ld de,CMD1+1
        ld bc,96-1
        ld (hl),a
        ldir
        ld hl,DELAY_TICK
        ld b,24
        ld a,0FFh
parse_delay_ff:
        ld (hl),a
        inc hl
        djnz parse_delay_ff
        call read_stream_byte
        jp c,stream_end
        cp 0FFh
        jp z,stream_end
        ld (ROW_COUNT_TMP),a
        or a
        ret z
parse_event_loop:
        call read_stream_byte
        jp c,stream_end
        ld (EV_TOKEN),a
        and 01Fh
        ld (CUR_CH),a
        xor a
        ld (EV_NOTE_KIND),a
        ld (EV_HAS_VOL),a
        ld (EV_NOTE_PRESENT),a
        ld a,0FFh
        ld (EV_DVOL),a
        ld a,(EV_TOKEN)
        and 020h
        jr z,parse_no_note
        ld a,1
        ld (EV_NOTE_PRESENT),a
        call parse_note
        jp c,stream_end
parse_no_note:
        ld a,(EV_TOKEN)
        and 040h
        jr z,parse_no_volume
        call read_stream_byte
        jp c,stream_end
        ld (EV_HAS_VOL),a
        call set_volume_a
parse_no_volume:
        ld a,(EV_TOKEN)
        and 080h
        jr z,parse_no_effect
        call parse_effects
        jp c,stream_end
parse_no_effect:
        call finish_event_note
        ld a,(ROW_COUNT_TMP)
        dec a
        ld (ROW_COUNT_TMP),a
        jr nz,parse_event_loop
        ret

parse_note:
        call read_stream_byte
        ret c
        ld (EV_NOTE_KIND),a
        cp 0FEh
        ret z
        cp 0FFh
        jr z,parse_note_delayed_off
        cp 080h
        jr z,parse_note_porta
        cp 081h
        jr z,parse_note_delayed_porta
        cp 082h
        jr z,parse_note_porta_swap
        ; Stream v4: 00 normal / 40 delayed normal, followed by a
        ; separate custom-wave index (0..127 => OPL4 384..511).
        ; Keep the descriptor in B; read_stream_byte preserves BC.
        ld b,a
        call read_stream_byte
        ret c
        ld (EV_TONE),a
        call read_word_to_ev_period
        ret c
        call read_stream_byte
        ret c
        ld (EV_PLO),a
        call read_stream_byte
        ret c
        ld (EV_PHI),a
        ld a,b
        and 040h
        ret z
        call read_stream_byte
        ret c
        ld (EV_DVOL),a
        call read_stream_byte
        ret c
        ld (EV_DELAY),a
        ret
parse_note_porta:
        jr read_word_to_ev_period
parse_note_porta_swap:
        call read_stream_byte
        ret c
        ld (EV_TONE),a
        jr read_word_to_ev_period
parse_note_delayed_porta:
        call read_word_to_ev_period
        ret c
        call read_stream_byte
        ret c
        ld (EV_DVOL),a
        call read_stream_byte
        ret c
        ld (EV_DELAY),a
        ret
parse_note_delayed_off:
        call read_stream_byte
        ret c
        ld (EV_DVOL),a
        call read_stream_byte
        ret c
        ld (EV_DELAY),a
        ret

read_word_to_ev_period:
        ; read_stream_byte uses HL internally, so do not keep the first byte in L
        ; across the second call. DE is explicitly preserved by read_stream_byte.
        call read_stream_byte
        ret c
        ld e,a
        call read_stream_byte
        ret c
        ld d,a
        ld (EV_PERIOD),de
        or a
        ret

parse_effects:
        xor a
        ld (FX_SLOT),a
parse_effects_loop:
        call parse_one_effect
        ret c
        ld a,(SECOND_FX)
        or a
        ret z
        jr parse_effects_loop

parse_one_effect:
        call read_stream_byte
        ret c
        ld b,a
        and 080h
        ld (SECOND_FX),a
        ld a,b
        and 07Fh
        ld d,a                 ; command
        call read_stream_byte
        ret c
        ld e,a                 ; parameter
        ld a,d
        cp CMD_A
        jr nz,fx_not_speed
        ld a,e
        or a
        ret z
        ld (SPEED),a
        or a
        ret
fx_not_speed:
        cp CMD_T
        jr nz,fx_not_tempo
        ld a,e
        cp 32
        ret c
        ld l,a
        ld h,0
        ld (TEMPO),hl
        or a
        ret
fx_not_tempo:
        cp CMD_X
        jr nz,fx_not_pan
        ld a,e
        call set_pan_from_tracker
        or a
        ret
fx_not_pan:
        cp CMD_GLISS
        jr nz,fx_not_gliss
        ld a,e
        ld hl,GLISS
        call ptr8_cur
        ld (hl),a
        or a
        ret
fx_not_gliss:
        cp CMD_ST3_VIBWAVE
        jr nz,fx_not_vibwave
        ld a,e
        and 03h
        ld hl,VIBTYPE
        call ptr8_cur
        ld (hl),a
        or a
        ret
fx_not_vibwave:
        cp CMD_ST3_TREMWAVE
        jr nz,fx_not_tremwave
        ld a,e
        and 03h
        ld hl,TREMTYPE
        call ptr8_cur
        ld (hl),a
        or a
        ret
fx_not_tremwave:
        cp CMD_ST3_PATDELAY
        jr nz,fx_not_patdelay
        ld a,e
        ld (PAT_DELAY),a
        or a
        ret
fx_not_patdelay:
        cp CMD_ST3_TICKDELAY
        jr nz,fx_not_tickdelay
        ld a,e
        ld (TICK_DELAY),a
        or a
        ret
fx_not_tickdelay:
        ; H updates nibble memory immediately; its resolved parameter already has both nibbles.
        cp CMD_H
        jr nz,fx_store
        ld a,e
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        push de
        call store_vib_speed
        pop de
        ld a,e
        and 00Fh
        push de
        call store_vib_depth
        pop de
fx_store:
        ld a,(FX_SLOT)
        cp 2
        jr nc,fx_extra
        or a
        jr nz,fx_store_2
        ld hl,CMD1
        call ptr8_cur
        ld (hl),d
        ld hl,PAR1
        call ptr8_cur
        ld (hl),e
        jr fx_store_inc
fx_store_2:
        ld hl,CMD2
        call ptr8_cur
        ld (hl),d
        ld hl,PAR2
        call ptr8_cur
        ld (hl),e
fx_store_inc:
        ld a,(FX_SLOT)
        inc a
        ld (FX_SLOT),a
fx_extra:
        ld a,d
        cp CMD_J
        jr nz,fx_check_finetune
        ; J carries two precomputed quarter-periods.
        call read_stream_byte
        ret c
        ld e,a
        call read_stream_byte
        ret c
        ld d,a
        ld hl,ARP1
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        call read_stream_byte
        ret c
        ld e,a
        call read_stream_byte
        ret c
        ld d,a
        ld hl,ARP2
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        jr fx_done
fx_check_finetune:
        cp CMD_ST3_FINETUNE
        jr nz,fx_done
        call read_stream_byte
        ret c
        ld e,a
        call read_stream_byte
        ret c
        ld d,a
        ld hl,ARP1
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
fx_done:
        or a
        ret

finish_event_note:
        ld a,(EV_NOTE_PRESENT)
        or a
        jr z,finish_no_note
        ld a,(EV_NOTE_KIND)
        cp 0FEh
        jr z,do_note_off
        cp 0FFh
        jr z,queue_delayed_note
        cp 080h
        jr z,do_porta_target
        cp 081h
        jr z,queue_delayed_note
        cp 082h
        jr z,do_porta_swap
        and 040h
        jr nz,queue_delayed_note
        jp do_normal_note
finish_no_note:
        ret

do_porta_target:
        ld hl,TARGET_Q
        call ptr16_cur
        ld de,(EV_PERIOD)
        ld (hl),e
        inc hl
        ld (hl),d
        ret

; Impulse Tracker S3M compatibility: a tone-portamento note with a different
; sample swaps to that sample and restarts it, while retaining the current
; pitch and using the new note only as the portamento target.
do_porta_swap:
        call do_porta_target
        ld a,(EV_TONE)
        ld hl,WAVE
        call ptr8_cur
        ld (hl),a
        call it_arm_retrig_on_note
        call keyoff_current
        ld a,(CUR_CH)
        add a,008h
        ld d,a
        ld a,(EV_TONE)
        add a,080h
        ld e,a
        call opl4_write_de
        jp keyon_current

; A note next to Qxy initializes IT's countdown and suppresses an immediate
; retrigger on the same tick. Bit 7 is a one-tick skip marker.
it_arm_retrig_on_note:
        ld hl,CMD1
        call ptr8_cur
        ld a,(hl)
        cp CMD_Q
        jr z,it_arm_retrig_cmd1
        ld hl,CMD2
        call ptr8_cur
        ld a,(hl)
        cp CMD_Q
        ret nz
        ld hl,PAR2
        jr it_arm_retrig_load
it_arm_retrig_cmd1:
        ld hl,PAR1
it_arm_retrig_load:
        call ptr8_cur
        ld a,(hl)
        and 0Fh
        or 080h
        ld b,a
        ld hl,RETRIG_COUNT
        call ptr8_cur
        ld (hl),b
        ret

do_note_off:
        jp keycut_current

queue_delayed_note:
        ld a,(EV_DELAY)
        ld hl,DELAY_TICK
        call ptr8_cur
        ld (hl),a
        ld a,(EV_NOTE_KIND)
        ld hl,PEND_KIND
        call ptr8_cur
        ld (hl),a
        ld a,(EV_TONE)
        ld hl,PEND_TONE
        call ptr8_cur
        ld (hl),a
        ld de,(EV_PERIOD)
        ld hl,PEND_PERIOD
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld a,(EV_PLO)
        ld hl,PEND_PLO
        call ptr8_cur
        ld (hl),a
        ld a,(EV_PHI)
        ld hl,PEND_PHI
        call ptr8_cur
        ld (hl),a
        ld a,(EV_DVOL)
        ld hl,PEND_VOL
        call ptr8_cur
        ld (hl),a
        ret

do_normal_note:
        ; Save base/target quarter-period and tone.
        call it_arm_retrig_on_note
        ld de,(EV_PERIOD)
        ld hl,PERIOD_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld hl,TARGET_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld a,(EV_TONE)
        ld hl,WAVE
        call ptr8_cur
        ld (hl),a
        xor a
        ld hl,VIBPH
        call ptr8_cur
        ld (hl),a
        ld hl,TREMPH
        call ptr8_cur
        ld (hl),a
        ld hl,TREMOR_COUNT
        call ptr8_cur
        ld (hl),a
        call keyoff_current
        ; Exact host-computed base pitch and wave number 384+tone.
        ld a,(CUR_CH)
        add a,020h
        ld d,a
        ld a,(EV_PLO)
        or 1
        ld e,a
        call opl4_write_de
        ld a,(CUR_CH)
        add a,008h
        ld d,a
        ld a,(EV_TONE)
        add a,080h
        ld e,a
        call opl4_write_de
        ld a,(CUR_CH)
        add a,038h
        ld d,a
        ld a,(EV_PHI)
        ld e,a
        call opl4_write_de
        jp keyon_current

process_all_channels:
        xor a
        ld (CUR_CH),a
process_ch_loop:
        call process_delayed
        ld hl,PERIOD_Q
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (OUT_PERIOD),de
        xor a
        ld (PITCH_DIRTY),a
        ; IT Qxy keeps its own countdown; there is no ST3 row-gap reset.
        ld hl,CMD1
        call ptr8_cur
        ld d,(hl)
        ld hl,PAR1
        call ptr8_cur
        ld e,(hl)
        call apply_effect_de
        ld hl,CMD2
        call ptr8_cur
        ld d,(hl)
        ld hl,PAR2
        call ptr8_cur
        ld e,(hl)
        call apply_effect_de
        ld a,(PITCH_DIRTY)
        or a
        call nz,emit_pitch_approx
        ld a,(CUR_CH)
        inc a
        ld (CUR_CH),a
        cp 24
        jr c,process_ch_loop
        ret

; Retained as an unreachable compatibility stub; IT does not use the
; ST3 row-without-Q counter reset.
it_unused_retrig_row_check:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld hl,CMD1
        call ptr8_cur
        ld a,(hl)
        cp CMD_Q
        ret z
        ld hl,CMD2
        call ptr8_cur
        ld a,(hl)
        cp CMD_Q
        ret z
        xor a
        ld hl,RETRIG_COUNT
        call ptr8_cur
        ld (hl),a
        ret

process_delayed:
        ld hl,DELAY_TICK
        call ptr8_cur
        ld a,(hl)
        cp 0FFh
        ret z
        ld b,a
        ld a,(TICK_NOW)
        cp b
        ret nz
        ld (hl),0FFh
        ld hl,PEND_VOL
        call ptr8_cur
        ld a,(hl)
        cp 0FFh
        jr z,delay_no_vol
        call set_volume_a
delay_no_vol:
        ld hl,PEND_KIND
        call ptr8_cur
        ld a,(hl)
        cp 0FFh
        jp z,keyoff_current
        cp 081h
        jr z,delay_porta
        ; restore pending normal fields into event globals and trigger
        ld hl,PEND_TONE
        call ptr8_cur
        ld a,(hl)
        ld (EV_TONE),a
        ld hl,PEND_PERIOD
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (EV_PERIOD),de
        ld hl,PEND_PLO
        call ptr8_cur
        ld a,(hl)
        ld (EV_PLO),a
        ld hl,PEND_PHI
        call ptr8_cur
        ld a,(hl)
        ld (EV_PHI),a
        jp do_normal_note
delay_porta:
        ld hl,PEND_PERIOD
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld hl,TARGET_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ret

apply_effect_de:
        ld a,d
        or a
        ret z
        cp CMD_D
        jp z,effect_volume_slide
        cp CMD_E
        jp z,effect_pitch_down
        cp CMD_F
        jp z,effect_pitch_up
        cp CMD_G
        jp z,effect_porta
        cp CMD_H
        jp z,effect_vibrato
        cp CMD_I
        jp z,effect_tremor
        cp CMD_J
        jp z,effect_arpeggio
        cp CMD_Q
        jp z,effect_retrig
        cp CMD_R
        jp z,effect_tremolo
        cp CMD_ST3_FINETUNE
        jp z,effect_finetune
        cp CMD_CUT
        jp z,effect_note_cut
        ret

effect_volume_slide:
        ; E=parameter. Fine forms happen on tick zero, ordinary forms afterwards.
        ld a,e
        and 0F0h
        ld b,a
        ld a,e
        and 00Fh
        ld c,a
        ld a,b
        cp 0F0h
        jr nz,vol_not_fine_down
        ld a,c
        or a
        jr z,vol_regular          ; D F0 is ordinary slide-up 15, not fine-down 0
        cp 0Fh
        ret z                     ; D FF is ambiguous/no-op in ST3
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,c
        jp volume_sub_a
vol_not_fine_down:
        ld a,c
        cp 0Fh
        jr nz,vol_regular
        ld a,b
        or a
        jr z,vol_regular          ; D 0F is ordinary slide-down 15, not fine-up 0
        cp 0F0h
        ret z                     ; D FF is ambiguous/no-op in ST3
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,b
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        jp volume_add_a
vol_regular:
        ld a,(TICK_NOW)
        or a
        jr nz,vol_regular_do
        ld a,(FAST_VOL)
        or a
        ret z
        ; fast-slide compatibility only makes D0F/DF0 active on tick zero.
        ld a,b
        or a
        jr nz,vol_fast_up_test
        ld a,c
        cp 0Fh
        ret nz
        ld a,c
        jp volume_sub_a
vol_fast_up_test:
        cp 0F0h
        ret nz
        ld a,c
        or a
        ret nz
        ld a,0Fh
        jp volume_add_a
vol_regular_do:
        ld a,b
        or a
        jr z,vol_slide_down
        ld a,c
        or a
        jr nz,vol_slide_down
        ld a,b
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        jp volume_add_a
vol_slide_down:
        ld a,c
        or a
        ret z
        jp volume_sub_a

volume_add_a:
        ld b,a
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        add a,b
        cp 65
        jr c,volume_store
        ld a,64
volume_store:
        ld (hl),a
        jp emit_volume_current
volume_sub_a:
        ld b,a
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        cp b
        jr nc,volume_sub_ok
        xor a
        jr volume_store
volume_sub_ok:
        sub b
        jr volume_store

effect_pitch_down:
        ld a,e
        call slide_delta_q
        ret c
        ex de,hl                 ; DE=delta q
        ld hl,PERIOD_Q
        call ptr16_cur
        ld a,(hl)
        ld c,a
        inc hl
        ld a,(hl)
        ld b,a
        ld h,b
        ld l,c
        add hl,de
        jr nc,pitch_down_store
        ld hl,0FFFFh
pitch_down_store:
        call store_period_hl
        ret

effect_pitch_up:
        ld a,e
        call slide_delta_q
        ret c
        ex de,hl                 ; DE=delta
        ld hl,PERIOD_Q
        call ptr16_cur
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld h,b
        ld l,c
        or a
        sbc hl,de
        jr nc,pitch_up_nonzero
        ld hl,1
pitch_up_nonzero:
        ld a,h
        or l
        jr nz,pitch_up_store
        inc hl
pitch_up_store:
        call store_period_hl
        ret

; Input A=slide parameter, output HL=quarter-period delta, CF=0 when active.
; CF=1 means no slide on this tick.
slide_delta_q:
        ld b,a
        and 0F0h
        cp 0F0h
        jr z,slide_fine
        cp 0E0h
        jr z,slide_extra_fine
        ld a,(TICK_NOW)
        or a
        jr z,slide_inactive
        ld a,b
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        or a
        ret
slide_fine:
        ld a,(TICK_NOW)
        or a
        jr nz,slide_inactive
        ld a,b
        and 0Fh
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        or a
        ret
slide_extra_fine:
        ld a,(TICK_NOW)
        or a
        jr nz,slide_inactive
        ld a,b
        and 0Fh
        ld l,a
        ld h,0
        or a
        ret
slide_inactive:
        scf
        ret

store_period_hl:
        ld (OUT_PERIOD),hl
        push hl
        ex de,hl
        ld hl,PERIOD_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        pop hl
        ld a,1
        ld (PITCH_DIRTY),a
        ret

effect_porta:
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        or a
        ret z
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        push hl                   ; step
        ld hl,PERIOD_Q
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)                 ; DE=current
        ld hl,TARGET_Q
        call ptr16_cur
        ld c,(hl)
        inc hl
        ld b,(hl)                 ; BC=target
        ; compare current DE with target BC
        ld h,d
        ld l,e
        or a
        sbc hl,bc
        pop hl                    ; HL=step
        jr z,porta_done
        jr c,porta_current_lower
        ; current > target: subtract step, clamp at target
        ex de,hl                  ; DE=step, HL=current
        or a
        sbc hl,de
        push hl
        or a
        sbc hl,bc
        pop hl
        jr nc,porta_store
        ld h,b
        ld l,c
        jr porta_store
porta_current_lower:
        ; current < target: add step, clamp at target
        ex de,hl                  ; DE=step, HL=current
        add hl,de
        push hl
        or a
        sbc hl,bc
        pop hl
        jr c,porta_store
        jr z,porta_store
        ld h,b
        ld l,c
porta_store:
        call store_period_hl
porta_done:
        ret

effect_vibrato:
        jp effect_vibrato_legacy

effect_vibrato_legacy:
        ; ST3 Hxy: evaluate vibrato on tick 0 using the current phase, but do
        ; not advance phase until non-zero ticks. 64-entry phase is equivalent
        ; to ST3's 256-step phase with speed x*4.
        ld hl,VIBPH
        call ptr8_cur
        ld a,(hl)
        and 3Fh
        call get_vib_wave_current
        ld b,a
        ld a,(TICK_NOW)
        or a
        jr z,s3m_vib_no_advance
        ld hl,VIBPH
        call ptr8_cur
        ld a,(hl)
        ld c,a
        ld hl,VIBSPD
        call ptr8_cur
        ld a,(hl)
        add a,c
        and 3Fh
        ld hl,VIBPH
        call ptr8_cur
        ld (hl),a
s3m_vib_no_advance:
        ld a,b
        or a
        ret z
        jp p,vib_positive
        neg
        ld b,1
        jr vib_abs_ready
vib_positive:
        ld b,0
vib_abs_ready:
        ld e,a
        ld d,0
        push bc
        ld hl,VIBDEP
        call ptr8_cur
        ld a,(hl)
        ld c,a
        ld hl,0
        ld b,0
vib_mul_loop:
        ld a,c
        or a
        jr z,vib_mul_done
        add hl,de
        dec c
        jr vib_mul_loop
vib_mul_done:
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ld e,l
        ld d,0
        pop bc
        ld hl,(OUT_PERIOD)
        ld a,b
        or a
        jr nz,vib_sub
        add hl,de
        jr vib_store_out
vib_sub:
        or a
        sbc hl,de
        jr nc,vib_store_out
        ld hl,1
vib_store_out:
        ld (OUT_PERIOD),hl
        ld a,e
        or d
        ret z
        ld a,1
        ld (PITCH_DIRTY),a
        ret

effect_tremor:
        ; ST3 Ixy: x+1 ticks on, y+1 ticks off. Counter persists across rows
        ; and is reset by a new note.
        ld a,e
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        ld b,a                 ; x
        ld a,e
        and 0Fh
        ld c,a                 ; y
        ld hl,TREMOR_COUNT
        call ptr8_cur
        ld a,b
        add a,c
        add a,2
        ld d,a                 ; cycle length
        ld a,(hl)
        cp d
        jr c,tremor_count_ok
        xor a
        ld (hl),a
tremor_count_ok:
        ld e,a                 ; current count
        inc a
        ld (hl),a              ; next count
        ld a,b
        inc a                  ; on length
        cp e
        jr c,tremor_off
        jr z,tremor_off
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        jp emit_volume_a_temp
tremor_off:
        xor a
        jp emit_volume_a_temp

effect_tremolo:
        ; ST3 Rxy. The host already resolved ST3 shared parameter memory, so
        ; both nibbles are authoritative here (including a zero nibble).
        ld a,e
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        ld hl,TREMSPD
        call ptr8_cur
        ld (hl),a
        ld a,e
        and 0Fh
        ld hl,TREMDEP
        call ptr8_cur
        ld (hl),a
        ld hl,TREMPH
        call ptr8_cur
        ld a,(hl)
        and 3Fh
        call get_trem_wave_current
        ld b,a                 ; signed waveform delta
        ld a,(TICK_NOW)
        or a
        jr z,trem_no_advance
        ld hl,TREMPH
        call ptr8_cur
        ld a,(hl)
        ld c,a
        ld hl,TREMSPD
        call ptr8_cur
        ld a,(hl)
        add a,c
        and 3Fh
        ld hl,TREMPH
        call ptr8_cur
        ld (hl),a
trem_no_advance:
        ld a,b
        or a
        jr z,trem_emit_base
        jp p,trem_positive
        neg
        ld c,1
        jr trem_abs_ready
trem_positive:
        ld c,0
trem_abs_ready:
        ld e,a
        ld d,0
        push bc
        ld hl,TREMDEP
        call ptr8_cur
        ld a,(hl)
        ld b,a
        ld hl,0
trem_mul:
        ld a,b
        or a
        jr z,trem_mul_done
        add hl,de
        dec b
        jr trem_mul
trem_mul_done:
        ; tracker-volume delta = waveform * depth / 64
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ld e,l
        pop bc
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        ld b,a
        ld a,c
        or a
        ld a,b
        jr nz,trem_sub
        add a,e
        cp 65
        jr c,trem_emit
        ld a,64
        jr trem_emit
trem_sub:
        sub e
        jr nc,trem_emit
        xor a
trem_emit:
        jp emit_volume_a_temp
trem_emit_base:
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        jp emit_volume_a_temp

effect_finetune:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld hl,ARP1
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        ret z
        ld hl,PERIOD_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld hl,TARGET_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld (OUT_PERIOD),de
        ld a,1
        ld (PITCH_DIRTY),a
        ret

effect_arpeggio:
        ld a,(TICK_NOW)
arp_mod3:
        cp 3
        jr c,arp_mod_done
        sub 3
        jr arp_mod3
arp_mod_done:
        or a
        ret z
        cp 1
        jr nz,arp_use_2
        ld hl,ARP1
        jr arp_load
arp_use_2:
        ld hl,ARP2
arp_load:
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        ret z
        ld (OUT_PERIOD),de
        ld a,1
        ld (PITCH_DIRTY),a
        ret

effect_retrig:
        ; IT Qxy countdown semantics. A note+Qxy arms bit 7 in
        ; it_arm_retrig_on_note, so the note is not retriggered immediately.
        ld a,e
        and 0Fh
        ret z
        ld b,a
        ld hl,RETRIG_COUNT
        call ptr8_cur
        ld a,(hl)
        bit 7,a
        jr z,it_retrig_count
        and 0Fh
        ld (hl),a
        ret
it_retrig_count:
        and 0Fh
        jr z,it_retrig_fire
        dec a
        ld (hl),a
        ret nz
it_retrig_fire:
        ld (hl),b
        ; IT short-sample retrigger: do not resurrect an already stopped voice.
        ld hl,KEYSTATE
        call ptr8_cur
        ld a,(hl)
        or a
        ret z
        ld a,e
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        call retrig_adjust_volume
        call keyoff_current
        jp keyon_current

retrig_adjust_volume:
        cp 0
        ret z
        cp 8
        ret z
        cp 1
        jr z,retrig_sub1
        cp 2
        jr z,retrig_sub2
        cp 3
        jr z,retrig_sub4
        cp 4
        jr z,retrig_sub8
        cp 5
        jr z,retrig_sub16
        cp 7
        jr z,retrig_half
        cp 9
        jr z,retrig_add1
        cp 10
        jr z,retrig_add2
        cp 11
        jr z,retrig_add4
        cp 12
        jr z,retrig_add8
        cp 13
        jr z,retrig_add16
        cp 15
        jr z,retrig_double
        ; x=6 (~2/3) and x=14 (~1.5) use compact approximations.
        cp 6
        jr z,retrig_twothirds
        ; x=14
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        ld b,a
        srl a
        add a,b
        cp 65
        jr c,retrig_store_a
        ld a,64
        jr retrig_store_a
retrig_twothirds:
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        ld b,a
        srl a
        srl a                    ; /4
        ld c,a
        ld a,b
        sub c                    ; ~3/4, conservative approximation
        jr retrig_store_a
retrig_half:
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        srl a
        jr retrig_store_a
retrig_double:
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        add a,a
        cp 65
        jr c,retrig_store_a
        ld a,64
        jr retrig_store_a
retrig_sub1: ld a,1
        jr retrig_sub
retrig_sub2: ld a,2
        jr retrig_sub
retrig_sub4: ld a,4
        jr retrig_sub
retrig_sub8: ld a,8
        jr retrig_sub
retrig_sub16: ld a,16
retrig_sub:
        call volume_sub_a
        ret
retrig_add1: ld a,1
        jr retrig_add
retrig_add2: ld a,2
        jr retrig_add
retrig_add4: ld a,4
        jr retrig_add
retrig_add8: ld a,8
        jr retrig_add
retrig_add16: ld a,16
retrig_add:
        call volume_add_a
        ret
retrig_store_a:
        ld hl,VOLUME
        call ptr8_cur
        ld (hl),a
        jp emit_volume_current

effect_note_cut:
        ld a,(TICK_NOW)
        cp e
        ret nz
        xor a
        call set_volume_a
        jp keycut_current

set_volume_a:
        cp 65
        jr c,set_volume_ok
        ld a,64
set_volume_ok:
        ld hl,VOLUME
        call ptr8_cur
        ld (hl),a
        jp emit_volume_current

emit_volume_current:
        ld hl,VOLUME
        call ptr8_cur
        ld e,(hl)
        ld d,0
        ld hl,VOL_LUT
        add hl,de
        ld e,(hl)
        ld a,(CUR_CH)
        add a,050h
        ld d,a
        jp opl4_write_de

emit_volume_a_temp:
        cp 65
        jr c,emit_temp_ok
        ld a,64
emit_temp_ok:
        ld e,a
        ld d,0
        ld hl,VOL_LUT
        add hl,de
        ld e,(hl)
        ld a,(CUR_CH)
        add a,050h
        ld d,a
        jp opl4_write_de

set_pan_from_tracker:
        ; A=0..255 tracker pan. OPL4: 9..15 left, 1..7 right, 0 centre.
        cp 128
        jr nc,pan_right
        rrca
        rrca
        rrca
        rrca
        and 07h
        ld b,a
        ld a,7
        sub b
        jr z,pan_center
        add a,8
        jr pan_store
pan_right:
        sub 128
        rrca
        rrca
        rrca
        rrca
        and 07h
        jr z,pan_center
        jr pan_store
pan_center:
        xor a
pan_store:
        ld hl,PAN
        call ptr8_cur
        ld (hl),a
        ; Update pan register immediately while preserving key-on state.
        ld e,a
        ld hl,KEYSTATE
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,pan_no_key
        ld a,e
        or 080h
        ld e,a
pan_no_key:
        ld a,(CUR_CH)
        add a,068h
        ld d,a
        jp opl4_write_de

store_vib_speed:
        ld hl,VIBSPD
        call ptr8_cur
        ld (hl),a
        ret
store_vib_depth:
        ld hl,VIBDEP
        call ptr8_cur
        ld (hl),a
        ret

get_vib_wave_current:
        ld c,a
        ld hl,VIBTYPE
        call ptr8_cur
        ld b,(hl)
        jr get_mod_wave

get_trem_wave_current:
        ld c,a
        ld hl,TREMTYPE
        call ptr8_cur
        ld b,(hl)
get_mod_wave:
        ld a,b
        and 03h
        or a
        jr z,mod_wave_sine
        cp 1
        jr z,mod_wave_ramp
        cp 2
        jr z,mod_wave_square
        ld e,c
        ld d,0
        ld hl,RANDOM_TABLE
        add hl,de
        ld a,(hl)
        ret
mod_wave_sine:
        ld e,c
        ld d,0
        ld hl,SINE_TABLE
        add hl,de
        ld a,(hl)
        ret
mod_wave_ramp:
        ld a,c
        add a,a
        add a,a
        ld b,a
        ld a,c
        cp 32
        jr nc,mod_ramp_hi
        xor a
        sub b
        ret
mod_ramp_hi:
        ld a,0FFh
        sub b
        ret
mod_wave_square:
        ld a,c
        cp 32
        ld a,127
        ret c
        ld a,129               ; -127 signed
        ret

keycut_current:
        ; S3M note-off is a cut, not a long envelope release.
        ; YMF278B DAMP reaches silence in about 11 ms and is cleared by keyon.
        ld hl,PAN
        call ptr8_cur
        ld a,(hl)
        or 040h
        ld e,a
        ld a,(CUR_CH)
        add a,068h
        ld d,a
        call opl4_write_de
        xor a
        ld hl,KEYSTATE
        call ptr8_cur
        ld (hl),a
        ret

keyoff_current:
        ld hl,PAN
        call ptr8_cur
        ld e,(hl)
        ld a,(CUR_CH)
        add a,068h
        ld d,a
        call opl4_write_de
        xor a
        ld hl,KEYSTATE
        call ptr8_cur
        ld (hl),a
        ret
keyon_current:
        ld hl,PAN
        call ptr8_cur
        ld a,(hl)
        or 080h
        ld e,a
        ld a,(CUR_CH)
        add a,068h
        ld d,a
        call opl4_write_de
        ld a,1
        ld hl,KEYSTATE
        call ptr8_cur
        ld (hl),a
        ret

emit_pitch_approx:
        ld hl,(OUT_PERIOD)
        ld a,0FDh                ; signed octave -3
pitch_norm_low:
        ld de,2574
        push hl
        or a
        sbc hl,de
        pop hl
        jr nc,pitch_norm_high
        add hl,hl
        inc a
        cp 8
        jr nz,pitch_norm_low
pitch_norm_high:
        ld de,5148
        push hl
        or a
        sbc hl,de
        pop hl
        jr c,pitch_norm_ready
        ; rounded right shift
        inc hl
        srl h
        rr l
        dec a
        cp 0F8h                  ; -8
        jr nz,pitch_norm_high
pitch_norm_ready:
        ld (EV_PHI),a            ; temporary octave
        ld de,2560
        or a
        sbc hl,de
        add hl,hl
        ld de,PITCH_LUT
        add hl,de
        ld e,(hl)                ; reg20 fnum bits
        inc hl
        ld b,(hl)                ; fnum high 3 bits
        ld a,e
        or 1
        ld e,a
        ld a,(CUR_CH)
        add a,020h
        ld d,a
        push bc
        call opl4_write_de
        pop bc
        ld a,(EV_PHI)
        and 0Fh
        add a,a
        add a,a
        add a,a
        add a,a
        or b
        ld e,a
        ld a,(CUR_CH)
        add a,038h
        ld d,a
        jp opl4_write_de

stream_end:
        ld a,1
        ld (ENDED),a
        call silence
        ret

ptr8_cur:
        push af
        push de
        ld a,(CUR_CH)
        ld e,a
        ld d,0
        add hl,de
        pop de
        pop af
        ret
ptr16_cur:
        push af
        push de
        ld a,(CUR_CH)
        add a,a
        ld e,a
        ld d,0
        add hl,de
        pop de
        pop af
        ret

read_stream_byte:
        push de
        ld hl,(PTR)
        ld de,(PAGE_END)
        or a
        sbc hl,de
        jr c,read_have
        call load_next_page
        jr c,read_fail
read_have:
        ld hl,(PTR)
        ld a,(hl)
        inc hl
        ld (PTR),hl
        or a
        pop de
        ret
read_fail:
        pop de
        scf
        ret

load_next_page:
        ld hl,(PAGE_INDEX)
        inc hl
        ld (PAGE_INDEX),hl
        push hl
        ld de,(PAGE_TOTAL_CFG)
        or a
        sbc hl,de
        pop hl
        jr nc,no_more_pages
        ; Enter the host gateway with carry clear.  KSP1PLAY explicitly returns
        ; carry clear on success; TinyKSP's host-intercepted gateway preserves CPU
        ; flags, so relying on the comparison carry above would falsely signal an
        ; error after every successful page install.
        or a
        ; The KSP dynamic gateway rematerializes the complete 16 KiB page.
        ; Preserve realtime tracker state in the top 512 bytes of MoonSound RAM
        ; across that replacement. Sample packing reserves this area.
        push hl
        call save_persistent_state
        pop hl
        call DYNAMIC_GATEWAY
        jr c,load_page_gateway_failed
        call restore_persistent_state
        ld hl,STREAM_DATA
        ld (PTR),hl
        call set_page_end
        or a
        ret
load_page_gateway_failed:
        call restore_persistent_state
        scf
        ret
no_more_pages:
        scf
        ret

set_page_end:
        ld hl,(STREAM_PAGE)
        ld de,STREAM_DATA
        add hl,de
        ld (PAGE_END),hl
        ret

; ---------------------------------------------------------------------------
; Dynamic-page persistent state
;
; Dynamic materialization replaces 4000h..7FFFh, including our RAM state.
; Store only state that must survive between rows in reserved MoonSound RAM
; 2FFE00h..2FFFFFh. 301 bytes are used; the converter never places MWK sample
; payload in this final 512-byte window. CMD/PAR/delay/ARP scratch is row-local
; and deliberately not persisted because page changes only occur between rows.
; ---------------------------------------------------------------------------

state_mem_address:
        ld d,03h
        ld e,02Fh              ; 2FFE00h high six address bits
        call opl4_write_de
        ld d,04h
        ld e,0FEh
        call opl4_write_de
        ld d,05h
        ld e,000h
        call opl4_write_de
        ld a,006h
        out (07Eh),a
        jp opl4_wait

save_persistent_state:
        ld d,02h
        ld e,011h              ; memory access + write enable
        call opl4_write_de
        call state_mem_address
        ld hl,PAGE_INDEX
        ld bc,9                ; PAGE_INDEX..ENDED (includes ROW_TICK)
        call state_write_block
        ld hl,FAST_VOL
        ld bc,31               ; FAST_VOL..HOLD_ROW
        call state_write_block
        ld hl,PERIOD_Q
        ld bc,CMD1-PERIOD_Q    ; periods/target/volume/wave/key state
        call state_write_block
        ld hl,VIBSPD
        ld bc,ARP1-VIBSPD      ; vibrato speed/depth/phase
        call state_write_block
        ld hl,PAN
        ld bc,24
        call state_write_block
        ld hl,TREMOR_COUNT
        ld bc,168
        call state_write_block
        ld d,02h
        ld e,010h              ; leave MoonSound RAM write disabled
        jp opl4_write_de

state_write_block:
        ld a,b
        or c
        ret z
state_write_loop:
        ld a,(hl)
        out (07Fh),a
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,state_write_loop
        ret

restore_persistent_state:
        ld d,02h
        ld e,011h              ; enable external-memory access for sequential reads
        call opl4_write_de
        call state_mem_address
        ld hl,PAGE_INDEX
        ld bc,9
        call state_read_block
        ld hl,FAST_VOL
        ld bc,31               ; FAST_VOL..HOLD_ROW
        call state_read_block
        ld hl,PERIOD_Q
        ld bc,CMD1-PERIOD_Q
        call state_read_block
        ld hl,VIBSPD
        ld bc,ARP1-VIBSPD
        call state_read_block
        ld hl,PAN
        ld bc,24
        call state_read_block
        ld hl,TREMOR_COUNT
        ld bc,168
        call state_read_block
        ld d,02h
        ld e,010h              ; return MoonSound to normal wave-table mode
        jp opl4_write_de

state_read_block:
        ld a,b
        or c
        ret z
state_read_loop:
        in a,(07Fh)
        ld (hl),a
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,state_read_loop
        ret

opl4_write_de:
        ld a,d
        out (07Eh),a
        call opl4_wait
        ld a,e
        out (07Fh),a
        jp opl4_wait
opl4_wait:
        push bc
        ld b,16
opl4_wait_loop:
        in a,(07Eh)
        djnz opl4_wait_loop
        pop bc
        ret

silence:
        ld d,050h
        ld e,0FFh
        ld b,24
silence_level:
        call opl4_write_de
        inc d
        djnz silence_level
        ld d,068h
        ld e,040h
        ld b,24
silence_key:
        call opl4_write_de
        inc d
        djnz silence_key
        ret

SINE_TABLE:
        db 0,12,25,37,49,60,71,81,90,98,106,112,117,122,125,126
        db 127,126,125,122,117,112,106,98,90,81,71,60,49,37,25,12
        db 0,244,231,219,207,196,185,175,166,158,150,144,139,134,131,130
        db 129,130,131,134,139,144,150,158,166,175,185,196,207,219,231,244
RANDOM_TABLE:
        db 98,129,213,88,102,41,191,162,125,20,185,170,186,224,240,160
        db 17,72,107,251,116,187,194,216,10,195,65,109,238,218,243,180
        db 96,160,243,125,84,145,204,189,236,187,100,174,8,186,205,143
        db 45,77,129,221,154,59,194,98,210,30,68,106,134,198,99,41


; Preserve the v0.3.8 table addresses exactly. The generic engine historically
; has a small PITCH_LUT/state overlap, so moving these tables changes playback.
        defs 4,0

; 65-byte volume -> OPL4 TL register table. The converter patches this per song/global volume.
VOL_LUT:
        defs 65,0

FT2_VIB_TAB:
        db 0,24,49,74,97,120,141,161,180,197,212,224,235,244,250,253
        db 255,253,250,244,235,224,212,197,180,161,141,120,97,74,49,24

PITCH_LUT:
        db FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h
        db FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h,FEh,07h
        db FCh,07h,FAh,07h,FAh,07h,F8h,07h,F6h,07h,F4h,07h,F2h,07h,F2h,07h
        db F0h,07h,EEh,07h,ECh,07h,EAh,07h,EAh,07h,E8h,07h,E6h,07h,E4h,07h
        db E4h,07h,E2h,07h,E0h,07h,DEh,07h,DCh,07h,DCh,07h,DAh,07h,D8h,07h
        db D6h,07h,D6h,07h,D4h,07h,D2h,07h,D0h,07h,CEh,07h,CEh,07h,CCh,07h
        db CAh,07h,C8h,07h,C8h,07h,C6h,07h,C4h,07h,C2h,07h,C0h,07h,C0h,07h
        db BEh,07h,BCh,07h,BAh,07h,BAh,07h,B8h,07h,B6h,07h,B4h,07h,B4h,07h
        db B2h,07h,B0h,07h,AEh,07h,ACh,07h,ACh,07h,AAh,07h,A8h,07h,A6h,07h
        db A6h,07h,A4h,07h,A2h,07h,A0h,07h,A0h,07h,9Eh,07h,9Ch,07h,9Ah,07h
        db 9Ah,07h,98h,07h,96h,07h,94h,07h,94h,07h,92h,07h,90h,07h,8Eh,07h
        db 8Eh,07h,8Ch,07h,8Ah,07h,88h,07h,88h,07h,86h,07h,84h,07h,82h,07h
        db 82h,07h,80h,07h,7Eh,07h,7Ch,07h,7Ch,07h,7Ah,07h,78h,07h,76h,07h
        db 76h,07h,74h,07h,72h,07h,70h,07h,70h,07h,6Eh,07h,6Ch,07h,6Ah,07h
        db 6Ah,07h,68h,07h,66h,07h,64h,07h,64h,07h,62h,07h,60h,07h,60h,07h
        db 5Eh,07h,5Ch,07h,5Ah,07h,5Ah,07h,58h,07h,56h,07h,54h,07h,54h,07h
        db 52h,07h,50h,07h,4Eh,07h,4Eh,07h,4Ch,07h,4Ah,07h,4Ah,07h,48h,07h
        db 46h,07h,44h,07h,44h,07h,42h,07h,40h,07h,3Eh,07h,3Eh,07h,3Ch,07h
        db 3Ah,07h,3Ah,07h,38h,07h,36h,07h,34h,07h,34h,07h,32h,07h,30h,07h
        db 30h,07h,2Eh,07h,2Ch,07h,2Ah,07h,2Ah,07h,28h,07h,26h,07h,26h,07h
        db 24h,07h,22h,07h,20h,07h,20h,07h,1Eh,07h,1Ch,07h,1Ch,07h,1Ah,07h
        db 18h,07h,16h,07h,16h,07h,14h,07h,12h,07h,12h,07h,10h,07h,0Eh,07h
        db 0Eh,07h,0Ch,07h,0Ah,07h,08h,07h,08h,07h,06h,07h,04h,07h,04h,07h
        db 02h,07h,00h,07h,00h,07h,FEh,06h,FCh,06h,FAh,06h,FAh,06h,F8h,06h
        db F6h,06h,F6h,06h,F4h,06h,F2h,06h,F2h,06h,F0h,06h,EEh,06h,ECh,06h
        db ECh,06h,EAh,06h,E8h,06h,E8h,06h,E6h,06h,E4h,06h,E4h,06h,E2h,06h
        db E0h,06h,E0h,06h,DEh,06h,DCh,06h,DCh,06h,DAh,06h,D8h,06h,D6h,06h
        db D6h,06h,D4h,06h,D2h,06h,D2h,06h,D0h,06h,CEh,06h,CEh,06h,CCh,06h
        db CAh,06h,CAh,06h,C8h,06h,C6h,06h,C6h,06h,C4h,06h,C2h,06h,C2h,06h
        db C0h,06h,BEh,06h,BEh,06h,BCh,06h,BAh,06h,BAh,06h,B8h,06h,B6h,06h
        db B4h,06h,B4h,06h,B2h,06h,B0h,06h,B0h,06h,AEh,06h,ACh,06h,ACh,06h
        db AAh,06h,A8h,06h,A8h,06h,A6h,06h,A4h,06h,A4h,06h,A2h,06h,A0h,06h
        db A0h,06h,9Eh,06h,9Ch,06h,9Ch,06h,9Ah,06h,98h,06h,98h,06h,96h,06h
        db 94h,06h,94h,06h,92h,06h,92h,06h,90h,06h,8Eh,06h,8Eh,06h,8Ch,06h
        db 8Ah,06h,8Ah,06h,88h,06h,86h,06h,86h,06h,84h,06h,82h,06h,82h,06h
        db 80h,06h,7Eh,06h,7Eh,06h,7Ch,06h,7Ah,06h,7Ah,06h,78h,06h,76h,06h
        db 76h,06h,74h,06h,72h,06h,72h,06h,70h,06h,70h,06h,6Eh,06h,6Ch,06h
        db 6Ch,06h,6Ah,06h,68h,06h,68h,06h,66h,06h,64h,06h,64h,06h,62h,06h
        db 60h,06h,60h,06h,5Eh,06h,5Ch,06h,5Ch,06h,5Ah,06h,5Ah,06h,58h,06h
        db 56h,06h,56h,06h,54h,06h,52h,06h,52h,06h,50h,06h,4Eh,06h,4Eh,06h
        db 4Ch,06h,4Ch,06h,4Ah,06h,48h,06h,48h,06h,46h,06h,44h,06h,44h,06h
        db 42h,06h,40h,06h,40h,06h,3Eh,06h,3Eh,06h,3Ch,06h,3Ah,06h,3Ah,06h
        db 38h,06h,36h,06h,36h,06h,34h,06h,34h,06h,32h,06h,30h,06h,30h,06h
        db 2Eh,06h,2Ch,06h,2Ch,06h,2Ah,06h,2Ah,06h,28h,06h,26h,06h,26h,06h
        db 24h,06h,22h,06h,22h,06h,20h,06h,20h,06h,1Eh,06h,1Ch,06h,1Ch,06h
        db 1Ah,06h,1Ah,06h,18h,06h,16h,06h,16h,06h,14h,06h,12h,06h,12h,06h
        db 10h,06h,10h,06h,0Eh,06h,0Ch,06h,0Ch,06h,0Ah,06h,0Ah,06h,08h,06h
        db 06h,06h,06h,06h,04h,06h,02h,06h,02h,06h,00h,06h,00h,06h,FEh,05h
        db FCh,05h,FCh,05h,FAh,05h,FAh,05h,F8h,05h,F6h,05h,F6h,05h,F4h,05h
        db F4h,05h,F2h,05h,F0h,05h,F0h,05h,EEh,05h,EEh,05h,ECh,05h,EAh,05h
        db EAh,05h,E8h,05h,E8h,05h,E6h,05h,E4h,05h,E4h,05h,E2h,05h,E2h,05h
        db E0h,05h,DEh,05h,DEh,05h,DCh,05h,DCh,05h,DAh,05h,D8h,05h,D8h,05h
        db D6h,05h,D6h,05h,D4h,05h,D2h,05h,D2h,05h,D0h,05h,D0h,05h,CEh,05h
        db CCh,05h,CCh,05h,CAh,05h,CAh,05h,C8h,05h,C6h,05h,C6h,05h,C4h,05h
        db C4h,05h,C2h,05h,C2h,05h,C0h,05h,BEh,05h,BEh,05h,BCh,05h,BCh,05h
        db BAh,05h,B8h,05h,B8h,05h,B6h,05h,B6h,05h,B4h,05h,B2h,05h,B2h,05h
        db B0h,05h,B0h,05h,AEh,05h,AEh,05h,ACh,05h,AAh,05h,AAh,05h,A8h,05h
        db A8h,05h,A6h,05h,A6h,05h,A4h,05h,A2h,05h,A2h,05h,A0h,05h,A0h,05h
        db 9Eh,05h,9Ch,05h,9Ch,05h,9Ah,05h,9Ah,05h,98h,05h,98h,05h,96h,05h
        db 94h,05h,94h,05h,92h,05h,92h,05h,90h,05h,90h,05h,8Eh,05h,8Ch,05h
        db 8Ch,05h,8Ah,05h,8Ah,05h,88h,05h,88h,05h,86h,05h,84h,05h,84h,05h
        db 82h,05h,82h,05h,80h,05h,80h,05h,7Eh,05h,7Ch,05h,7Ch,05h,7Ah,05h
        db 7Ah,05h,78h,05h,78h,05h,76h,05h,76h,05h,74h,05h,72h,05h,72h,05h
        db 70h,05h,70h,05h,6Eh,05h,6Eh,05h,6Ch,05h,6Ah,05h,6Ah,05h,68h,05h
        db 68h,05h,66h,05h,66h,05h,64h,05h,64h,05h,62h,05h,60h,05h,60h,05h
        db 5Eh,05h,5Eh,05h,5Ch,05h,5Ch,05h,5Ah,05h,5Ah,05h,58h,05h,56h,05h
        db 56h,05h,54h,05h,54h,05h,52h,05h,52h,05h,50h,05h,50h,05h,4Eh,05h
        db 4Eh,05h,4Ch,05h,4Ah,05h,4Ah,05h,48h,05h,48h,05h,46h,05h,46h,05h
        db 44h,05h,44h,05h,42h,05h,40h,05h,40h,05h,3Eh,05h,3Eh,05h,3Ch,05h
        db 3Ch,05h,3Ah,05h,3Ah,05h,38h,05h,38h,05h,36h,05h,34h,05h,34h,05h
        db 32h,05h,32h,05h,30h,05h,30h,05h,2Eh,05h,2Eh,05h,2Ch,05h,2Ch,05h
        db 2Ah,05h,2Ah,05h,28h,05h,26h,05h,26h,05h,24h,05h,24h,05h,22h,05h
        db 22h,05h,20h,05h,20h,05h,1Eh,05h,1Eh,05h,1Ch,05h,1Ch,05h,1Ah,05h
        db 1Ah,05h,18h,05h,16h,05h,16h,05h,14h,05h,14h,05h,12h,05h,12h,05h
        db 10h,05h,10h,05h,0Eh,05h,0Eh,05h,0Ch,05h,0Ch,05h,0Ah,05h,0Ah,05h
        db 08h,05h,06h,05h,06h,05h,04h,05h,04h,05h,02h,05h,02h,05h,00h,05h
        db 00h,05h,FEh,04h,FEh,04h,FCh,04h,FCh,04h,FAh,04h,FAh,04h,F8h,04h
        db F8h,04h,F6h,04h,F6h,04h,F4h,04h,F4h,04h,F2h,04h,F0h,04h,F0h,04h
        db EEh,04h,EEh,04h,ECh,04h,ECh,04h,EAh,04h,EAh,04h,E8h,04h,E8h,04h
        db E6h,04h,E6h,04h,E4h,04h,E4h,04h,E2h,04h,E2h,04h,E0h,04h,E0h,04h
        db DEh,04h,DEh,04h,DCh,04h,DCh,04h,DAh,04h,DAh,04h,D8h,04h,D8h,04h
        db D6h,04h,D6h,04h,D4h,04h,D4h,04h,D2h,04h,D2h,04h,D0h,04h,CEh,04h
        db CEh,04h,CCh,04h,CCh,04h,CAh,04h,CAh,04h,C8h,04h,C8h,04h,C6h,04h
        db C6h,04h,C4h,04h,C4h,04h,C2h,04h,C2h,04h,C0h,04h,C0h,04h,BEh,04h
        db BEh,04h,BCh,04h,BCh,04h,BAh,04h,BAh,04h,B8h,04h,B8h,04h,B6h,04h
        db B6h,04h,B4h,04h,B4h,04h,B2h,04h,B2h,04h,B0h,04h,B0h,04h,AEh,04h
        db AEh,04h,ACh,04h,ACh,04h,AAh,04h,AAh,04h,A8h,04h,A8h,04h,A6h,04h
        db A6h,04h,A4h,04h,A4h,04h,A2h,04h,A2h,04h,A0h,04h,A0h,04h,9Eh,04h
        db 9Eh,04h,9Ch,04h,9Ch,04h,9Ah,04h,9Ah,04h,98h,04h,98h,04h,96h,04h
        db 96h,04h,94h,04h,94h,04h,92h,04h,92h,04h,90h,04h,90h,04h,8Eh,04h
        db 8Eh,04h,8Eh,04h,8Ch,04h,8Ch,04h,8Ah,04h,8Ah,04h,88h,04h,88h,04h
        db 86h,04h,86h,04h,84h,04h,84h,04h,82h,04h,82h,04h,80h,04h,80h,04h
        db 7Eh,04h,7Eh,04h,7Ch,04h,7Ch,04h,7Ah,04h,7Ah,04h,78h,04h,78h,04h
        db 76h,04h,76h,04h,74h,04h,74h,04h,72h,04h,72h,04h,70h,04h,70h,04h
        db 6Eh,04h,6Eh,04h,6Eh,04h,6Ch,04h,6Ch,04h,6Ah,04h,6Ah,04h,68h,04h
        db 68h,04h,66h,04h,66h,04h,64h,04h,64h,04h,62h,04h,62h,04h,60h,04h
        db 60h,04h,5Eh,04h,5Eh,04h,5Ch,04h,5Ch,04h,5Ah,04h,5Ah,04h,58h,04h
        db 58h,04h,58h,04h,56h,04h,56h,04h,54h,04h,54h,04h,52h,04h,52h,04h
        db 50h,04h,50h,04h,4Eh,04h,4Eh,04h,4Ch,04h,4Ch,04h,4Ah,04h,4Ah,04h
        db 48h,04h,48h,04h,48h,04h,46h,04h,46h,04h,44h,04h,44h,04h,42h,04h
        db 42h,04h,40h,04h,40h,04h,3Eh,04h,3Eh,04h,3Ch,04h,3Ch,04h,3Ah,04h
        db 3Ah,04h,3Ah,04h,38h,04h,38h,04h,36h,04h,36h,04h,34h,04h,34h,04h
        db 32h,04h,32h,04h,30h,04h,30h,04h,2Eh,04h,2Eh,04h,2Eh,04h,2Ch,04h
        db 2Ch,04h,2Ah,04h,2Ah,04h,28h,04h,28h,04h,26h,04h,26h,04h,24h,04h
        db 24h,04h,22h,04h,22h,04h,22h,04h,20h,04h,20h,04h,1Eh,04h,1Eh,04h
        db 1Ch,04h,1Ch,04h,1Ah,04h,1Ah,04h,18h,04h,18h,04h,18h,04h,16h,04h
        db 16h,04h,14h,04h,14h,04h,12h,04h,12h,04h,10h,04h,10h,04h,0Eh,04h
        db 0Eh,04h,0Eh,04h,0Ch,04h,0Ch,04h,0Ah,04h,0Ah,04h,08h,04h,08h,04h
        db 06h,04h,06h,04h,06h,04h,04h,04h,04h,04h,02h,04h,02h,04h,00h,04h
        db 00h,04h,FEh,03h,FEh,03h,FCh,03h,FCh,03h,FCh,03h,FAh,03h,FAh,03h
        db F8h,03h,F8h,03h,F6h,03h,F6h,03h,F4h,03h,F4h,03h,F4h,03h,F2h,03h
        db F2h,03h,F0h,03h,F0h,03h,EEh,03h,EEh,03h,ECh,03h,ECh,03h,ECh,03h
        db EAh,03h,EAh,03h,E8h,03h,E8h,03h,E6h,03h,E6h,03h,E6h,03h,E4h,03h
        db E4h,03h,E2h,03h,E2h,03h,E0h,03h,E0h,03h,DEh,03h,DEh,03h,DEh,03h
        db DCh,03h,DCh,03h,DAh,03h,DAh,03h,D8h,03h,D8h,03h,D8h,03h,D6h,03h
        db D6h,03h,D4h,03h,D4h,03h,D2h,03h,D2h,03h,D0h,03h,D0h,03h,D0h,03h
        db CEh,03h,CEh,03h,CCh,03h,CCh,03h,CAh,03h,CAh,03h,CAh,03h,C8h,03h
        db C8h,03h,C6h,03h,C6h,03h,C4h,03h,C4h,03h,C4h,03h,C2h,03h,C2h,03h
        db C0h,03h,C0h,03h,BEh,03h,BEh,03h,BEh,03h,BCh,03h,BCh,03h,BAh,03h
        db BAh,03h,B8h,03h,B8h,03h,B8h,03h,B6h,03h,B6h,03h,B4h,03h,B4h,03h
        db B2h,03h,B2h,03h,B2h,03h,B0h,03h,B0h,03h,AEh,03h,AEh,03h,ACh,03h
        db ACh,03h,ACh,03h,AAh,03h,AAh,03h,A8h,03h,A8h,03h,A6h,03h,A6h,03h
        db A6h,03h,A4h,03h,A4h,03h,A2h,03h,A2h,03h,A2h,03h,A0h,03h,A0h,03h
        db 9Eh,03h,9Eh,03h,9Ch,03h,9Ch,03h,9Ch,03h,9Ah,03h,9Ah,03h,98h,03h
        db 98h,03h,98h,03h,96h,03h,96h,03h,94h,03h,94h,03h,92h,03h,92h,03h
        db 92h,03h,90h,03h,90h,03h,8Eh,03h,8Eh,03h,8Eh,03h,8Ch,03h,8Ch,03h
        db 8Ah,03h,8Ah,03h,88h,03h,88h,03h,88h,03h,86h,03h,86h,03h,84h,03h
        db 84h,03h,84h,03h,82h,03h,82h,03h,80h,03h,80h,03h,80h,03h,7Eh,03h
        db 7Eh,03h,7Ch,03h,7Ch,03h,7Ah,03h,7Ah,03h,7Ah,03h,78h,03h,78h,03h
        db 76h,03h,76h,03h,76h,03h,74h,03h,74h,03h,72h,03h,72h,03h,72h,03h
        db 70h,03h,70h,03h,6Eh,03h,6Eh,03h,6Eh,03h,6Ch,03h,6Ch,03h,6Ah,03h
        db 6Ah,03h,6Ah,03h,68h,03h,68h,03h,66h,03h,66h,03h,64h,03h,64h,03h
        db 64h,03h,62h,03h,62h,03h,60h,03h,60h,03h,60h,03h,5Eh,03h,5Eh,03h
        db 5Ch,03h,5Ch,03h,5Ch,03h,5Ah,03h,5Ah,03h,58h,03h,58h,03h,58h,03h
        db 56h,03h,56h,03h,54h,03h,54h,03h,54h,03h,52h,03h,52h,03h,50h,03h
        db 50h,03h,50h,03h,4Eh,03h,4Eh,03h,4Ch,03h,4Ch,03h,4Ch,03h,4Ah,03h
        db 4Ah,03h,48h,03h,48h,03h,48h,03h,46h,03h,46h,03h,46h,03h,44h,03h
        db 44h,03h,42h,03h,42h,03h,42h,03h,40h,03h,40h,03h,3Eh,03h,3Eh,03h
        db 3Eh,03h,3Ch,03h,3Ch,03h,3Ah,03h,3Ah,03h,3Ah,03h,38h,03h,38h,03h
        db 36h,03h,36h,03h,36h,03h,34h,03h,34h,03h,32h,03h,32h,03h,32h,03h
        db 30h,03h,30h,03h,30h,03h,2Eh,03h,2Eh,03h,2Ch,03h,2Ch,03h,2Ch,03h
        db 2Ah,03h,2Ah,03h,28h,03h,28h,03h,28h,03h,26h,03h,26h,03h,26h,03h
        db 24h,03h,24h,03h,22h,03h,22h,03h,22h,03h,20h,03h,20h,03h,1Eh,03h
        db 1Eh,03h,1Eh,03h,1Ch,03h,1Ch,03h,1Ch,03h,1Ah,03h,1Ah,03h,18h,03h
        db 18h,03h,18h,03h,16h,03h,16h,03h,14h,03h,14h,03h,14h,03h,12h,03h
        db 12h,03h,12h,03h,10h,03h,10h,03h,0Eh,03h,0Eh,03h,0Eh,03h,0Ch,03h
        db 0Ch,03h,0Ch,03h,0Ah,03h,0Ah,03h,08h,03h,08h,03h,08h,03h,06h,03h
        db 06h,03h,04h,03h,04h,03h,04h,03h,02h,03h,02h,03h,02h,03h,00h,03h
        db 00h,03h,FEh,02h,FEh,02h,FEh,02h,FCh,02h,FCh,02h,FCh,02h,FAh,02h
        db FAh,02h,F8h,02h,F8h,02h,F8h,02h,F6h,02h,F6h,02h,F6h,02h,F4h,02h
        db F4h,02h,F2h,02h,F2h,02h,F2h,02h,F0h,02h,F0h,02h,F0h,02h,EEh,02h
        db EEh,02h,EEh,02h,ECh,02h,ECh,02h,EAh,02h,EAh,02h,EAh,02h,E8h,02h
        db E8h,02h,E8h,02h,E6h,02h,E6h,02h,E4h,02h,E4h,02h,E4h,02h,E2h,02h
        db E2h,02h,E2h,02h,E0h,02h,E0h,02h,DEh,02h,DEh,02h,DEh,02h,DCh,02h
        db DCh,02h,DCh,02h,DAh,02h,DAh,02h,DAh,02h,D8h,02h,D8h,02h,D6h,02h
        db D6h,02h,D6h,02h,D4h,02h,D4h,02h,D4h,02h,D2h,02h,D2h,02h,D2h,02h
        db D0h,02h,D0h,02h,CEh,02h,CEh,02h,CEh,02h,CCh,02h,CCh,02h,CCh,02h
        db CAh,02h,CAh,02h,CAh,02h,C8h,02h,C8h,02h,C6h,02h,C6h,02h,C6h,02h
        db C4h,02h,C4h,02h,C4h,02h,C2h,02h,C2h,02h,C2h,02h,C0h,02h,C0h,02h
        db C0h,02h,BEh,02h,BEh,02h,BCh,02h,BCh,02h,BCh,02h,BAh,02h,BAh,02h
        db BAh,02h,B8h,02h,B8h,02h,B8h,02h,B6h,02h,B6h,02h,B6h,02h,B4h,02h
        db B4h,02h,B2h,02h,B2h,02h,B2h,02h,B0h,02h,B0h,02h,B0h,02h,AEh,02h
        db AEh,02h,AEh,02h,ACh,02h,ACh,02h,ACh,02h,AAh,02h,AAh,02h,A8h,02h
        db A8h,02h,A8h,02h,A6h,02h,A6h,02h,A6h,02h,A4h,02h,A4h,02h,A4h,02h
        db A2h,02h,A2h,02h,A2h,02h,A0h,02h,A0h,02h,A0h,02h,9Eh,02h,9Eh,02h
        db 9Ch,02h,9Ch,02h,9Ch,02h,9Ah,02h,9Ah,02h,9Ah,02h,98h,02h,98h,02h
        db 98h,02h,96h,02h,96h,02h,96h,02h,94h,02h,94h,02h,94h,02h,92h,02h
        db 92h,02h,92h,02h,90h,02h,90h,02h,90h,02h,8Eh,02h,8Eh,02h,8Ch,02h
        db 8Ch,02h,8Ch,02h,8Ah,02h,8Ah,02h,8Ah,02h,88h,02h,88h,02h,88h,02h
        db 86h,02h,86h,02h,86h,02h,84h,02h,84h,02h,84h,02h,82h,02h,82h,02h
        db 82h,02h,80h,02h,80h,02h,80h,02h,7Eh,02h,7Eh,02h,7Eh,02h,7Ch,02h
        db 7Ch,02h,7Ch,02h,7Ah,02h,7Ah,02h,7Ah,02h,78h,02h,78h,02h,78h,02h
        db 76h,02h,76h,02h,74h,02h,74h,02h,74h,02h,72h,02h,72h,02h,72h,02h
        db 70h,02h,70h,02h,70h,02h,6Eh,02h,6Eh,02h,6Eh,02h,6Ch,02h,6Ch,02h
        db 6Ch,02h,6Ah,02h,6Ah,02h,6Ah,02h,68h,02h,68h,02h,68h,02h,66h,02h
        db 66h,02h,66h,02h,64h,02h,64h,02h,64h,02h,62h,02h,62h,02h,62h,02h
        db 60h,02h,60h,02h,60h,02h,5Eh,02h,5Eh,02h,5Eh,02h,5Ch,02h,5Ch,02h
        db 5Ch,02h,5Ah,02h,5Ah,02h,5Ah,02h,58h,02h,58h,02h,58h,02h,56h,02h
        db 56h,02h,56h,02h,54h,02h,54h,02h,54h,02h,52h,02h,52h,02h,52h,02h
        db 50h,02h,50h,02h,50h,02h,4Eh,02h,4Eh,02h,4Eh,02h,4Ch,02h,4Ch,02h
        db 4Ch,02h,4Ah,02h,4Ah,02h,4Ah,02h,48h,02h,48h,02h,48h,02h,46h,02h
        db 46h,02h,46h,02h,44h,02h,44h,02h,44h,02h,42h,02h,42h,02h,42h,02h
        db 40h,02h,40h,02h,40h,02h,40h,02h,3Eh,02h,3Eh,02h,3Eh,02h,3Ch,02h
        db 3Ch,02h,3Ch,02h,3Ah,02h,3Ah,02h,3Ah,02h,38h,02h,38h,02h,38h,02h
        db 36h,02h,36h,02h,36h,02h,34h,02h,34h,02h,34h,02h,32h,02h,32h,02h
        db 32h,02h,30h,02h,30h,02h,30h,02h,2Eh,02h,2Eh,02h,2Eh,02h,2Ch,02h
        db 2Ch,02h,2Ch,02h,2Ah,02h,2Ah,02h,2Ah,02h,2Ah,02h,28h,02h,28h,02h
        db 28h,02h,26h,02h,26h,02h,26h,02h,24h,02h,24h,02h,24h,02h,22h,02h
        db 22h,02h,22h,02h,20h,02h,20h,02h,20h,02h,1Eh,02h,1Eh,02h,1Eh,02h
        db 1Ch,02h,1Ch,02h,1Ch,02h,1Ah,02h,1Ah,02h,1Ah,02h,1Ah,02h,18h,02h
        db 18h,02h,18h,02h,16h,02h,16h,02h,16h,02h,14h,02h,14h,02h,14h,02h
        db 12h,02h,12h,02h,12h,02h,10h,02h,10h,02h,10h,02h,0Eh,02h,0Eh,02h
        db 0Eh,02h,0Eh,02h,0Ch,02h,0Ch,02h,0Ch,02h,0Ah,02h,0Ah,02h,0Ah,02h
        db 08h,02h,08h,02h,08h,02h,06h,02h,06h,02h,06h,02h,04h,02h,04h,02h
        db 04h,02h,04h,02h,02h,02h,02h,02h,02h,02h,00h,02h,00h,02h,00h,02h
        db FEh,01h,FEh,01h,FEh,01h,FCh,01h,FCh,01h,FCh,01h,FAh,01h,FAh,01h
        db FAh,01h,FAh,01h,F8h,01h,F8h,01h,F8h,01h,F6h,01h,F6h,01h,F6h,01h
        db F4h,01h,F4h,01h,F4h,01h,F2h,01h,F2h,01h,F2h,01h,F2h,01h,F0h,01h
        db F0h,01h,F0h,01h,EEh,01h,EEh,01h,EEh,01h,ECh,01h,ECh,01h,ECh,01h
        db EAh,01h,EAh,01h,EAh,01h,EAh,01h,E8h,01h,E8h,01h,E8h,01h,E6h,01h
        db E6h,01h,E6h,01h,E4h,01h,E4h,01h,E4h,01h,E4h,01h,E2h,01h,E2h,01h
        db E2h,01h,E0h,01h,E0h,01h,E0h,01h,DEh,01h,DEh,01h,DEh,01h,DEh,01h
        db DCh,01h,DCh,01h,DCh,01h,DAh,01h,DAh,01h,DAh,01h,D8h,01h,D8h,01h
        db D8h,01h,D6h,01h,D6h,01h,D6h,01h,D6h,01h,D4h,01h,D4h,01h,D4h,01h
        db D2h,01h,D2h,01h,D2h,01h,D0h,01h,D0h,01h,D0h,01h,D0h,01h,CEh,01h
        db CEh,01h,CEh,01h,CCh,01h,CCh,01h,CCh,01h,CAh,01h,CAh,01h,CAh,01h
        db CAh,01h,C8h,01h,C8h,01h,C8h,01h,C6h,01h,C6h,01h,C6h,01h,C6h,01h
        db C4h,01h,C4h,01h,C4h,01h,C2h,01h,C2h,01h,C2h,01h,C0h,01h,C0h,01h
        db C0h,01h,C0h,01h,BEh,01h,BEh,01h,BEh,01h,BCh,01h,BCh,01h,BCh,01h
        db BCh,01h,BAh,01h,BAh,01h,BAh,01h,B8h,01h,B8h,01h,B8h,01h,B6h,01h
        db B6h,01h,B6h,01h,B6h,01h,B4h,01h,B4h,01h,B4h,01h,B2h,01h,B2h,01h
        db B2h,01h,B2h,01h,B0h,01h,B0h,01h,B0h,01h,AEh,01h,AEh,01h,AEh,01h
        db ACh,01h,ACh,01h,ACh,01h,ACh,01h,AAh,01h,AAh,01h,AAh,01h,A8h,01h
        db A8h,01h,A8h,01h,A8h,01h,A6h,01h,A6h,01h,A6h,01h,A4h,01h,A4h,01h
        db A4h,01h,A4h,01h,A2h,01h,A2h,01h,A2h,01h,A0h,01h,A0h,01h,A0h,01h
        db A0h,01h,9Eh,01h,9Eh,01h,9Eh,01h,9Ch,01h,9Ch,01h,9Ch,01h,9Ch,01h
        db 9Ah,01h,9Ah,01h,9Ah,01h,98h,01h,98h,01h,98h,01h,98h,01h,96h,01h
        db 96h,01h,96h,01h,94h,01h,94h,01h,94h,01h,94h,01h,92h,01h,92h,01h
        db 92h,01h,90h,01h,90h,01h,90h,01h,90h,01h,8Eh,01h,8Eh,01h,8Eh,01h
        db 8Ch,01h,8Ch,01h,8Ch,01h,8Ch,01h,8Ah,01h,8Ah,01h,8Ah,01h,88h,01h
        db 88h,01h,88h,01h,88h,01h,86h,01h,86h,01h,86h,01h,84h,01h,84h,01h
        db 84h,01h,84h,01h,82h,01h,82h,01h,82h,01h,80h,01h,80h,01h,80h,01h
        db 80h,01h,7Eh,01h,7Eh,01h,7Eh,01h,7Eh,01h,7Ch,01h,7Ch,01h,7Ch,01h
        db 7Ah,01h,7Ah,01h,7Ah,01h,7Ah,01h,78h,01h,78h,01h,78h,01h,76h,01h
        db 76h,01h,76h,01h,76h,01h,74h,01h,74h,01h,74h,01h,72h,01h,72h,01h
        db 72h,01h,72h,01h,70h,01h,70h,01h,70h,01h,70h,01h,6Eh,01h,6Eh,01h
        db 6Eh,01h,6Ch,01h,6Ch,01h,6Ch,01h,6Ch,01h,6Ah,01h,6Ah,01h,6Ah,01h
        db 6Ah,01h,68h,01h,68h,01h,68h,01h,66h,01h,66h,01h,66h,01h,66h,01h
        db 64h,01h,64h,01h,64h,01h,62h,01h,62h,01h,62h,01h,62h,01h,60h,01h
        db 60h,01h,60h,01h,60h,01h,5Eh,01h,5Eh,01h,5Eh,01h,5Ch,01h,5Ch,01h
        db 5Ch,01h,5Ch,01h,5Ah,01h,5Ah,01h,5Ah,01h,5Ah,01h,58h,01h,58h,01h
        db 58h,01h,56h,01h,56h,01h,56h,01h,56h,01h,54h,01h,54h,01h,54h,01h
        db 54h,01h,52h,01h,52h,01h,52h,01h,52h,01h,50h,01h,50h,01h,50h,01h
        db 4Eh,01h,4Eh,01h,4Eh,01h,4Eh,01h,4Ch,01h,4Ch,01h,4Ch,01h,4Ch,01h
        db 4Ah,01h,4Ah,01h,4Ah,01h,48h,01h,48h,01h,48h,01h,48h,01h,46h,01h
        db 46h,01h,46h,01h,46h,01h,44h,01h,44h,01h,44h,01h,44h,01h,42h,01h
        db 42h,01h,42h,01h,40h,01h,40h,01h,40h,01h,40h,01h,3Eh,01h,3Eh,01h
        db 3Eh,01h,3Eh,01h,3Ch,01h,3Ch,01h,3Ch,01h,3Ch,01h,3Ah,01h,3Ah,01h
        db 3Ah,01h,3Ah,01h,38h,01h,38h,01h,38h,01h,36h,01h,36h,01h,36h,01h
        db 36h,01h,34h,01h,34h,01h,34h,01h,34h,01h,32h,01h,32h,01h,32h,01h
        db 32h,01h,30h,01h,30h,01h,30h,01h,30h,01h,2Eh,01h,2Eh,01h,2Eh,01h
        db 2Ch,01h,2Ch,01h,2Ch,01h,2Ch,01h,2Ah,01h,2Ah,01h,2Ah,01h,2Ah,01h
        db 28h,01h,28h,01h,28h,01h,28h,01h,26h,01h,26h,01h,26h,01h,26h,01h
        db 24h,01h,24h,01h,24h,01h,24h,01h,22h,01h,22h,01h,22h,01h,20h,01h
        db 20h,01h,20h,01h,20h,01h,1Eh,01h,1Eh,01h,1Eh,01h,1Eh,01h,1Ch,01h
        db 1Ch,01h,1Ch,01h,1Ch,01h,1Ah,01h,1Ah,01h,1Ah,01h,1Ah,01h,18h,01h
        db 18h,01h,18h,01h,18h,01h,16h,01h,16h,01h,16h,01h,16h,01h,14h,01h
        db 14h,01h,14h,01h,14h,01h,12h,01h,12h,01h,12h,01h,10h,01h,10h,01h
        db 10h,01h,10h,01h,0Eh,01h,0Eh,01h,0Eh,01h,0Eh,01h,0Ch,01h,0Ch,01h
        db 0Ch,01h,0Ch,01h,0Ah,01h,0Ah,01h,0Ah,01h,0Ah,01h,08h,01h,08h,01h
        db 08h,01h,08h,01h,06h,01h,06h,01h,06h,01h,06h,01h,04h,01h,04h,01h
        db 04h,01h,04h,01h,02h,01h,02h,01h,02h,01h,02h,01h,00h,01h,00h,01h
        db 00h,01h,00h,01h,FEh,00h,FEh,00h,FEh,00h,FEh,00h,FCh,00h,FCh,00h
        db FCh,00h,FCh,00h,FAh,00h,FAh,00h,FAh,00h,FAh,00h,F8h,00h,F8h,00h
        db F8h,00h,F8h,00h,F6h,00h,F6h,00h,F6h,00h,F6h,00h,F4h,00h,F4h,00h
        db F4h,00h,F4h,00h,F2h,00h,F2h,00h,F2h,00h,F2h,00h,F0h,00h,F0h,00h
        db F0h,00h,F0h,00h,EEh,00h,EEh,00h,EEh,00h,EEh,00h,ECh,00h,ECh,00h
        db ECh,00h,ECh,00h,EAh,00h,EAh,00h,EAh,00h,EAh,00h,E8h,00h,E8h,00h
        db E8h,00h,E8h,00h,E6h,00h,E6h,00h,E6h,00h,E6h,00h,E4h,00h,E4h,00h
        db E4h,00h,E4h,00h,E2h,00h,E2h,00h,E2h,00h,E2h,00h,E0h,00h,E0h,00h
        db E0h,00h,E0h,00h,DEh,00h,DEh,00h,DEh,00h,DEh,00h,DEh,00h,DCh,00h
        db DCh,00h,DCh,00h,DCh,00h,DAh,00h,DAh,00h,DAh,00h,DAh,00h,D8h,00h
        db D8h,00h,D8h,00h,D8h,00h,D6h,00h,D6h,00h,D6h,00h,D6h,00h,D4h,00h
        db D4h,00h,D4h,00h,D4h,00h,D2h,00h,D2h,00h,D2h,00h,D2h,00h,D0h,00h
        db D0h,00h,D0h,00h,D0h,00h,CEh,00h,CEh,00h,CEh,00h,CEh,00h,CEh,00h
        db CCh,00h,CCh,00h,CCh,00h,CCh,00h,CAh,00h,CAh,00h,CAh,00h,CAh,00h
        db C8h,00h,C8h,00h,C8h,00h,C8h,00h,C6h,00h,C6h,00h,C6h,00h,C6h,00h
        db C4h,00h,C4h,00h,C4h,00h,C4h,00h,C2h,00h,C2h,00h,C2h,00h,C2h,00h
        db C2h,00h,C0h,00h,C0h,00h,C0h,00h,C0h,00h,BEh,00h,BEh,00h,BEh,00h
        db BEh,00h,BCh,00h,BCh,00h,BCh,00h,BCh,00h,BAh,00h,BAh,00h,BAh,00h
        db BAh,00h,B8h,00h,B8h,00h,B8h,00h,B8h,00h,B8h,00h,B6h,00h,B6h,00h
        db B6h,00h,B6h,00h,B4h,00h,B4h,00h,B4h,00h,B4h,00h,B2h,00h,B2h,00h
        db B2h,00h,B2h,00h,B0h,00h,B0h,00h,B0h,00h,B0h,00h,B0h,00h,AEh,00h
        db AEh,00h,AEh,00h,AEh,00h,ACh,00h,ACh,00h,ACh,00h,ACh,00h,AAh,00h
        db AAh,00h,AAh,00h,AAh,00h,AAh,00h,A8h,00h,A8h,00h,A8h,00h,A8h,00h
        db A6h,00h,A6h,00h,A6h,00h,A6h,00h,A4h,00h,A4h,00h,A4h,00h,A4h,00h
        db A2h,00h,A2h,00h,A2h,00h,A2h,00h,A2h,00h,A0h,00h,A0h,00h,A0h,00h
        db A0h,00h,9Eh,00h,9Eh,00h,9Eh,00h,9Eh,00h,9Ch,00h,9Ch,00h,9Ch,00h
        db 9Ch,00h,9Ch,00h,9Ah,00h,9Ah,00h,9Ah,00h,9Ah,00h,98h,00h,98h,00h
        db 98h,00h,98h,00h,96h,00h,96h,00h,96h,00h,96h,00h,96h,00h,94h,00h
        db 94h,00h,94h,00h,94h,00h,92h,00h,92h,00h,92h,00h,92h,00h,92h,00h
        db 90h,00h,90h,00h,90h,00h,90h,00h,8Eh,00h,8Eh,00h,8Eh,00h,8Eh,00h
        db 8Ch,00h,8Ch,00h,8Ch,00h,8Ch,00h,8Ch,00h,8Ah,00h,8Ah,00h,8Ah,00h
        db 8Ah,00h,88h,00h,88h,00h,88h,00h,88h,00h,88h,00h,86h,00h,86h,00h
        db 86h,00h,86h,00h,84h,00h,84h,00h,84h,00h,84h,00h,82h,00h,82h,00h
        db 82h,00h,82h,00h,82h,00h,80h,00h,80h,00h,80h,00h,80h,00h,7Eh,00h
        db 7Eh,00h,7Eh,00h,7Eh,00h,7Eh,00h,7Ch,00h,7Ch,00h,7Ch,00h,7Ch,00h
        db 7Ah,00h,7Ah,00h,7Ah,00h,7Ah,00h,7Ah,00h,78h,00h,78h,00h,78h,00h
        db 78h,00h,76h,00h,76h,00h,76h,00h,76h,00h,76h,00h,74h,00h,74h,00h
        db 74h,00h,74h,00h,72h,00h,72h,00h,72h,00h,72h,00h,72h,00h,70h,00h
        db 70h,00h,70h,00h,70h,00h,6Eh,00h,6Eh,00h,6Eh,00h,6Eh,00h,6Eh,00h
        db 6Ch,00h,6Ch,00h,6Ch,00h,6Ch,00h,6Ah,00h,6Ah,00h,6Ah,00h,6Ah,00h
        db 6Ah,00h,68h,00h,68h,00h,68h,00h,68h,00h,66h,00h,66h,00h,66h,00h
        db 66h,00h,66h,00h,64h,00h,64h,00h,64h,00h,64h,00h,64h,00h,62h,00h
        db 62h,00h,62h,00h,62h,00h,60h,00h,60h,00h,60h,00h,60h,00h,60h,00h
        db 5Eh,00h,5Eh,00h,5Eh,00h,5Eh,00h,5Ch,00h,5Ch,00h,5Ch,00h,5Ch,00h
        db 5Ch,00h,5Ah,00h,5Ah,00h,5Ah,00h,5Ah,00h,5Ah,00h,58h,00h,58h,00h
        db 58h,00h,58h,00h,56h,00h,56h,00h,56h,00h,56h,00h,56h,00h,54h,00h
        db 54h,00h,54h,00h,54h,00h,52h,00h,52h,00h,52h,00h,52h,00h,52h,00h
        db 50h,00h,50h,00h,50h,00h,50h,00h,50h,00h,4Eh,00h,4Eh,00h,4Eh,00h
        db 4Eh,00h,4Ch,00h,4Ch,00h,4Ch,00h,4Ch,00h,4Ch,00h,4Ah,00h,4Ah,00h
        db 4Ah,00h,4Ah,00h,4Ah,00h,48h,00h,48h,00h,48h,00h,48h,00h,46h,00h
        db 46h,00h,46h,00h,46h,00h,46h,00h,44h,00h,44h,00h,44h,00h,44h,00h
        db 44h,00h,42h,00h,42h,00h,42h,00h,42h,00h,42h,00h,40h,00h,40h,00h
        db 40h,00h,40h,00h,3Eh,00h,3Eh,00h,3Eh,00h,3Eh,00h,3Eh,00h,3Ch,00h
        db 3Ch,00h,3Ch,00h,3Ch,00h,3Ch,00h,3Ah,00h,3Ah,00h,3Ah,00h,3Ah,00h
        db 3Ah,00h,38h,00h,38h,00h,38h,00h,38h,00h,36h,00h,36h,00h,36h,00h
        db 36h,00h,36h,00h,34h,00h,34h,00h,34h,00h,34h,00h,34h,00h,32h,00h
        db 32h,00h,32h,00h,32h,00h,32h,00h,30h,00h,30h,00h,30h,00h,30h,00h
        db 2Eh,00h,2Eh,00h,2Eh,00h,2Eh,00h,2Eh,00h,2Ch,00h,2Ch,00h,2Ch,00h
        db 2Ch,00h,2Ch,00h,2Ah,00h,2Ah,00h,2Ah,00h,2Ah,00h,2Ah,00h,28h,00h
        db 28h,00h,28h,00h,28h,00h,28h,00h,26h,00h,26h,00h,26h,00h,26h,00h
        db 26h,00h,24h,00h,24h,00h,24h,00h,24h,00h,22h,00h,22h,00h,22h,00h
        db 22h,00h,22h,00h,20h,00h,20h,00h,20h,00h,20h,00h,20h,00h,1Eh,00h
        db 1Eh,00h,1Eh,00h,1Eh,00h,1Eh,00h,1Ch,00h,1Ch,00h,1Ch,00h,1Ch,00h
        db 1Ch,00h,1Ah,00h,1Ah,00h,1Ah,00h,1Ah,00h,1Ah,00h,18h,00h,18h,00h
        db 18h,00h,18h,00h,18h,00h,16h,00h,16h,00h,16h,00h,16h,00h,16h,00h
        db 14h,00h,14h,00h,14h,00h,14h,00h,14h,00h,12h,00h,12h,00h,12h,00h
        db 12h,00h,12h,00h,10h,00h,10h,00h,10h,00h,10h,00h,0Eh,00h,0Eh,00h
        db 0Eh,00h,0Eh,00h,0Eh,00h,0Ch,00h,0Ch,00h,0Ch,00h,0Ch,00h,0Ch,00h
        db 0Ah,00h,0Ah,00h,0Ah,00h,0Ah,00h,0Ah,00h,08h,00h,08h,00h,08h,00h
        db 08h,00h,08h,00h,06h,00h,06h,00h,06h,00h,06h,00h,06h,00h,04h,00h
        db 04h,00h,04h,00h,04h,00h,04h,00h,02h,00h,02h,00h,02h,00h,02h,00h
        db 02h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h
        db 00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h,00h
        db 00h,00h
PITCH_LUT_END:



; Resident gap 6288h..63FBh is outside mutable tracker state and below the
; dynamic stream window. Generic S3M/MOD/non-linear-XM engine uses it for the
; one-time shared-payload header alias installer.
        org 06288h

; Apply converter-generated OPL4 wave-header aliases once at INIT.
; Stream v3 appends N records after the 39-byte base header:
;   tone byte + 7 bytes (start[3], loop[2], end-complement[2]).
; PCM payload itself remains shared in MoonSound RAM.
apply_init_aliases:
        ld a,(STREAM_DATA+38)
        ld (ROW_COUNT_TMP),a
        or a
        ret z
        ld d,02h
        ld e,011h              ; external memory write enable
        call opl4_write_de
alias_init_loop:
        call read_stream_byte
        jr c,alias_init_done
        ld l,a
        ld h,0
        add hl,hl              ; *2
        add hl,hl              ; *4
        ld e,l
        ld d,h
        add hl,hl              ; *8
        add hl,de              ; *12
        push hl
        ld d,03h
        ld e,020h              ; custom header bank high address
        call opl4_write_de
        pop hl
        push hl
        ld d,04h
        ld e,h
        call opl4_write_de
        pop hl
        ld d,05h
        ld e,l
        call opl4_write_de
        ld a,006h
        out (07Eh),a
        call opl4_wait
        ld b,7
alias_init_bytes:
        call read_stream_byte
        jr c,alias_init_done
        out (07Fh),a
        djnz alias_init_bytes
        ld a,(ROW_COUNT_TMP)
        dec a
        ld (ROW_COUNT_TMP),a
        jr nz,alias_init_loop
alias_init_done:
        ld d,02h
        ld e,010h              ; normal wave-table mode / write disabled
        jp opl4_write_de

