; Resident player state, FCB and scratch buffers.

file_open:
	db 0
file_fcb:
	ds 37,0
fcb_request_count:
	dw 0
scc_slot:
	db 2
scc_slot_b:
	db 1
cmd_remaining:
	db 0
selected_track:
	dw 0
current_page:
	dw 0
current_song_id:
	dw 0
space_previous:
	db 1
mapper_ready:
	db 0
engine_ready:
	db 0
engine_running:
	db 0
decode_stage:
	db 0
hybrid_ready:
	db 0
file_cache_ready:
	db 0
template_cache_ready:
	db 0
template_segment_allocated:
	db 0
template_segment:
	db 0
dynamic_profile:
	db 0
page2_runtime_profile:
	db 0
page3_workram_profile:
	db 0
engine_p2_segment_allocated:
	db 0
engine_p2_segment:
	db 0
engine_p3_segment_allocated:
	db 0
engine_p3_segment:
	db 0
dynamic_page:
	dw 0
dynamic_result:
	db 0
dynamic_saved_p3:
	db 0
dynamic_install_active:
	db 0
gateway_patch_flags:
	db 0
hardware_error_code:
	db 0
stream_source:
	db 0
stream_vdp_guard:
	db 0
vdp_saved_iff:
	db 0
refresh_saved:
	db 0
original_vdp_r9:
	db 0
template_compression:
	db 0
mapper_segment_mask:
	db 0
mapper_pool_count:
	db 0
mapper_pool:
	ds 12,0
probe_original_p1:
	db 0
probe_base_byte:
	db 0
probe_marker:
	db 0
original_p0:
	db 0
original_p1:
	db 0
original_p2:
	db 0
original_p3:
	db 0
original_a8:
	db 0
mapped_p1:
	db 0
mapped_p2:
	db 0
saved_map_p1:
	db 0
saved_map_p2:
	db 0
hot_segments:
	ds 3,0
hot_segment_count:
	db 0
hot_needed_count:
	db 0
hot_write_mapped:
	db 0ffh
hot_read_mapped:
	db 0ffh
hpol_map_segment:
	db 0
hpol_map_allocated:
	db 0
menu_launch:
	db 0
ui_error_code:
	db 0
tmp_offset_lo:
	dw 0
mul_multiplicand:
	ds 3,0
mul_multiplier:
	dw 0
mul_result:
	ds 3,0
tmp_offset_hi:
	db 0
file_cache_size:
	ds 3,0
cache_remaining:
	ds 3,0
cache_written:
	ds 3,0
cache_chunk:
	dw 0
resource_count:
	dw 0
resource_index:
	dw 0
resource_cursor_lo:
	dw 0
resource_cursor_hi:
	db 0
hpol_offset_lo:
	dw 0
hpol_offset_hi:
	db 0
hpol_size_lo:
	dw 0
hpol_size_hi:
	db 0
abs_offset_lo:
	dw 0
abs_offset_hi:
	db 0
hpl_block_size:
	dw 0
hpl_block_shift:
	db 0
hpl_position_count:
	dw 0
hpl_hot_count:
	dw 0
hpl_warm_count:
	dw 0
hpl_cold_count:
	dw 0
hpl_slab_count:
	dw 0
hpl_positions_off:
	ds 3,0
hpl_maps_off:
	ds 3,0
hpl_maps_packed:
	ds 3,0
hpl_maps_raw:
	ds 3,0
hpl_hot_off:
	ds 3,0
hpl_hot_packed:
	ds 3,0
hpl_hot_raw:
	ds 3,0
hpl_warm_off:
	ds 3,0
hpl_warm_packed:
	ds 3,0
hpl_warm_raw:
	ds 3,0
hpl_cold_table_off:
	ds 3,0
cold_cached_slab:
	dw 0ffffh
cold_div_shift:
	db 0
current_map_ptr:
	dw 0
current_pos_ptr:
	dw 0
overlay_ptr:
	dw 0
overlay_remaining:
	dw 0
overlay_previous_end:
	dw 0
overlay_offset:
	dw 0
overlay_length:
	dw 0
overlay_end:
	dw 0
stream_offset_lo:
	dw 0
stream_offset_hi:
	db 0
stream_remaining:
	ds 3,0
input_ptr:
	dw 0
input_count:
	dw 0
refill_count:
	dw 0
zx_mode:
	db 0
zx_bit_value:
	db 0
zx_bit_mask:
	db 0
zx_last_byte:
	db 0
zx_backtrack:
	db 0
gamma_invert:
	db 0
zx_last_offset:
	dw 1
zx_output_pos:
	ds 3,0
zx_remaining:
	ds 3,0
linear_base:
	dw 0
history_pos_lo:
	dw 0
history_pos_hi:
	db 0
decimal_buffer:
	ds 7,0
filename:
	ds 16,0
ui_logo_rows:
	db 0
ui_logo_chunks:
	db 0
ui_logo_vram_addr:
	dw 0
; ---------------------------------------------------------------------------
; User-visible startup/error strings and runtime filenames
; ---------------------------------------------------------------------------
msg_err_ksp_format:
	db "ERR KSP FORMAT",13,10
msg_err_profile:
	db "ERR PROFILE",13,10
msg_err_mapper128k:
	db "ERR 128K MAPPER",13,10
msg_err_memory:
	db "ERR MEMORY",13,10
msg_err_file:
	db "ERR FILE",13,10
msg_err_track:
	db "ERR TRACK",13,10
msg_err_decode:
	db "ERR DECODE",13,10,13,10
msg_version_0470:
	db "KSP1PLAY 0.47.0",13,10
kspmenu_filename:
	db "KSPMENU.BIN",0
msg_err_opl4:
	db "ERR OPL4",13,10
msg_err_scc_slots:
	db "ERR SCC SLOTS",13,10
logo_filename:
	db "LOGO.S5",0
