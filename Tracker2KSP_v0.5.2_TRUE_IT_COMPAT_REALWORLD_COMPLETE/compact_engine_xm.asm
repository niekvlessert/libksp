
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
XMFLAGS         equ 05F1Eh      ; compact-stream XM behavior flags
FAST_VOL        equ XMFLAGS      ; persisted block compatibility alias
ROW_COUNT_TMP   equ 05F1Fh
LINEAR_XM       equ 05F21h
PREV_PFX        equ 05F22h      ; 24 bytes: bit0 previous arpeggio, bit1 previous vibrato
XMPROF          equ 05F3Ah      ; 24 bytes, FT2 sample/instrument profile id
XMPAN           equ 05F52h      ; 24 bytes, exact FT2 base panning 0..255
XMKEYOFF        equ 05F6Ah      ; 24 bytes
ENVVTICK        equ 05F82h      ; 24 words
ENVPTICK        equ 05FB2h      ; 24 words
VIBCTRL         equ 05FE2h      ; 24 bytes, E4x waveform/retrigger control

PERIOD_Q        equ 06000h      ; 24 words
TARGET_Q        equ 06030h      ; 24 words
VOLUME          equ 06060h      ; 24 bytes
WAVE            equ 06078h      ; 24 bytes, custom tone 0..63
KEYSTATE        equ 06090h      ; 24 bytes
CMD1            equ 060A8h
PAR1            equ 060C0h
CMD2            equ 060D8h
PAR2            equ 060F0h
CMD3            equ 06400h      ; 24 bytes, third FT2 realtime effect slot
PAR3            equ 06418h      ; 24 bytes
ROWDELAY        equ 06430h      ; 24 bytes, original FT2 EDx tick for vol-column quirks
ROWINS          equ 06448h      ; 24 bytes, literal instrument marker for FT2 row quirks
ROWNOTE         equ 06460h      ; 24 bytes, literal real note on current row
ROWVOL          equ 06478h      ; 24 bytes, nonzero volume-column volume on current row
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
FADEVOL         equ 06288h      ; 24 words, 0..32768
AUTOPOS         equ 062B8h      ; 24 bytes
AUTOAMP         equ 062D0h      ; 24 words, Q8 depth sweep
GLISS           equ 06300h      ; 24 bytes, E3x semitone-porta control
TREMSPD         equ 06318h      ; 24 bytes, FT2 7xy speed
TREMDEP         equ 06330h      ; 24 bytes, FT2 7xy depth
TREMPH          equ 06348h      ; 24 bytes, FT2 tremolo phase
TREMWAVE        equ 06360h      ; 24 bytes, E7x waveform/control
TREMORPAR       equ 06378h      ; 24 bytes, FT2 Txy memory
TREMORCNT       equ 06390h      ; 24 bytes, FT2 tremor state
RETRIGCNT       equ 063A8h      ; 24 bytes, FT2 Rxy running counter
GLOBALVOL       equ 063C0h      ; 0..64
TREMOFF         equ 063C1h      ; 24 signed bytes, transient tremolo volume offset
PATDELAY        equ 063D9h      ; FT2 EEx row-delay multiplier minus one
ROW_LIMIT       equ 063DAh      ; ticks on current row, clamped to 255
PANENVSTOP      equ 063DBh      ; 24 bytes: FT2 pan sustain reached before key-off
PAGE_TOTAL_CFG  equ 063FCh      ; patched by converter
STATE_CLEAR     equ 05F00h
STATE_CLEAR_END equ 063F3h

CMD_A           equ 1
CMD_D           equ 4
CMD_E           equ 5
CMD_F           equ 6
CMD_G           equ 7
CMD_H           equ 8
CMD_J           equ 10
CMD_O           equ 15
CMD_Q           equ 17
CMD_T           equ 20
CMD_X           equ 24
CMD_CUT         equ 27
CMD_XMPROF      equ 28
CMD_VCTRL       equ 29
CMD_GLISS       equ 30
CMD_KEYOFF      equ 31
CMD_XM_TREMOLO  equ 40
CMD_XM_VFNDN    equ 41
CMD_XM_VFNUP    equ 42
CMD_XM_VIBSPD   equ 43
CMD_XM_VIBDEP   equ 44
CMD_XM_PANLEFT  equ 45
CMD_XM_PANRIGHT equ 46
CMD_XM_VOLPORTA equ 47
CMD_XM_TREMWAVE equ 52
CMD_XM_E9RETRIG equ 53
CMD_XM_FVUP     equ 54
CMD_XM_FVDN     equ 55
CMD_XM_PATDELAY equ 56
CMD_XM_GVOL     equ 57
CMD_XM_GVOLSL   equ 58
CMD_XM_ENVPOS   equ 59
CMD_XM_PANSLIDE equ 60
CMD_XM_RETRIG   equ 61
CMD_XM_TREMOR   equ 62
CMD_XM_VC_VOLDN equ 66
CMD_XM_VC_VOLUP equ 67
CMD_XM_ROWINS   equ 68
CMD_XM_ROWDELAY equ 69
CMD_XM_ROWNOTE  equ 70
CMD_XM_ROWVOL   equ 71

init:
        xor a
        ld hl,STATE_CLEAR
        ld de,STATE_CLEAR+1
        ld bc,STATE_CLEAR_END-STATE_CLEAR-1
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
        ld a,6                    ; FT2 default when header speed is zero
init_speed_ok:
        ld (SPEED),a
        ld (ROW_LIMIT),a
        ld a,64
        ld (GLOBALVOL),a
        ld a,(STREAM_DATA+7)
        ld b,a
        ld (XMFLAGS),a            ; bits 1..7: linear, arp, env escape, pan sustain, auto-vib abort, porta-dir, target-preserve
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
        ld a,(ROW_LIMIT)
        cp b
        jr c,process_row_done
        jr z,process_row_done
        ld a,b
        ld (ROW_TICK),a
        ret
process_row_done:
        xor a
        ld (ROW_TICK),a
        ret

parse_row:
        ; Clear row-local effects and expire delayed actions from a malformed prior row.
        xor a
        ld (PATDELAY),a
        ld a,(SPEED)
        ld (ROW_LIMIT),a
        xor a
        ld hl,CMD1
        ld de,CMD1+1
        ld bc,96-1
        ld (hl),a
        ldir
        ; CMD3/PAR3 live in the otherwise unused 06400h area, outside the
        ; contiguous legacy row-effect block above.
        ld hl,CMD3
        ld de,CMD3+1
        ld bc,144-1
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
        call xm_update_row_limit
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
        cp CMD_XM_GVOL
        jr nz,fx_not_gvol
        ld a,e
        cp 65
        jr c,fx_gvol_ok
        ld a,64
fx_gvol_ok:
        ld (GLOBALVOL),a
        jp fx_extra
fx_not_gvol:
        cp CMD_XM_PATDELAY
        jr nz,fx_not_patdelay
        ld a,e
        and 0Fh
        ld (PATDELAY),a
        call xm_update_row_limit
        jp fx_extra
fx_not_patdelay:
        cp CMD_XM_ROWDELAY
        jr nz,fx_not_rowdelay
        ld a,e
        and 0Fh
        ld hl,ROWDELAY
        call ptr8_cur
        ld (hl),a
        jp fx_extra
fx_not_rowdelay:
        cp CMD_XM_ROWNOTE
        jr nz,fx_not_rownote
        ld a,1
        ld hl,ROWNOTE
        call ptr8_cur
        ld (hl),a
        jp fx_extra
fx_not_rownote:
        cp CMD_XM_ROWVOL
        jr nz,fx_not_rowvol
        ld a,1
        ld hl,ROWVOL
        call ptr8_cur
        ld (hl),a
        jp fx_extra
fx_not_rowvol:
        cp CMD_XM_ROWINS
        jr nz,fx_not_rowins
        ld a,1
        ld hl,ROWINS
        call ptr8_cur
        ld (hl),a
        jp fx_extra
