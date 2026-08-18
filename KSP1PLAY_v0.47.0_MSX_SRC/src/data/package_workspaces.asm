; Fixed KSP descriptors, page/resource records and shared package workspaces.
;
; These labels describe data layouts used by package parsing and track install.
; Keep sizes synchronized with src/include/ksp_format.inc.

ksp_header:
	db 0
	db 0
	db 0
	db 0
ksp_header_size:
	db 0
	db 0
ksp_version_minor:
	db 0
	db 0
	db 0
	db 0
	db 0
	db 0
ksp_file_size_lo:
	db 0
	db 0
ksp_file_size_hi:
	db 0
ksp_file_size_top:
	db 0
ksp_engine_table_offset_lo:
	db 0
	db 0
ksp_engine_table_offset_hi:
	db 0
	db 0
ksp_engine_count:
	db 0
	db 0
ksp_engine_entry_size:
	db 0
	db 0
ksp_page_table_offset_lo:
	db 0
	db 0
ksp_page_table_offset_hi:
	db 0
	db 0
ksp_page_count:
	db 0
	db 0
ksp_page_entry_size:
	db 0
	db 0
ksp_track_table_offset_lo:
	db 0
	db 0
ksp_track_table_offset_hi:
	db 0
	db 0
ksp_track_count:
	db 0
	db 0
ksp_track_entry_size:
	db 0
	db 0
ksp_resource_table_offset_lo:
	db 0
	db 0
ksp_resource_table_offset_hi:
	db 0
	db 0
ksp_resource_count:
	db 0
	db 0
ksp_resource_entry_size:
	db 0
	db 0
ksp_string_table_offset_lo:
	db 0
	db 0
ksp_string_table_offset_hi:
	db 0
	db 0
	db 0
	db 0
	db 0
	db 0
ksp_default_track:
	db 0
	db 0
ksp_meta_resource_index:
	db 0
	db 0
	db 0
	db 0
ksp_logo_resource_index:
	ds 9,0		; 1cbe-1cc6 zero-filled reserved/data bytes
ksp_header_reserved_tail:
	ds 57,0		; 1cc7-1cff zero-filled reserved/data bytes
engine_entry:
	db 0
	db 0
engine_flags_hi:
	db 0
	db 0
engine_required_hardware:
	db 0
engine_required_hardware_byte1:
	db 0
engine_required_hardware_hi:
	db 0
	db 0
engine_abi_version:
	db 0
	db 0
engine_play_frequency:
	db 0
	db 0
engine_page_load_address:
	db 0
	db 0
engine_page_size:
	db 0
	db 0
engine_init_address:
	db 0
	db 0
engine_play_address:
	db 0
	db 0
engine_stop_address:
	db 0
	db 0
engine_dynamic_gateway:
	db 0
	db 0
engine_replace_start:
	db 0
	db 0
engine_first_page:
	db 0
	db 0
engine_page_count:
	db 0
	db 0
engine_default_mwk_resource:
	db 0
	db 0
engine_template_compression:
	db 0
	db 0
engine_bank_count:
	db 0
engine_bank_width:
	db 0
engine_template_offset_lo:
	db 0
	db 0
engine_template_offset_hi:
	db 0
engine_template_offset_top:
	db 0
engine_template_packed_size_lo:
	db 0
	db 0
engine_template_packed_size_hi:
	db 0
	db 0
engine_template_unpacked_size_lo:
	db 0
	db 0
engine_template_unpacked_size_hi:
	ds 10,0		; 1d2e-1d37 zero-filled reserved/data bytes
engine_direct_state_start:
	db 0
	db 0
engine_direct_state_end:
	db 0
	db 0
	db 0
	db 0
	db 0
	db 0
track_entry:
	db 0
	db 0
track_song_id:
	db 0
	db 0
track_flags:
	db 0
track_flags_hi:
	db 0
track_mwk_resource:
	ds 10,0		; 1d46-1d4f zero-filled reserved/data bytes
track_duration_ms_lo:
	db 0
	db 0
track_duration_ms_hi:
	db 0
