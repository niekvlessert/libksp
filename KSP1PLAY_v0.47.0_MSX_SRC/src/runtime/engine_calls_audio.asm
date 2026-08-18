; engine calls audio.asm - KSP1PLAY v0.47.0

next_track:
	di
	; Fixed handoff spacing before mapper/interrupt restoration.
	nop
	nop
	nop
	call restore_process_pages
	call save_interrupt_hook
	call ui_load_hvar_overlay
	ret c
	ld hl,(scc_slot_b+2)
	call KSPMENU_ENTRY_UPDATE_ROW
	ret c
	ld (scc_slot_b+2),hl
	jp ui_install_selected_track

; Stop the active engine through its declared call profile, then let the caller
; restore player-owned mapper/slot/audio state.
; stop_engine
; Stops the active engine through the declared KSPOS or compatibility call path.
; Returns with interrupts disabled, matching the playback transition contract.
stop_engine:
	ld a,(engine_running)
	or a
	ret z
	xor a
	ld (engine_running),a
	ld hl,(engine_stop_address)
	ld a,h
	or l
	ret z
	ld (stop_call+1),hl
	ld a,(KSPOS_FLAGS)
	and 040h
	jp z,stop_call_compatibility
	call KSPOS_CALL_STOP
	di
	ret
stop_call_compatibility:
	ld a,(page3_workram_profile)
	or a
	jp z,stop_call
	ld a,(engine_p3_segment)
	out (PORT_MAPPER_P3),a
stop_call:
	call ENGINE_DIRECT_CALL_PATCH
	di
	ld a,(page3_workram_profile)
	or a
	ret z
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ret
stop_and_mute:
	call stop_engine
	call hard_mute_audio
	ret
prepare_engine_page2:
	ld a,(page2_runtime_profile)
	or a
	jp z,prepare_engine_page2_hardware
	jp RECON_ENTRY_PREPARE_PAGE2
prepare_engine_page2_hardware:
	ld a,(engine_required_hardware)
	and 008h
	jp nz,map_ram_page2
	ld a,(engine_required_hardware)
	and 006h
	ret z
	call map_scc_page2
	ld a,(engine_required_hardware)
	and 00eh
	cp 002h
	ret nz
	ld a,03fh
	ld (SCC_ENABLE_REG),a
	ret
hard_mute_audio:
	push af
	push bc
	push de
	push hl
	ld d,000h
	ld b,007h
hard_reset_psg_0_6:
	ld a,d
	out (PORT_PSG_ADDR),a
	xor a
	out (PORT_PSG_DATA),a
	inc d
	djnz hard_reset_psg_0_6
	ld a,007h
	out (PORT_PSG_ADDR),a
	ld a,0bfh
	out (PORT_PSG_DATA),a
	ld d,008h
	ld b,006h
hard_reset_psg_8_13:
	ld a,d
	out (PORT_PSG_ADDR),a
	xor a
	out (PORT_PSG_DATA),a
	inc d
	djnz hard_reset_psg_8_13
	ld a,(space_previous+2)
	or a
	jp z,hard_mute_done
	ld a,(engine_required_hardware)
	and 010h
	call nz,hard_reset_ym2413
	ld a,(engine_required_hardware)
	and 040h
	call nz,hard_reset_opl4
	ld a,(engine_required_hardware)
	and 008h
	jp z,hard_reset_single_scc
	call dual_scc_select_a
	call hard_reset_normal_scc_selected
	call dual_scc_select_b
	call hard_reset_normal_scc_selected
	call map_ram_page2
	jp hard_mute_done
hard_reset_single_scc:
	ld a,(engine_required_hardware)
	and 006h
	jp z,hard_mute_done
	call map_scc_page2
	ld a,(engine_required_hardware)
	and 004h
	jp nz,hard_reset_sccplus_selected
	call hard_reset_normal_scc_selected
	jp hard_mute_done
hard_reset_normal_scc_selected:
	ld a,03fh
	ld (SCC_ENABLE_REG),a
	xor a
	ld hl,SCC_WAVE_BASE
	ld b,090h
hard_reset_normal_scc_loop:
	ld (hl),a
	inc hl
	djnz hard_reset_normal_scc_loop
	ret
hard_reset_sccplus_selected:
	ld a,020h
	ld (SCCPLUS_MODE_REG+1),a
	ld a,080h
	ld (SCCPLUS_BANK_REG),a
	xor a
	ld hl,SCCPLUS_WAVE_BASE
	ld b,000h