fx_not_rowins:
        ; FT2 profile resets are row-start actions, not continuing tick effects.
        ; Apply them immediately so they do not consume one of the three realtime
        ; effect slots (important for instrument+porta+volume-column combinations).
        cp CMD_XMPROF
        jr nz,fx_not_profile
        ld a,e
        call xm_reset_profile_a
        jp fx_extra
fx_not_profile:
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
        or a
        jr nz,fx_store_2
        ld hl,CMD1
        call ptr8_cur
        ld (hl),d
        ld hl,PAR1
        call ptr8_cur
        ld (hl),e
        ld a,1
        ld (FX_SLOT),a
        jp fx_extra
fx_store_2:
        cp 2
        jr nc,fx_store_3
        ld hl,CMD2
        call ptr8_cur
        ld (hl),d
        ld hl,PAR2
        call ptr8_cur
        ld (hl),e
        ld a,2
        ld (FX_SLOT),a
        jp fx_extra
fx_store_3:
        cp 3
        jr nc,fx_extra             ; standard FT2 needs at most three continuing effects
        ld hl,CMD3
        call ptr8_cur
        ld (hl),d
        ld hl,PAR3
        call ptr8_cur
        ld (hl),e
        ld a,3
        ld (FX_SLOT),a
fx_extra:
        ld a,d
        cp CMD_J
        jr nz,fx_done
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
        and 040h
        jr nz,queue_delayed_note
        jr do_normal_note
finish_no_note:
        ret

do_porta_target:
        ld hl,TARGET_Q
        call ptr16_cur
        ld de,(EV_PERIOD)
        ld (hl),e
        inc hl
        ld (hl),d
        ; A new tone-portamento target resets FT2's remembered arrival direction.
        ld hl,GLISS
        call ptr8_cur
        ld a,(hl)
        and 07Fh
        ld (hl),a
        ret

do_note_off:
        jp xm_note_off

queue_delayed_note:
        ld a,(EV_DELAY)
        ld b,a
        ld hl,DELAY_TICK
        call ptr8_cur
        ld (hl),b
        ld hl,ROWDELAY
        call ptr8_cur
        ld (hl),b
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
        ; Save base quarter-period. Genuine FT2 deliberately keeps an older
        ; tone-portamento target across ordinary new notes (Porta-Pickup.xm).
        ld de,(EV_PERIOD)
        ld hl,PERIOD_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld a,(XMFLAGS)
        bit 7,a
        jr nz,normal_target_done
        ld hl,TARGET_Q
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ld hl,GLISS
        call ptr8_cur
        ld a,(hl)
        and 07Fh
        ld (hl),a
normal_target_done:
        ld a,(EV_TONE)
        ld hl,WAVE
        call ptr8_cur
        ld (hl),a
        ; XM engine: profile/envelope state is independent of linear-vs-Amiga periods.
        ld a,(EV_TONE)
        ld e,a
        ld d,0
        ld hl,XM_TONE_PROFILE
        add hl,de
        ld a,(hl)
        ld b,a
        ld a,(EV_NOTE_KIND)
        bit 1,a                   ; bare XM note: no literal instrument column
        ld a,b
        jr z,normal_reset_profile_full
        call xm_reset_profile_preserve_pan_a
        jr normal_profile_done
normal_reset_profile_full:
        call xm_reset_profile_a
        ; FT2: a literal instrument number disables/re-arms tremor.
        ; The host marks bare notes (no instrument column) in EV_NOTE_KIND bit 1.
        ld a,020h
        ld hl,TREMORCNT
        call ptr8_cur
        ld (hl),a
normal_profile_done:
        ; E4x bit 2 means don't retrigger manual vibrato phase.
        ld hl,VIBCTRL
        call ptr8_cur
        bit 2,(hl)
        jr nz,normal_vib_done
normal_reset_vib:
        xor a
        ld hl,VIBPH
        call ptr8_cur
        ld (hl),a
normal_vib_done:
        ; E7x bit 2 independently controls tremolo-phase retrigger.
        ld hl,TREMWAVE
        call ptr8_cur
        bit 2,(hl)
        jr nz,normal_trem_done
        xor a
        ld hl,TREMPH
        call ptr8_cur
        ld (hl),a
normal_trem_done:
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

xm_update_row_limit:
        ; ROW_LIMIT = SPEED * (PATDELAY+1), saturating at 255.
        ld a,(PATDELAY)
        inc a
        ld b,a
        ld a,(SPEED)
        ld c,a
        xor a
xm_rowlim_mul:
        add a,c
        jr c,xm_rowlim_sat
        djnz xm_rowlim_mul
        or a
        jr nz,xm_rowlim_store
        inc a
xm_rowlim_store:
        ld (ROW_LIMIT),a
        ret
xm_rowlim_sat:
        ld a,0FFh
        jr xm_rowlim_store

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
        call row_pitch_reset_check
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
        ld hl,CMD3
        call ptr8_cur
        ld d,(hl)
        ld hl,PAR3
        call ptr8_cur
        ld e,(hl)
        call apply_effect_de
        call xm_tick_modulators
        ld a,(PITCH_DIRTY)
        or a
        call nz,emit_pitch_approx
        ld a,(CUR_CH)
        inc a
        ld (CUR_CH),a
        cp 24
        jr c,process_ch_loop
        ret

; FT2 row-boundary pitch reset semantics.
; - a previous arpeggio always restores real/base period at the next row tick 0;
; - previous vibrato restores base period when the current row no longer has vibrato.
; CMD_H also represents 6xy's vibrato half and the supported volume-column vibrato.
row_pitch_reset_check:
        ld a,(TICK_NOW)
        or a
        ret nz
        xor a
        ld hl,TREMOFF
        call ptr8_cur
        ld (hl),a
        ld hl,PREV_PFX
        call ptr8_cur
        ld b,(hl)                ; previous-row flags
        ld c,0                   ; current-row flags
        ld hl,CMD1
        call ptr8_cur
        ld a,(hl)
        cp CMD_J
        jr nz,row_pfx_cmd1_not_j
        set 0,c
row_pfx_cmd1_not_j:
        cp CMD_H
        jr nz,row_pfx_cmd2
        set 1,c
row_pfx_cmd2:
        ld hl,CMD2
        call ptr8_cur
        ld a,(hl)
        cp CMD_J
        jr nz,row_pfx_cmd2_not_j
        set 0,c
row_pfx_cmd2_not_j:
        cp CMD_H
        jr nz,row_pfx_cmd3
        set 1,c
row_pfx_cmd3:
        ld hl,CMD3
        call ptr8_cur
        ld a,(hl)
        cp CMD_J
        jr nz,row_pfx_cmd3_not_j
        set 0,c
row_pfx_cmd3_not_j:
        cp CMD_H
        jr nz,row_pfx_decide
        set 1,c
row_pfx_decide:
        bit 0,b                  ; previous arpeggio: always restore on row start
        jr nz,row_pfx_restore
        bit 1,b                  ; previous vibrato...
        jr z,row_pfx_store
        bit 1,c                  ; ...continues only when current row still has H
        jr nz,row_pfx_store
row_pfx_restore:
        ld a,1
        ld (PITCH_DIRTY),a       ; OUT_PERIOD already contains current real/base period
row_pfx_store:
        ld a,c
        ld hl,PREV_PFX
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
        ld (EV_NOTE_KIND),a
        cp 0FFh
        jr nz,delay_not_keyoff
        ; FT2 Off+EDx retriggers envelope/sample settings but does NOT key-off
        ; or start fadeout (OpenMPT OffDelay.xm behaviour). Pending default
        ; volume, when appropriate, was already applied above.
        jp xm_reset_current_profile_clocks