track_duration_ms_top:
	ds 13,0		; 1d53-1d5f zero-filled reserved/data bytes
page_entry:
	db 0
	db 0
page_encoding:
	db 0
page_payload_compression:
	db 0
page_flags:
	db 0
page_flags_hi:
	db 0
page_reserved:
	db 0
	db 0
page_payload_offset_lo:
	db 0
	db 0
page_payload_offset_hi:
	db 0
page_payload_offset_top:
	db 0
page_packed_size_lo:
	db 0
	db 0
page_packed_size_hi:
	db 0
	db 0
page_unpacked_size_lo:
	db 0
	db 0
page_unpacked_size_hi:
	ds 14,0		; 1d72-1d7f zero-filled reserved/data bytes
resource_entry:
	db 0
	db 0
resource_fourcc_hi:
	db 0
	db 0
resource_flags:
	db 0
resource_flags_hi:
	db 0
resource_compression:
	db 0
resource_reserved:
	db 0
resource_payload_offset_lo:
	db 0
	db 0
resource_payload_offset_hi:
	db 0
resource_payload_offset_top:
	db 0
resource_packed_size_lo:
	db 0
	db 0
resource_packed_size_hi:
	db 0
resource_packed_size_top:
	db 0
resource_unpacked_size_lo:
	db 0
	db 0
resource_unpacked_size_hi:
	db 0
resource_unpacked_size_top:
	db 0
	db 0
	db 0
	db 0
	db 0
resource_aux0_lo:
	ds 8,0		; 1d98-1d9f zero-filled reserved/data bytes
hpl_header:
	db 0
	db 0
	db 0
	db 0
hpl_header_size:
	db 0
	db 0
hpl_version:
	db 0
	db 0
hpl_header_block_size:
	db 0
	db 0
hpl_header_position_count:
	db 0
	db 0
hpl_page_count:
	db 0
hpl_page_count_hi:
	db 0
hpl_hot_block_count:
	db 0
	db 0
hpl_warm_block_count:
	db 0
	db 0
hpl_cold_block_count:
	db 0
	db 0
hpl_cold_slab_count:
	db 0
	db 0
hpl_flags:
	db 0
	db 0
hpl_position_table_offset_lo:
	db 0
	db 0
hpl_position_table_offset_hi:
	db 0
	db 0
hpl_map_stream_offset_lo:
	db 0
	db 0
hpl_map_stream_offset_hi:
	db 0
	db 0
hpl_map_packed_size_lo:
	db 0
	db 0
hpl_map_packed_size_hi:
	db 0
	db 0
hpl_map_raw_size_lo:
	db 0
	db 0
hpl_map_raw_size_hi:
	db 0
	db 0
hpl_hot_stream_offset_lo:
	db 0
	db 0
hpl_hot_stream_offset_hi:
	db 0
	db 0
hpl_hot_packed_size_lo:
	db 0
	db 0
hpl_hot_packed_size_hi:
	db 0
	db 0
hpl_hot_raw_size_lo:
	db 0
	db 0
hpl_hot_raw_size_hi:
	db 0
	db 0
hpl_warm_stream_offset_lo:
	db 0
	db 0
hpl_warm_stream_offset_hi:
	db 0
	db 0
hpl_warm_packed_size_lo:
	db 0
	db 0
hpl_warm_packed_size_hi:
	db 0
	db 0
hpl_warm_raw_size_lo:
	db 0
	db 0
hpl_warm_raw_size_hi:
	db 0
	db 0
hpl_cold_slab_table_offset_lo:
	db 0
	db 0
hpl_cold_slab_table_offset_hi:
	ds 12,0		; 1de2-1ded zero-filled reserved/data bytes
hpl_cold_raw_size_hi:
	db 0
hpl_cold_raw_size_top:
	ds 17,0		; 1def-1dff zero-filled reserved/data bytes
; 512-byte shared scratch/I/O workspace. Record fields above are used
; transiently by FCB, META, KZB/MWK and page-materialization code.
io_buffer:
	ds 00200h,0		;1e00-1fff