hard_reset_sccplus_loop:
	ld (hl),a
	inc hl
	djnz hard_reset_sccplus_loop
	jp hard_mute_done
mute_fmpac_before_disk_io:
	push af
	push bc
	push de
	ld a,(engine_running)
	or a
	jp z,mute_fmpac_disk_done
	ld a,(space_previous+2)
	or a
	jp z,mute_fmpac_disk_done
	ld a,(engine_required_hardware)
	and 010h
	jp z,mute_fmpac_disk_done
	ld d,00eh
	xor a
	call write_ym2413_register
	ld d,020h
	ld b,009h
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
	ld e,a
	ld a,d
	out (PORT_FM_ADDR),a
	; YM2413 address-to-data port delay.
	nop
	nop
	ld a,e
	out (PORT_FM_DATA),a
	push bc
	ld b,020h
write_ym2413_wait:
	djnz write_ym2413_wait
	pop bc
	ret
hard_reset_ym2413:
	ld d,000h
hard_reset_ym2413_loop:
	xor a
	call write_ym2413_register
	inc d
	ld a,d
	cp 039h
	jp c,hard_reset_ym2413_loop
	ret
hard_mute_done:
	pop hl
	pop de
	pop bc
	pop af
	ret

; Invoke the selected engine INIT entry with the KSP ABI context installed.
; Compatibility profiles use the alternate register/context path below.
; call_init
; Calls the selected engine INIT entry with the current song id and ABI context.
; Returns with interrupts disabled.
call_init:
	ld hl,(engine_init_address)
	ld (ENGINE_INIT_CALL_OPERAND),hl
	ld a,(KSPOS_FLAGS)
	and 040h
	jp z,call_init_compatibility
	ld hl,(current_song_id)
	ld a,l
	ld bc,ENGINE_DIRECT_CALL_PATCH
	ld de,ENGINE_DIRECT_CALL_PATCH
	call KSPOS_CALL_INIT
	di
	ret
call_init_compatibility:
	ld a,(page3_workram_profile)
	or a
	jp z,call_init_compatibility_parameters
	ld a,(engine_p3_segment)
	out (PORT_MAPPER_P3),a
call_init_compatibility_parameters:
	ld hl,(current_song_id)
	ld a,l
	ld bc,ENGINE_DIRECT_CALL_PATCH
	ld de,ENGINE_DIRECT_CALL_PATCH
	call ENGINE_DIRECT_CALL_PATCH
	di
	ld a,(page3_workram_profile)
	or a
	ret z
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ret

; Invoke one engine PLAY tick. Keep this path bounded: no FAT/BDOS work belongs
; in the playback hot path.
; call_play
; Playback hot path: invokes one engine PLAY tick.
; Invariant: no FAT/BDOS/disk access may be introduced here.
call_play:
	ld hl,(engine_play_address)
	ld (play_call+1),hl
	ld a,(KSPOS_FLAGS)
	and 040h
	jp z,call_play_compatibility
	call KSPOS_CALL_PLAY
	di
	ret
call_play_compatibility:
	ld a,(page3_workram_profile)
	or a
	jp z,play_call
	ld a,(engine_p3_segment)
	out (PORT_MAPPER_P3),a
play_call:
	call ENGINE_DIRECT_CALL_PATCH
	di
	ld a,(page3_workram_profile)
	or a
	ret z
	ld a,(original_p3)
	out (PORT_MAPPER_P3),a
	ret
read_controls:
	in a,(PORT_KEY_ROW)
	ld d,a
	and 0f0h
	or 007h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	ld e,a
	ld a,d
	out (PORT_KEY_ROW),a
	ld a,e
	bit 2,a
	jp z,control_escape
	in a,(PORT_KEY_ROW)
	ld d,a
	and 0f0h
	or 008h
	out (PORT_KEY_ROW),a
	in a,(PORT_KEY_IN)
	ld e,a
	ld a,d
	out (PORT_KEY_ROW),a
	ld a,e
	and 001h
	ld b,a
	ld a,(space_previous)
	ld c,a
	ld a,b
	ld (space_previous),a
	or a
	jp nz,control_none
	ld a,c
	or a
	jp z,control_none
	ld a,002h
	ret
control_escape:
	ld a,001h
	ret
control_none:
	xor a
	ret