delay_not_keyoff:
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
        cp CMD_J
        jp z,effect_arpeggio
        cp CMD_Q
        jp z,effect_retrig
        cp CMD_CUT
        jp z,effect_note_cut
        cp CMD_XMPROF
        jp z,effect_xm_profile
        cp CMD_VCTRL
        jp z,effect_vibctrl
        cp CMD_GLISS
        jp z,effect_gliss
        cp CMD_KEYOFF
        jp z,effect_xm_keyoff
        cp CMD_XM_TREMOLO
        jp z,effect_xm_tremolo
        cp CMD_XM_VFNDN
        jp z,effect_xm_vfine_down
        cp CMD_XM_VFNUP
        jp z,effect_xm_vfine_up
        cp CMD_XM_VIBSPD
        jp z,effect_xm_vibspeed
        cp CMD_XM_VIBDEP
        jp z,effect_xm_vibdepth
        cp CMD_XM_PANLEFT
        jp z,effect_xm_panleft
        cp CMD_XM_PANRIGHT
        jp z,effect_xm_panright
        cp CMD_XM_VOLPORTA
        jp z,effect_xm_volporta
        cp CMD_XM_E9RETRIG
        jp z,effect_xm_e9retrig
        cp CMD_XM_FVUP
        jp z,effect_xm_fvup
        cp CMD_XM_FVDN
        jp z,effect_xm_fvdn
        cp CMD_XM_GVOLSL
        jp z,effect_xm_gvolslide
        cp CMD_XM_TREMWAVE
        jp z,effect_xm_tremwave
        cp CMD_XM_ENVPOS
        jp z,effect_xm_envpos
        cp CMD_XM_PANSLIDE
        jp z,effect_xm_panslide
        cp CMD_XM_RETRIG
        jp z,effect_xm_retrig
        cp CMD_XM_TREMOR
        jp z,effect_xm_tremor
        cp CMD_XM_VC_VOLDN
        jp z,effect_xm_vc_voldown
        cp CMD_XM_VC_VOLUP
        jp z,effect_xm_vc_volup
        ret

; Return NZ when a non-volume/panning FT2 volume-column command is
; allowed on this tick. With EDx, FT2 skips row tick 0 and also skips the
; delayed start tick when a literal instrument is present.
xm_volcol_allowed:
        ld hl,ROWDELAY
        call ptr8_cur
        ld b,(hl)
        ld a,b
        or a
        jr z,xm_vca_allowed
        ld a,(TICK_NOW)
        or a
        ret z
        cp b
        jr nz,xm_vca_allowed
        ld hl,ROWINS
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_vca_allowed
        xor a
        ret
xm_vca_allowed:
        ld a,1
        or a
        ret

; Same as above but volume-column tone-portamento also skips the delayed
; start tick even when there is no instrument number.
xm_volcol_porta_allowed:
        ld hl,ROWDELAY
        call ptr8_cur
        ld b,(hl)
        ld a,b
        or a
        jr z,xm_vcpa_allowed
        ld a,(TICK_NOW)
        or a
        ret z
        cp b
        jr z,xm_vcpa_skip
xm_vcpa_allowed:
        ld a,1
        or a
        ret
xm_vcpa_skip:
        xor a
        ret

effect_xm_vc_voldown:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0Fh
        or a
        ret z
        jp volume_sub_a

effect_xm_vc_volup:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0Fh
        or a
        ret z
        jp volume_add_a

effect_volume_slide:
        ; FT2 Axy / 5xy / 6xy: high-nibble priority, no S3M/IT fine forms.
        ; Slides execute only on non-row ticks. EAx/EBx are separate commands.
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0F0h
        jr z,xm_volslide_down
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        jp volume_add_a
xm_volslide_down:
        ld a,e
        and 0Fh
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
        jr nz,porta_compare_done
        ; FT2 remembers the direction from which a tone-portamento reached
        ; its target. On a later row that starts exactly at the old target,
        ; it may continue in the previous upward-period direction.
        ld a,(XMFLAGS)
        bit 6,a
        jr z,porta_done
        push hl
        ld hl,GLISS
        call ptr8_cur
        bit 7,(hl)
        pop hl
        jr nz,porta_current_lower
        jr porta_done
porta_compare_done:
        jr c,porta_current_lower
        ; current > target: subtract step, clamp at target
        ex de,hl                  ; DE=step, HL=current
        or a
        sbc hl,de
        push hl
        or a
        sbc hl,bc
        jr c,porta_high_clamp
        jr z,porta_high_exact
        pop hl
        jr porta_store
porta_high_clamp:
        pop hl
        ld h,b
        ld l,c
        jr porta_high_reached
porta_high_exact:
        pop hl
porta_high_reached:
        call porta_mark_reached
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

; Preserve HL and mark that FT2 reached the current porta target from the
; current>target direction. The flag shares GLISS bit 7; E3x uses low bits.
porta_mark_reached:
        ld a,(XMFLAGS)
        bit 6,a
        ret z
        push hl
        ld hl,GLISS
        call ptr8_cur
        set 7,(hl)
        pop hl
        ret

effect_vibrato:
        ld a,(TICK_NOW)
        or a
        ret z
        ; FT2 vibrato waveform/timing is used for both linear and Amiga XM.

        ; FastTracker II vibrato: 8-bit phase, table index=(phase>>2)&31,
        ; speed memory is the high nibble but the phase increment is x*4.
        ld hl,VIBPH
        call ptr8_cur
        ld a,(hl)
        ld c,a                    ; C=full signed phase
        srl a
        srl a
        and 1Fh
        ld e,a                    ; table/ramp index
        ld hl,VIBCTRL
        call ptr8_cur
        ld a,(hl)
        and 3
        cp 1
        jr z,ft2_vib_ramp
        cp 2
        jr nc,ft2_vib_square
        ld d,0
        ld hl,FT2_VIB_TAB
        add hl,de
        ld e,(hl)                 ; sine amplitude 0..255
        jr ft2_vib_wave_ready
ft2_vib_ramp:
        ld a,e
        add a,a
        add a,a
        add a,a
        bit 7,c
        jr z,ft2_vib_ramp_ready
        cpl
ft2_vib_ramp_ready:
        ld e,a
        jr ft2_vib_wave_ready
ft2_vib_square:
        ld e,255
ft2_vib_wave_ready:
        ld hl,VIBDEP
        call ptr8_cur
        ld b,(hl)                 ; depth 0..15
        ld hl,0
ft2_vib_mul:
        ld a,b
        or a
        jr z,ft2_vib_mul_done
        ld d,0
        add hl,de
        dec b
        jr ft2_vib_mul
ft2_vib_mul_done:
        ; logical >>5 exactly like FT2
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
        ex de,hl                  ; DE=period delta
        ld hl,(OUT_PERIOD)
        bit 7,c
        jr nz,ft2_vib_negative_phase
        add hl,de
        jr ft2_vib_store
ft2_vib_negative_phase:
        or a
        sbc hl,de
        jr nc,ft2_vib_store
        ld hl,1
ft2_vib_store:
        ld (OUT_PERIOD),hl
        ld a,d
        or e
        jr z,ft2_vib_advance
        ld a,1
        ld (PITCH_DIRTY),a
ft2_vib_advance:
        ld hl,VIBSPD
        call ptr8_cur
        ld a,(hl)
        add a,a
        add a,a                   ; speed nibble * 4
        add a,c                   ; 8-bit wrap is intentional
        ld hl,VIBPH
        call ptr8_cur
        ld (hl),a
        ret

effect_vibrato_legacy:
        ; S3M/MOD legacy 64-step signed vibrato.
        ld hl,VIBPH
        call ptr8_cur
        ld a,(hl)
        and 3Fh
        ld e,a
        ld d,0
        ld hl,SINE_TABLE
        add hl,de
        ld a,(hl)
        ld b,a
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

effect_arpeggio:
        ld a,(TICK_NOW)
        or a
        ret z                      ; FT2 and clone modes: tick 0 is base note
        ld a,(XMFLAGS)
        bit 2,a
        jr z,arp_generic
        ; FT2's 16-entry arpeggio-position LUT is indexed backwards from
        ; speed. At >=16 ticks/row it famously reads into the next table.
        ld a,(TICK_NOW)
        ld b,a
        ld a,(SPEED)
        ld c,a
        ld a,b
arp_tick_mod_speed:
        cp c
        jr c,arp_tick_rem_ready
        sub c
        jr arp_tick_mod_speed
arp_tick_rem_ready:
        ld b,a                    ; remainder = tick % speed
        ld a,c
        sub b                     ; FT2 arpPos = speed - remainder
        cp 17
        jr c,arp_ft2_le16
        ld a,2
        jr arp_pos_ready
arp_ft2_le16:
        cp 16
        jr nz,arp_ft2_mod3
        xor a
        jr arp_pos_ready
arp_ft2_mod3:
arp_ft2_mod3_loop:
        cp 3
        jr c,arp_pos_ready
        sub 3
        jr arp_ft2_mod3_loop
arp_generic:
        ld a,(TICK_NOW)
arp_generic_mod3:
        cp 3
        jr c,arp_pos_ready
        sub 3
        jr arp_generic_mod3
arp_pos_ready:
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
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0Fh
        ret z
        ld b,a                    ; interval
        ld a,(TICK_NOW)
retrig_mod:
        cp b
        jr c,retrig_mod_done
        sub b
        jr retrig_mod
retrig_mod_done:
        or a
        ret nz
        ; Volume transform x is intentionally complete for S3M Qxy.
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
        ; x=6 (5/8) and x=14 (3/2) use exact integer transforms.
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
        ; FT2/ST3 retrig transform x=6 is *10/16 = *5/8 exactly.
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)
        ld b,a
        srl a                    ; /2
        ld c,a
        ld a,b
        srl a
        srl a
        srl a                    ; /8
        add a,c                  ; 5/8 (integer truncation)
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
        jp keyoff_current

effect_xm_profile:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        call xm_reset_profile_a
        ; FT2: any explicit instrument number disables/re-arms tremor.
        ld a,020h
        ld hl,TREMORCNT
        call ptr8_cur
        ld (hl),a
        ret

effect_vibctrl:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        ld hl,VIBCTRL
        call ptr8_cur
        ld (hl),a
        ret

effect_gliss:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        ld b,a
        ld hl,GLISS
        call ptr8_cur
        ld a,(hl)
        and 080h                  ; high bit is FT2 portaTargetReached state
        or b
        ld (hl),a
        ret

effect_xm_keyoff:
        ld a,(TICK_NOW)
        cp e
        ret nz
        jp xm_note_off

effect_xm_vfine_down:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        jp volume_sub_a

effect_xm_vfine_up:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        jp volume_add_a

effect_xm_vibspeed:
        call xm_volcol_allowed
        ret z
        ld a,e
        and 0Fh
        jp store_vib_speed

effect_xm_vibdepth:
        ; Volume-column Bx changes depth and enables FT2 vibrato on non-row ticks.
        call xm_volcol_allowed
        ret z
        ld a,e
        and 0Fh
        call store_vib_depth
        ld a,(TICK_NOW)
        or a
        ret z
        jp effect_vibrato

effect_xm_panleft:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0Fh
        jr nz,xm_panleft_nonzero
        xor a                     ; FT2 D0 volume-column pan slide quirk
        jp set_pan_from_tracker
xm_panleft_nonzero:
        ld b,a                    ; FT2 volume-column slide is +/- nibble
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        cp b
        jr nc,xm_panleft_sub
        xor a
        jp set_pan_from_tracker
xm_panleft_sub:
        sub b
        jp set_pan_from_tracker

effect_xm_panright:
        call xm_volcol_allowed
        ret z
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0Fh
        ret z
        ld b,a
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        add a,b
        jr nc,xm_panright_ok
        ld a,255
xm_panright_ok:
        jp set_pan_from_tracker

effect_xm_volporta:
        ; Volume-column Fx step is translated by FT2 to a coarser tone-porta.
        call xm_volcol_porta_allowed
        ret z
        ld a,e
        and 0Fh
        ret z
        add a,a
        add a,a
        add a,a
        add a,a
        ld e,a
        jp effect_porta

effect_xm_fvup:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        jp volume_add_a

effect_xm_fvdn:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 0Fh
        jp volume_sub_a

effect_xm_panslide:
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0F0h
        jr z,xm_panslide_left
        ; FT2 gives high nibble priority; +high/16 in exact 0..255 pan domain.
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        ld b,a
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        add a,b
        jr nc,xm_panslide_store
        ld a,255
        jr xm_panslide_store
xm_panslide_left:
        ld a,e
        and 0Fh
        ld b,a
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        cp b
        jr nc,xm_panslide_sub
        xor a
        jr xm_panslide_store
xm_panslide_sub:
        sub b
xm_panslide_store:
        jp set_pan_from_tracker

effect_xm_gvolslide:
        ; FT2 Hxy global-volume slide: high-nibble priority, ordinary slide
        ; only on non-row ticks. There are no FT2 fine-global-volume forms.
        ld a,(TICK_NOW)
        or a
        ret z
        ld a,e
        and 0F0h
        jr z,xm_gvol_regular_down
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        jr xm_gvol_add_a
xm_gvol_regular_down:
        ld a,e
        and 0Fh
        or a
        ret z
xm_gvol_sub_a:
        ld b,a
        ld a,(GLOBALVOL)
        cp b
        jr nc,xm_gvol_sub_ok
        xor a
        jr xm_gvol_store
xm_gvol_sub_ok:
        sub b
        jr xm_gvol_store
xm_gvol_add_a:
        ld b,a
        ld a,(GLOBALVOL)
        add a,b
        cp 65
        jr c,xm_gvol_store
        ld a,64
xm_gvol_store:
        ld (GLOBALVOL),a
        ret

effect_xm_tremwave:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        and 07h
        ld hl,TREMWAVE
        call ptr8_cur
        ld (hl),a
        ret

effect_xm_envpos:
        ld a,(TICK_NOW)
        or a
        ret nz
        ld a,e
        jp xm_set_env_position_a

effect_xm_e9retrig:
        ; FT2 E90 retriggers instantly once on tick 0. E9x (x>0) triggers on
        ; tick multiples x, except a fresh note already triggered at tick 0.
        ld a,e
        and 0Fh
        jr nz,xm_e9_nonzero
        ld a,(TICK_NOW)
        or a
        ret nz
        call keyoff_current
        jp keyon_current
xm_e9_nonzero:
        ld b,a
        ld a,(TICK_NOW)
        or a
        ret z
xm_e9_mod:
        cp b
        jr c,xm_e9_done
        sub b
        jr xm_e9_mod
xm_e9_done:
        or a
        ret nz
        call keyoff_current
        jp keyon_current

effect_xm_retrig:
        ; Bug-compatible FT2 Rxy counter. Unlike E9x, interval 0 is valid and
        ; effectively retriggers every eligible tick. Rxy does not reset XM
        ; envelopes on retrigger.
        ld a,e
        and 0Fh
        ld b,a                    ; B=speed
        ld hl,RETRIGCNT
        call ptr8_cur
        ld c,(hl)                 ; C=running FT2 retrig count
        ld a,(TICK_NOW)
        or a
        jr nz,xm_r_after_tick0
        ; On tick 0 an instrument number next to note-or-empty forces local
        ; retrigCount=1. The host does not set ROWINS for Note Off rows.
        push hl
        ld hl,ROWINS
        call ptr8_cur
        ld a,(hl)
        pop hl
        or a
        jr z,xm_r_tick0_no_ins
        ld c,1
xm_r_tick0_no_ins:
        ; A non-zero volume-column volume causes FT2 to save the count and
        ; return immediately on tick 0.
        push hl
        ld hl,ROWVOL
        call ptr8_cur
        ld a,(hl)
        pop hl
        or a
        jr z,xm_r_after_tick0
        ld (hl),c
        ret
xm_r_after_tick0:
        ; if retrigCount >= retrigSpeed, retrigger except on tick0 with a real
        ; note (the normal note trigger already happened there).
        ld a,c
        cp b
        jr c,xm_r_no_trigger
        ld a,(TICK_NOW)
        or a
        jr nz,xm_r_do_trigger
        push hl
        ld hl,ROWNOTE
        call ptr8_cur
        ld a,(hl)
        pop hl
        or a
        jr nz,xm_r_no_trigger
xm_r_do_trigger:
        ld c,0
        ; FT2 suppresses Rxy's volume transform whenever a volume-column
        ; volume is present on the row.
        push hl
        ld hl,ROWVOL
        call ptr8_cur
        ld a,(hl)
        pop hl
        or a
        jr nz,xm_r_rekey
        ld a,e
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        and 0Fh
        call retrig_adjust_volume
xm_r_rekey:
        call keyoff_current
        call keyon_current
        ld c,1                    ; FT2 increments retrigCount after a retrigger
        jr xm_r_store_count
xm_r_no_trigger:
        inc c
xm_r_store_count:
        ld hl,RETRIGCNT
        call ptr8_cur
        ld (hl),c
        ret

effect_xm_tremolo:
        ; 7xy: calculate a transient signed volume offset. Phase advances on
        ; non-row ticks by speed*4 in FT2's 8-bit phase domain.
        ld a,(TICK_NOW)
        or a
        ret z
        ld hl,TREMSPD
        call ptr8_cur
        ld a,e
        and 0F0h
        jr z,xm_trem_spd_keep
        rrca
        rrca
        rrca
        rrca
        ld (hl),a
xm_trem_spd_keep:
        ld hl,TREMDEP
        call ptr8_cur
        ld a,e
        and 0Fh
        jr z,xm_trem_dep_keep
        ld (hl),a
xm_trem_dep_keep:
        ld hl,TREMPH
        call ptr8_cur
        ld a,(hl)
        ld c,a
        srl a
        srl a
        and 1Fh
        ld e,a
        ld hl,TREMWAVE
        call ptr8_cur
        ld a,(hl)
        and 3
        cp 1
        jr z,xm_trem_ramp
        cp 2
        jr nc,xm_trem_square
        ld d,0
        ld hl,FT2_VIB_TAB
        add hl,de
        ld a,(hl)
        jr xm_trem_wave_ready
xm_trem_ramp:
        ld a,e
        add a,a
        add a,a
        add a,a
        bit 7,c
        jr z,xm_trem_wave_ready
        cpl
        jr xm_trem_wave_ready
xm_trem_square:
        ld a,255
xm_trem_wave_ready:
        ld e,a
        ld hl,TREMDEP
        call ptr8_cur
        ld b,(hl)
        ld hl,0
xm_trem_mul:
        ld a,b
        or a
        jr z,xm_trem_mul_done
        ld d,0
        add hl,de
        dec b
        jr xm_trem_mul
xm_trem_mul_done:
        ; FT2 tremolo depth scale: amplitude*depth >> 6, then channel volume
        ; unit is 4 internally; our VOLUME domain is already 0..64 -> >>8.
        ld a,h
        bit 7,c
        jr z,xm_trem_sign_ok
        neg
xm_trem_sign_ok:
        ld hl,TREMOFF
        call ptr8_cur
        ld (hl),a
        ld hl,TREMSPD
        call ptr8_cur
        ld a,(hl)
        add a,a
        add a,a
        add a,c
        ld hl,TREMPH
        call ptr8_cur
        ld (hl),a
        ret

effect_xm_tremor:
        ; FT2 Txy state machine (OpenMPT kFT2Tremor semantics).
        ; Bit 7 means the state machine is active. Bits 7..5 == 100 are
        ; the OFF phase; 110 is the ON phase. Bit 5 is also used by FT2
        ; as the "instrument number just seen" recovery marker.
        ld a,e
        or a
        jr z,xm_tremor_param_done
        ld hl,TREMORPAR
        call ptr8_cur
        ld (hl),a
xm_tremor_param_done:
        ld hl,TREMORCNT
        call ptr8_cur
        ld a,(TICK_NOW)
        or a
        jr nz,xm_tremor_nonfirst
        ; ProcessEffects on FT2 tick 0 only arms the tremor state.
        ld a,(hl)
        or 080h
        ld (hl),a
        ret
xm_tremor_nonfirst:
        ; Only a continuing Txy row advances the state machine. The command
        ; dispatcher guarantees that we are executing Txy here.
        ld a,(hl)
        and 0DFh                 ; clear FT2 instrument marker bit 5
        cp 080h
        jr z,xm_tremor_off_done
        cp 0C0h
        jr z,xm_tremor_on_done
        dec a
        ld (hl),a
        ret
xm_tremor_off_done:
        ; End of OFF time -> enter ON phase with high nibble count.
        push hl
        ld hl,TREMORPAR
        call ptr8_cur
        ld a,(hl)
        and 0F0h
        rrca
        rrca
        rrca
        rrca
        or 0C0h
        pop hl
        ld (hl),a
        ret
xm_tremor_on_done:
        ; End of ON time -> enter OFF phase with low nibble count.
        push hl
        ld hl,TREMORPAR
        call ptr8_cur
        ld a,(hl)
        and 00Fh
        or 080h
        pop hl
        ld (hl),a
        ret

xm_reset_current_profile_clocks:
        ld hl,XMPROF
        call ptr8_cur
        ld a,(hl)
        jp xm_reset_profile_a

xm_set_env_position_a:
        ; Lxx sets both volume and panning envelope positions. The envelope
        ; evaluator increments before lookup, hence store xx-1 (FFFF for 0).
        ld e,a
        ld d,0
        dec de
        ld hl,ENVVTICK
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ; FT2 only applies Lxx to the panning envelope when the volume
        ; envelope has its sustain flag set (SetEnvPos.xm quirk).
        push de
        call xm_profile_current
        ld a,(hl)
        bit 1,a
        pop de
        ret z
        ld hl,ENVPTICK
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        ret

xm_profile_ptr_a:
        and 3Fh
        add a,a
        ld e,a
        ld d,0
        ld hl,XM_PROFILE_PTRS
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ex de,hl
        ret

xm_profile_current:
        ld hl,XMPROF
        call ptr8_cur
        ld a,(hl)
        jp xm_profile_ptr_a

xm_reset_profile_a:
        ; A=deduplicated FT2 profile id.
        push af
        ld hl,XMPROF
        call ptr8_cur
        pop af
        ld (hl),a
        push af
        call xm_profile_ptr_a
        inc hl                     ; +1 base pan
        ld a,(hl)
        call set_pan_from_tracker
        pop af
        ; envelope clocks start at 0xFFFF so first update becomes tick 0.
        ld hl,ENVVTICK
        call ptr16_cur
        ld (hl),0FFh
        inc hl
        ld (hl),0FFh
        ld hl,ENVPTICK
        call ptr16_cur
        ld (hl),0FFh
        inc hl
        ld (hl),0FFh
        xor a
        ld hl,PANENVSTOP
        call ptr8_cur
        ld (hl),a
        ld hl,XMKEYOFF
        call ptr8_cur
        ld (hl),a
        ld hl,AUTOPOS
        call ptr8_cur
        ld (hl),a
        ; fadeoutVol is 32768 at instrument trigger.
        ld hl,FADEVOL
        call ptr16_cur
        ld (hl),0
        inc hl
        ld (hl),080h
        ; auto-vibrato starts at full depth when sweep=0, otherwise at zero.
        ld hl,AUTOAMP
        call ptr16_cur
        ld (hl),0
        inc hl
        ld (hl),0
        call xm_profile_current
        ld de,8                    ; sweep step word
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        ret nz
        ; no sweep: initial amp = depth << 8
        call xm_profile_current
        ld de,5                    ; auto depth
        add hl,de
        ld a,(hl)
        ld hl,AUTOAMP
        call ptr16_cur
        ld (hl),0
        inc hl
        ld (hl),a
        ret

xm_reset_profile_preserve_pan_a:
        ; A=profile. A bare FT2 note retriggers envelopes/auto-vibrato but
        ; does not recall the sample's default panning (PanMemory.xm).
        push af
        ld hl,XMPAN
        call ptr8_cur
        ld b,(hl)
        pop af
        push bc
        call xm_reset_profile_a
        pop bc
        ld a,b
        jp set_pan_from_tracker

xm_note_off:
        ld a,1
        ld hl,XMKEYOFF
        call ptr8_cur
        ld (hl),a
        call xm_profile_current
        ld a,(hl)
        bit 0,a                    ; volume envelope enabled?
        ret nz
        xor a                      ; FT2: no volume envelope => volume immediately zero
        ld hl,VOLUME
        call ptr8_cur
        ld (hl),a
        jp emit_volume_current

xm_tick_modulators:
        ; XM engine: envelopes/fade/auto-vibrato apply in both frequency modes.
        call xm_apply_auto_vib
        call xm_apply_volume_env
        jp xm_apply_pan_env

xm_apply_auto_vib:
        call xm_profile_current
        ld a,(hl)
        bit 6,a
        ret z
        ld (EV_PERIOD),hl          ; scratch profile pointer
        ; ramp auto-vibrato amplitude while key is held
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_auto_ramp_held
        ; FT2 auto-vibrato quirk: key-off before the sweep finished resets
        ; the sweep accumulator to one sweep step. Once full depth was
        ; reached it remains there. Clone profiles can disable this quirk.
        ld a,(XMFLAGS)
        bit 5,a
        jr z,xm_auto_amp_ready
        ld hl,AUTOAMP
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)                  ; DE=current Q8 depth
        ld hl,(EV_PERIOD)
        ld bc,5
        add hl,bc
        ld a,(hl)                  ; full depth (integer, high byte)
        cp d
        jr nz,xm_auto_keyoff_reset
        ld a,e
        or a
        jr z,xm_auto_amp_ready     ; exactly fullDepth<<8: sweep completed
xm_auto_keyoff_reset:
        ld hl,(EV_PERIOD)
        ld bc,8
        add hl,bc
        ld e,(hl)
        inc hl
        ld d,(hl)                  ; one precomputed sweep step
        ld hl,AUTOAMP
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
        jr xm_auto_amp_ready
xm_auto_ramp_held:
        ld hl,(EV_PERIOD)
        ld de,8                    ; sweep step Q8
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        jr z,xm_auto_amp_ready
        push de
        ld hl,AUTOAMP
        call ptr16_cur
        ld c,(hl)
        inc hl
        ld b,(hl)
        pop de
        ld h,b
        ld l,c
        add hl,de
        push hl
        ld hl,(EV_PERIOD)
        ld de,5                    ; depth
        add hl,de
        ld a,(hl)
        pop hl
        cp h                       ; cap at depth<<8 (high byte)
        jr nc,xm_auto_amp_store
        ld h,a
        ld l,0
xm_auto_amp_store:
        ex de,hl
        ld hl,AUTOAMP
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
xm_auto_amp_ready:
        ; position advances before waveform evaluation in FT2
        ld hl,(EV_PERIOD)
        ld de,6                    ; rate
        add hl,de
        ld b,(hl)
        ld hl,AUTOPOS
        call ptr8_cur
        ld a,(hl)
        add a,b
        ld (hl),a
        ld c,a                     ; C=position
        ; waveform type
        ld hl,(EV_PERIOD)
        ld de,4
        add hl,de
        ld a,(hl)
        and 3
        cp 1
        jr z,xm_auto_square
        cp 2
        jr z,xm_auto_ramp_up
        cp 3
        jr z,xm_auto_ramp_down
        ld a,c
        ld e,a
        ld d,0
        ld hl,AUTO_VIB_SINE
        add hl,de
        ld a,(hl)
        jr xm_auto_wave_ready
xm_auto_square:
        ld a,c
        cp 128
        ld a,0C0h                  ; -64
        jr c,xm_auto_wave_ready
        ld a,64
        jr xm_auto_wave_ready
xm_auto_ramp_up:
        ld a,c
        srl a
        add a,64
        and 127
        sub 64
        jr xm_auto_wave_ready
xm_auto_ramp_down:
        ld a,c
        srl a
        neg
        add a,64
        and 127
        sub 64
xm_auto_wave_ready:
        or a
        ret z
        ld b,0                     ; sign flag
        jp p,xm_auto_abs
        neg
        ld b,1
xm_auto_abs:
        ; FT2 keeps autoVibAmp in Q8 and calculates
        ; (signedWave * autoVibAmp) >> 14. Preserve the fractional sweep
        ; amplitude instead of truncating it to whole depth units.
        ld c,a                     ; abs waveform 0..64
        ld a,b
        ld (EV_PLO),a              ; sign scratch
        ld hl,AUTOAMP
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)                  ; DE=Q8 amplitude 0..65280
        ld a,d
        or e
        ret z
        ld hl,0                    ; B:HL = 24-bit product
        ld b,0
xm_auto_mul_q8:
        ld a,c
        or a
        jr z,xm_auto_mul_q8_done
        add hl,de
        jr nc,xm_auto_mul_q8_no_carry
        inc b
xm_auto_mul_q8_no_carry:
        dec c
        jr xm_auto_mul_q8
xm_auto_mul_q8_done:
        ld a,14
xm_auto_shift_q8:
        srl b
        rr h
        rr l
        dec a
        jr nz,xm_auto_shift_q8
        ld e,l                    ; result is 0..255
        ld d,0
        ld hl,(OUT_PERIOD)
        ld a,(EV_PLO)
        or a
        jr nz,xm_auto_sub
        add hl,de
        jr xm_auto_period_store
xm_auto_sub:
        or a
        sbc hl,de
        jr nc,xm_auto_period_store
        ld hl,1
xm_auto_period_store:
        ld (OUT_PERIOD),hl
        ld a,e
        or d
        ret z
        ld a,1
        ld (PITCH_DIRTY),a
        ret

; Advance FT2 volume-envelope tick and return curve value 0..64 in A.
xm_vol_env_value:
        call xm_profile_current
        ld (EV_PERIOD),hl
        ld a,(hl)
        bit 0,a
        jr nz,xm_vol_env_on
        ld a,64
        ret
xm_vol_env_on:
        ; DE=current tick
        ld hl,ENVVTICK
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ; sustain holds when key is on and current tick is sustain X
        ld hl,(EV_PERIOD)
        ld a,(hl)
        bit 1,a
        jr z,xm_vol_tick_inc
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr nz,xm_vol_tick_inc
        ld hl,(EV_PERIOD)
        ld bc,14
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld a,d
        cp b
        jr nz,xm_vol_tick_inc
        ld a,e
        cp c
        jr z,xm_vol_tick_after_inc
xm_vol_tick_inc:
        inc de
xm_vol_tick_after_inc:
        ; FT2 envelope escape: after key-off, a loop whose end point is also
        ; the sustain point must not trap the released envelope.
        ld a,(XMFLAGS)
        bit 3,a
        jr z,xm_vol_loop_check
        push de
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_vol_escape_no
        call xm_profile_current
        ld a,(hl)
        bit 1,a
        jr z,xm_vol_escape_no
        ld de,14
        add hl,de
        ld c,(hl)
        inc hl
        ld b,(hl)                 ; BC=sustain tick
        call xm_profile_current
        ld de,18
        add hl,de
        ld a,(hl)
        cp c
        jr nz,xm_vol_escape_no
        inc hl
        ld a,(hl)
        cp b
        jr nz,xm_vol_escape_no
        pop de
        jr xm_vol_no_loop
xm_vol_escape_no:
        pop de
xm_vol_loop_check:
        ; loop end jumps to loop start (FT2's common-case semantics)
        ld hl,(EV_PERIOD)
        ld a,(hl)
        bit 2,a
        jr z,xm_vol_no_loop
        ld hl,(EV_PERIOD)
        ld bc,18
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld a,d
        cp b
        jr nz,xm_vol_no_loop
        ld a,e
        cp c
        jr nz,xm_vol_no_loop
        ld hl,(EV_PERIOD)
        ld bc,16
        add hl,bc
        ld e,(hl)
        inc hl
        ld d,(hl)
xm_vol_no_loop:
        ; clamp to max curve tick
        ld hl,(EV_PERIOD)
        ld bc,12
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld h,d
        ld l,e
        or a
        sbc hl,bc
        jr c,xm_vol_tick_ok
        jr z,xm_vol_tick_ok
        ld d,b
        ld e,c
xm_vol_tick_ok:
        push de
        ld hl,ENVVTICK
        call ptr16_cur
        pop de
        ld (hl),e
        inc hl
        ld (hl),d
        ; curve base + tick
        ld hl,(EV_PERIOD)
        ld bc,10
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld h,b
        ld l,c
        add hl,de
        ld a,(hl)
        ret

xm_apply_volume_env:
        call xm_profile_current
        ld a,(hl)
        ld b,a                     ; flags
        ; fadeout on key-off, independent from envelope value
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_vol_fade_done
        call xm_profile_current
        inc hl
        inc hl                     ; +2 fadeout speed
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        jr z,xm_vol_fade_done
        push de
        ld hl,FADEVOL
        call ptr16_cur
        ld c,(hl)
        inc hl
        ld b,(hl)
        pop de
        ld h,b
        ld l,c
        or a
        sbc hl,de
        jr nc,xm_vol_fade_store
        ld hl,0
xm_vol_fade_store:
        ex de,hl
        ld hl,FADEVOL
        call ptr16_cur
        ld (hl),e
        inc hl
        ld (hl),d
xm_vol_fade_done:
        call xm_vol_env_value
        ld c,a                     ; C=envelope 0..64
        ld hl,VOLUME
        call ptr8_cur
        ld a,(hl)                  ; base volume
        ld b,a
        ; Apply transient 7xy tremolo without modifying VOLUME memory.
        ld hl,TREMOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_vol_no_trem
        jp p,xm_vol_trem_add
        neg
        ld c,a
        ld a,b
        cp c
        jr nc,xm_vol_trem_sub_ok
        xor a
        jr xm_vol_trem_store
xm_vol_trem_sub_ok:
        sub c
        jr xm_vol_trem_store
xm_vol_trem_add:
        ld c,a
        ld a,b
        add a,c
        cp 65
        jr c,xm_vol_trem_store
        ld a,64
xm_vol_trem_store:
        ld b,a
xm_vol_no_trem:
        ; FT2 tremor off-phase mutes the mixed output, not channel volume state.
        ld hl,TREMORCNT
        call ptr8_cur
        ld a,(hl)
        and 0E0h
        cp 080h                  ; FT2 OFF phase is exactly 10xxxxx
        jr nz,xm_vol_tremor_on
        ld b,0
xm_vol_tremor_on:
        ; base*env /64
        ld e,c
        ld d,0
        ld hl,0
xm_vol_mul1:
        ld a,b
        or a
        jr z,xm_vol_mul1_done
        add hl,de
        dec b
        jr xm_vol_mul1
xm_vol_mul1_done:
        ld de,32                   ; rounded /64
        add hl,de
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
        ld b,l                     ; effective before fade 0..64
        ; multiply by fade high byte /128 (full fade high=128)
        ld hl,FADEVOL
        call ptr16_cur
        inc hl
        ld e,(hl)
        ld d,0
        ld hl,0
xm_vol_mul2:
        ld a,b
        or a
        jr z,xm_vol_mul2_done
        add hl,de
        dec b
        jr xm_vol_mul2
xm_vol_mul2_done:
        ld de,64                   ; rounded /128
        add hl,de
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
        srl h
        rr l
        ld a,l
        cp 65
        jr c,xm_vol_final_ok
        ld a,64
xm_vol_final_ok:
        ; XM Gxx/Hxy global volume, 0..64.
        ld b,a
        ld a,(GLOBALVOL)
        ld e,a
        ld d,0
        ld hl,0
xm_gv_mul:
        ld a,b
        or a
        jr z,xm_gv_mul_done
        add hl,de
        dec b
        jr xm_gv_mul
xm_gv_mul_done:
        ld de,32
        add hl,de
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
        ld a,l
        cp 65
        jr c,xm_gv_ok
        ld a,64
xm_gv_ok:
        ld e,a
        ld d,0
        ld hl,VOL_LUT
        add hl,de
        ld e,(hl)
        ld a,(CUR_CH)
        add a,050h
        ld d,a
        jp opl4_write_de

xm_pan_env_value:
        call xm_profile_current
        ld (EV_PERIOD),hl
        ld a,(hl)
        bit 3,a
        jr nz,xm_pan_env_on
        ld a,32                    ; neutral envelope center
        ret
xm_pan_env_on:
        ld hl,ENVPTICK
        call ptr16_cur
        ld e,(hl)
        inc hl
        ld d,(hl)
        ; FT2 panning envelope quirk: if sustain was reached while the key
        ; was still held, the panning envelope stays there even after key-off.
        ld a,(XMFLAGS)
        bit 4,a
        jr z,xm_pan_stop_checked
        push de
        ld hl,PANENVSTOP
        call ptr8_cur
        ld a,(hl)
        pop de
        or a
        jp nz,xm_pan_no_loop
xm_pan_stop_checked:
        ld hl,(EV_PERIOD)
        ld a,(hl)
        bit 4,a
        jr z,xm_pan_tick_inc
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr nz,xm_pan_tick_inc
        ld hl,(EV_PERIOD)
        ld bc,24
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld a,d
        cp b
        jr nz,xm_pan_tick_inc
        ld a,e
        cp c
        jr nz,xm_pan_tick_inc
        ld a,(XMFLAGS)
        bit 4,a
        jr z,xm_pan_tick_after_inc
        push de
        ld hl,PANENVSTOP
        call ptr8_cur
        ld (hl),1
        pop de
        jr xm_pan_no_loop
xm_pan_tick_inc:
        inc de
xm_pan_tick_after_inc:
        ; Same FT2 loop/sustain escape rule applies to the panning envelope.
        ld a,(XMFLAGS)
        bit 3,a
        jr z,xm_pan_loop_check
        push de
        ld hl,XMKEYOFF
        call ptr8_cur
        ld a,(hl)
        or a
        jr z,xm_pan_escape_no
        call xm_profile_current
        ld a,(hl)
        bit 4,a
        jr z,xm_pan_escape_no
        ld de,24
        add hl,de
        ld c,(hl)
        inc hl
        ld b,(hl)                 ; BC=pan sustain tick
        call xm_profile_current
        ld de,28
        add hl,de
        ld a,(hl)
        cp c
        jr nz,xm_pan_escape_no
        inc hl
        ld a,(hl)
        cp b
        jr nz,xm_pan_escape_no
        pop de
        jr xm_pan_no_loop
xm_pan_escape_no:
        pop de
xm_pan_loop_check:
        ld hl,(EV_PERIOD)
        ld a,(hl)
        bit 5,a
        jr z,xm_pan_no_loop
        ld hl,(EV_PERIOD)
        ld bc,28
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld a,d
        cp b
        jr nz,xm_pan_no_loop
        ld a,e
        cp c
        jr nz,xm_pan_no_loop
        ld hl,(EV_PERIOD)
        ld bc,26
        add hl,bc
        ld e,(hl)
        inc hl
        ld d,(hl)
xm_pan_no_loop:
        ld hl,(EV_PERIOD)
        ld bc,22
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld h,d
        ld l,e
        or a
        sbc hl,bc
        jr c,xm_pan_tick_ok
        jr z,xm_pan_tick_ok
        ld d,b
        ld e,c
xm_pan_tick_ok:
        push de
        ld hl,ENVPTICK
        call ptr16_cur
        pop de
        ld (hl),e
        inc hl
        ld (hl),d
        ld hl,(EV_PERIOD)
        ld bc,20
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld h,b
        ld l,c
        add hl,de
        ld a,(hl)
        ret

xm_apply_pan_env:
        call xm_profile_current
        ld a,(hl)
        bit 3,a
        ret z
        call xm_pan_env_value
        sub 32
        ret z
        ld b,0                     ; sign
        jp p,xm_pan_diff_abs
        neg
        ld b,1
xm_pan_diff_abs:
        ld c,a                     ; abs env delta 0..32
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        ld e,a                     ; base pan
        cp 128
        jr nc,xm_pan_range_right
        ld a,128
        sub e
        jr xm_pan_range_abs
xm_pan_range_right:
        sub 128
xm_pan_range_abs:
        ld d,a                     ; distance from center
        ld a,128
        sub d
        ld d,0
        ld e,a                     ; range
        ld hl,0
xm_pan_mul:
        ld a,c
        or a
        jr z,xm_pan_mul_done
        add hl,de
        dec c
        jr xm_pan_mul
xm_pan_mul_done:
        ; /32
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
        ld c,l                     ; pan add magnitude
        ld hl,XMPAN
        call ptr8_cur
        ld a,(hl)
        ld e,a
        ld a,b
        or a
        jr nz,xm_pan_sub
        ld a,e
        add a,c
        jr nc,xm_pan_emit
        ld a,255
        jr xm_pan_emit
xm_pan_sub:
        ld a,e
        cp c
        jr nc,xm_pan_sub_ok
        xor a
        jr xm_pan_emit
xm_pan_sub_ok:
        sub c
xm_pan_emit:
        jp emit_pan_tracker_a

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

set_pan_from_tracker:
        ; Preserve exact FT2 pan for panning envelopes, then quantize to OPL4.
        push af
        ld hl,XMPAN
        call ptr8_cur
        pop af
        ld (hl),a
emit_pan_tracker_a:
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
        ld a,(LINEAR_XM)
        or a
        jp nz,emit_pitch_linear
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
        ld e,0FCh
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
        ld bc,28               ; FAST_VOL..PREV_PFX[23]
        call state_write_block
        ld hl,XMPROF
        ld bc,06000h-XMPROF    ; XM profile/pan/keyoff/env ticks/vibrato ctrl
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
        ld hl,FADEVOL
        ld bc,STATE_CLEAR_END-FADEVOL
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
        ld bc,28               ; FAST_VOL..PREV_PFX[23]
        call state_read_block
        ld hl,XMPROF
        ld bc,06000h-XMPROF
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
        ld hl,FADEVOL
        ld bc,STATE_CLEAR_END-FADEVOL
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

; 65-byte volume -> OPL4 TL register table. The converter patches this per song/global volume.
VOL_LUT:
        defs 65,0

FT2_VIB_TAB:
        db 0,24,49,74,97,120,141,161,180,197,212,224,235,244,250,253
        db 255,253,250,244,235,224,212,197,180,161,141,120,97,74,49,24

PITCH_LUT:
        dw 0
PITCH_LUT_END:

; XM linear-frequency mode. OUT_PERIOD is FT2's native linear period, not the
; quarter-sized inverse-frequency period used by S3M/MOD. FT2 uses
;   freq = 8363 * 2^((4608-period)/768)
; and OPL4 pitch is octave + a 10-bit linear F-number inside each octave.
; 2766 is 4608 + 768*log2(8363/44100), rounded to the nearest integer; the
; resulting constant tuning error is only ~0.43 cent. A 97-word table at 8
; linear-period-unit spacing plus interpolation keeps the conversion error well
; below a cent while using under 200 bytes of ROM.
emit_pitch_linear:
        ; signed log2-ratio numerator Q = 2766 - period
        ld hl,2766
        ld de,(OUT_PERIOD)
        or a
        sbc hl,de
        ld a,1                    ; OPL4 octave = floor(Q/768)+1
linear_norm_negative:
        bit 7,h
        jr z,linear_norm_positive
        ld de,768
        add hl,de
        dec a
        jr linear_norm_negative
linear_norm_positive:
        ld de,768
linear_norm_high:
        or a
        sbc hl,de
        jr c,linear_norm_done
        inc a
        jr linear_norm_high
linear_norm_done:
        add hl,de                 ; restore final 0..767 remainder
        ld (EV_PHI),a             ; temporary signed OPL4 octave

        ; index = remainder >> 3, frac = remainder & 7
        ld a,l
        and 7
        ld (EV_PLO),a
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        add hl,hl
        ld de,LINEAR_FNUM_LUT
        add hl,de
        ld c,(hl)                 ; BC = y0
        inc hl
        ld b,(hl)
        inc hl
        ld e,(hl)                 ; DE = y1
        inc hl
        ld d,(hl)
        push bc
        ex de,hl                  ; HL = y1
        or a
        sbc hl,bc                 ; HL = delta (small positive value)
        ld e,l
        ld d,0
        ld a,(EV_PLO)             ; multiply delta by frac (0..7)
        ld hl,0
linear_interp_mul:
        or a
        jr z,linear_interp_done
        add hl,de
        dec a
        jr linear_interp_mul
linear_interp_done:
        ld de,4                   ; rounded /8
        add hl,de
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        pop bc
        add hl,bc                 ; HL = interpolated fnum 0..1023

        ; reg 20h+n: FNUM bits 0..6 in bits 1..7, custom-wave high bit=1.
        ld a,l
        and 07Fh
        add a,a
        or 1
        ld e,a
        ld a,(CUR_CH)
        add a,020h
        ld d,a
        push hl
        call opl4_write_de
        pop hl

        ; reg 38h+n: signed octave nibble + FNUM bits 7..9.
        ld a,h
        and 3
        add a,a
        ld b,a
        ld a,l
        rlca
        and 1
        or b
        ld b,a
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


; 97 entries cover linear remainder 0,8,...,768.
LINEAR_FNUM_LUT:
        dw 0,7,15,22,30,38,45,53
        dw 61,69,77,85,93,101,109,117
        dw 125,134,142,151,159,168,176,185
        dw 194,203,211,220,229,239,248,257
        dw 266,276,285,294,304,314,323,333
        dw 343,353,363,373,383,393,403,414
        dw 424,435,445,456,467,477,488,499
        dw 510,521,533,544,555,567,578,590
        dw 601,613,625,637,649,661,673,686
        dw 698,711,723,736,749,761,774,787
        dw 801,814,827,841,854,868,881,895
        dw 909,923,937,951,966,980,995,1009
        dw 1024
LINEAR_FNUM_LUT_END:







AUTO_VIB_SINE:
        db 0,-2,-3,-5,-6,-8,-9,-11,-12,-14,-16,-17,-19,-20,-22,-23
        db -24,-26,-27,-29,-30,-32,-33,-34,-36,-37,-38,-39,-41,-42,-43,-44
        db -45,-46,-47,-48,-49,-50,-51,-52,-53,-54,-55,-56,-56,-57,-58,-59
        db -59,-60,-60,-61,-61,-62,-62,-62,-63,-63,-63,-64,-64,-64,-64,-64
        db -64,-64,-64,-64,-64,-64,-63,-63,-63,-62,-62,-62,-61,-61,-60,-60
        db -59,-59,-58,-57,-56,-56,-55,-54,-53,-52,-51,-50,-49,-48,-47,-46
        db -45,-44,-43,-42,-41,-39,-38,-37,-36,-34,-33,-32,-30,-29,-27,-26
        db -24,-23,-22,-20,-19,-17,-16,-14,-12,-11,-9,-8,-6,-5,-3,-2
        db 0,2,3,5,6,8,9,11,12,14,16,17,19,20,22,23
        db 24,26,27,29,30,32,33,34,36,37,38,39,41,42,43,44
        db 45,46,47,48,49,50,51,52,53,54,55,56,56,57,58,59
        db 59,60,60,61,61,62,62,62,63,63,63,64,64,64,64,64
        db 64,64,64,64,64,64,63,63,63,62,62,62,61,61,60,60
        db 59,59,58,57,56,56,55,54,53,52,51,50,49,48,47,46
        db 45,44,43,42,41,39,38,37,36,34,33,32,30,29,27,26
        db 24,23,22,20,19,17,16,14,12,11,9,8,6,5,3,2

XM_TONE_PROFILE:
        db 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        db 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        db 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        db 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
XM_PROFILE_PTRS:
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
        dw 0,0,0,0,0,0,0,0
XM_PROFILE_DATA:
        org 05F00h
XM_PROFILE_LIMIT:
