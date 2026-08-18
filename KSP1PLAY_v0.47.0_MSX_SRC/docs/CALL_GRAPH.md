# Call graph

Generated from direct named `CALL` instructions plus a curated view of the main runtime flows.

## Primary flow

```text
start
  -> init_application_defaults
  -> get_mapper_api
  -> capture_original_pages
  -> kspos_detect_and_prepare
  -> ui_application
       -> ui_menu / ui_load_pack
       -> ui_install_selected_track
       -> ui_play_screen
            -> wait_vblank_without_keyclick
            -> call_play
            -> playback action dispatch
```

## Track installation

```text
ui_install_selected_track
  -> select_track
  -> ui_prepare_selected_engine
  -> install_current_track
       -> page-materialization ABI as required
       -> patch_engine_gateways
       -> prepare_engine_page2
       -> call_init
```

## Direct cross-module CALLs

### `src/core/startup_io.asm`

- → `src/core/mapper_kspos.asm`: `capture_original_pages`, `cleanup`, `get_mapper_api`, `kspos_configure_engine_runtime`, `map_p1`, `mapper_alloc_user_primary`, `mapper_free_primary`, `restore_process_pages`
- → `src/platform/hardware.asm`: `kspos_detect_and_prepare`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`, `vram_set_write_address`
- → `src/runtime/compat_helpers.asm`: `fcb_prepare_filename`
- → `src/runtime/engine_calls_audio.asm`: `mute_fmpac_before_disk_io`
- → `src/runtime/service_runtime_image.asm`: `menu_reset_probe_state`
- → `src/runtime/track_engine.asm`: `decode_template_page`

### `src/core/mapper_kspos.asm`

- → `src/core/startup_io.asm`: `fcb_close_current`, `free_page3_workram_segment`, `free_template_segment`
- → `src/platform/runtime_audio.asm`: `free_mwk_segment`
- → `src/runtime/compat_helpers.asm`: `restore_secondary_slot_state`
- → `src/runtime/engine_calls_audio.asm`: `stop_and_mute`
- → `src/runtime/stream_decode.asm`: `restore_refresh_rate`
- → `src/ui/game_intro.asm`: `capture_secondary_slot_state`
- → `src/ui/overlay_loader.asm`: `page_runtime_available`
- → `src/ui/package_loader.asm`: `hpol_map_release`
- → `src/ui/text_renderer.asm`: `ui_reset_package_state`

### `src/format/ksp_format.asm`

- → `src/core/mapper_kspos.asm`: `restore_process_pages`
- → `src/core/startup_io.asm`: `read_at`
- → `src/platform/vdp.asm`: `vram_set_warm_base_write`, `vram_set_write_address`
- → `src/runtime/stream_decode.asm`: `stream_begin`, `zx_decode_stream`, `zx_set_output_size`
- → `src/runtime/track_engine.asm`: `mul16x16_24`

### `src/runtime/track_engine.asm`

- → `src/core/mapper_kspos.asm`: `kspos_sync_gateway`, `kspos_verify_engine_memory`, `map_p2`, `restore_process_pages`
- → `src/core/startup_io.asm`: `initialize_page3_workram_segment`, `read_at`
- → `src/format/ksp_format.asm`: `load_engine_index`, `validate_engine_profile`
- → `src/platform/runtime_audio.asm`: `free_mwk_segment`, `upload_current_mwk`
- → `src/platform/vdp.asm`: `vram_set_read_address`
- → `src/runtime/engine_calls_audio.asm`: `stop_and_mute`
- → `src/runtime/stream_decode.asm`: `stream_begin`, `zx_decode_stream`, `zx_set_output_size`
- → `src/ui/game_intro.asm`: `prepare_engine_page2_for_install`, `ui_init_track_engine`
- → `src/ui/overlay_loader.asm`: `page_runtime_available`
- → `src/ui/status_errors.asm`: `ui_load_hvar_overlay`

### `src/runtime/engine_calls_audio.asm`

- → `src/boot/KSPOS_GATEWAY.asm`: `KSPOS_CALL_INIT`, `KSPOS_CALL_PLAY`, `KSPOS_CALL_STOP`
- → `src/core/mapper_kspos.asm`: `map_scc_page2`, `restore_process_pages`
- → `src/runtime/compat_helpers.asm`: `dual_scc_select_a`, `dual_scc_select_b`, `map_ram_page2`
- → `src/ui/KSPMENU.asm`: `KSPMENU_ENTRY_UPDATE_ROW`
- → `src/ui/status_errors.asm`: `ui_load_hvar_overlay`
- → `src/ui/text_layout.asm`: `save_interrupt_hook`

### `src/runtime/stream_decode.asm`

- → `src/core/mapper_kspos.asm`: `map_p1`, `map_p2`, `restore_process_pages`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`
- → `src/runtime/engine_calls_audio.asm`: `mute_fmpac_before_disk_io`

### `src/ui/overlay_loader.asm`

- → `src/core/startup_io.asm`: `fcb_close_current`, `fcb_open_current`, `fcb_read_current`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_write_address`
- → `src/runtime/service_runtime_image.asm`: `menu_scan_scc_slots`
- → `src/ui/KSPMENU.asm`: `MENU_SHOW_HARDWARE_PAGE`
- → `src/ui/track_browser.asm`: `ui_draw_player_track_index`

### `src/runtime/compat_helpers.asm`

- → `src/core/mapper_kspos.asm`: `map_primary_slot_page2`, `restore_process_pages`
- → `src/runtime/engine_calls_audio.asm`: `prepare_engine_page2`
- → `src/ui/overlay_loader.asm`: `page_runtime_available`

### `src/ui/startup_splash.asm`

- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vram_set_write_address`
- → `src/ui/input.asm`: `ui_capture_keys`, `ui_poll_action`
- → `src/ui/overlay_loader.asm`: `ui_activate_menu_vdp`, `ui_preload_logo`, `ui_reload_menu_overlay`, `ui_restore_player_from_menu`, `wait_vblank`

### `src/ui/application.asm`

- → `src/core/mapper_kspos.asm`: `cleanup`
- → `src/runtime/compat_helpers.asm`: `ui_recompute_track_total`
- → `src/runtime/engine_calls_audio.asm`: `next_track`, `prepare_engine_page2`
- → `src/ui/game_intro.asm`: `ui_game_intro`, `ui_switch_to_metadata_view`
- → `src/ui/input.asm`: `ui_capture_keys`
- → `src/ui/menu_backend.asm`: `menu_overlay_entry`
- → `src/ui/metadata_playback.asm`: `playback_time_reset`, `ui_draw_help_hint`, `ui_draw_playback_time`, `ui_enter_track_view`, `ui_help_action`, `ui_metadata_page_next`, `ui_metadata_page_prev`, `ui_poll_playback_action`, `ui_service_view_redraw`, `ui_toggle_metadata_track_view`, `ui_track_page_next`, `ui_track_page_prev`
- → `src/ui/package_loader.asm`: `ui_install_selected_track`, `ui_load_pack`
- → `src/ui/startup_splash.asm`: `wait_vblank_without_keyclick`
- → `src/ui/status_errors.asm`: `ui_show_error`
- → `src/ui/text_layout.asm`: `save_interrupt_hook`, `ui_clear_bios_keyboard_buffer`, `ui_prepare_menu_overlay`, `ui_release_menu_overlay`, `ui_restore_text2_screen`
- → `src/ui/text_renderer.asm`: `ui_enable_text80`, `ui_prepare_game_title`, `ui_restore_text2_mode_only`
- → `src/ui/track_browser.asm`: `previous_track`, `ui_menu`, `ui_redraw_track_page`

### `src/ui/package_loader.asm`

- → `src/core/mapper_kspos.asm`: `allocate_hot_segments`, `mapper_free_primary`, `release_engine_resources`
- → `src/core/startup_io.asm`: `allocate_page3_workram_segment`, `allocate_template_segment`, `fcb_open_current`, `preload_file_cache`, `preload_template_page`, `read_at`
- → `src/format/ksp_format.asm`: `find_hpol_resource`, `load_hpl_header`, `preload_hybrid_pool`, `validate_engine_profile`, `validate_header`
- → `src/platform/runtime_audio.asm`: `validate_required_hardware`
- → `src/runtime/stream_decode.asm`: `configure_engine_refresh`
- → `src/runtime/track_engine.asm`: `install_current_track`, `select_track`
- → `src/ui/KSPMENU.asm`: `KSPMENU_ENTRY_VDP_SETUP`, `MENU_SETUP_VDP`
- → `src/ui/overlay_loader.asm`: `page_runtime_available`
- → `src/ui/status_errors.asm`: `ui_load_hvar_overlay`
- → `src/ui/text_renderer.asm`: `ui_begin_track_change`
- → `src/ui/track_browser.asm`: `ui_read_track_title`

### `src/ui/track_browser.asm`

- → `src/core/mapper_kspos.asm`: `restore_process_pages`
- → `src/core/startup_io.asm`: `read_at`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`
- → `src/runtime/track_engine.asm`: `mul16x16_24`
- → `src/ui/KSPMENU.asm`: `KSPMENU_ENTRY_REDRAW_LIST`
- → `src/ui/game_intro.asm`: `ui_switch_to_metadata_view`
- → `src/ui/input.asm`: `ui_capture_keys`, `ui_poll_action`
- → `src/ui/menu_backend.asm`: `menu_ovl_get_line`, `menu_ovl_refresh`
- → `src/ui/metadata_playback.asm`: `ui_enter_track_view`, `ui_metadata_page_next`, `ui_metadata_page_prev`, `ui_service_view_redraw`, `ui_track_page_next`, `ui_track_page_prev`
- → `src/ui/overlay_loader.asm`: `ui_menu_move_up_dynamic`, `ui_menu_store_selection`, `ui_tracks_per_page`, `wait_vblank`
- → `src/ui/status_errors.asm`: `ui_load_hvar_overlay`
- → `src/ui/text_layout.asm`: `save_interrupt_hook`, `ui_draw_common_header`, `ui_draw_frame`, `ui_draw_menu_header`, `ui_line_append_char`, `ui_line_append_string`, `ui_line_append_u16`, `ui_line_clear`, `ui_line_terminate`, `ui_screen5_init`, `ui_text_line`, `ui_write_char`, `ui_write_field`
- → `src/ui/text_renderer.asm`: `pager_prev`, `ui_menu_page_next_dynamic`, `ui_restore_text2_mode_only`

### `src/ui/status_errors.asm`

- → `src/core/mapper_kspos.asm`: `restore_process_pages`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vram_set_read_address`
- → `src/ui/input.asm`: `ui_capture_keys`, `ui_poll_action`
- → `src/ui/text_layout.asm`: `ui_line_append_string`, `ui_line_append_u16`, `ui_line_clear`, `ui_line_terminate`, `ui_screen5_init`, `ui_text_line`

### `src/ui/text_layout.asm`

- → `src/core/mapper_kspos.asm`: `map_p1`, `map_p2`, `mapper_alloc_user_primary`, `mapper_free_primary`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`, `vram_set_write_address`
- → `src/ui/input.asm`: `ui_scan_keyboard_rows`
- → `src/ui/status_errors.asm`: `div10_u16`

### `src/ui/game_intro.asm`

- → `src/core/mapper_kspos.asm`: `map_scc_page2`
- → `src/platform/runtime_audio.asm`: `prepare_opl4_init`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`
- → `src/runtime/engine_calls_audio.asm`: `call_init`
- → `src/ui/input.asm`: `ui_capture_keys`, `ui_poll_action`
- → `src/ui/metadata_playback.asm`: `ui_enter_metadata_view`
- → `src/ui/status_errors.asm`: `ui_load_hvar_overlay`
- → `src/ui/text_layout.asm`: `ui_draw_common_header`, `ui_draw_hline`, `ui_line_clear`, `ui_screen5_init`, `ui_write_char`, `ui_write_field`
- → `src/ui/text_renderer.asm`: `ui_restore_text2_mode_only`

### `src/platform/runtime_audio.asm`

- → `src/core/mapper_kspos.asm`: `mapper_free_primary`
- → `src/ui/overlay_loader.asm`: `page_runtime_available`

### `src/ui/metadata_playback.asm`

- → `src/ui/game_intro.asm`: `ui_draw_cached_help_row_resident`
- → `src/ui/text_layout.asm`: `ui_line_append_char`, `ui_line_append_string`, `ui_line_append_u16`, `ui_line_clear`, `ui_text_line`
- → `src/ui/track_browser.asm`: `ui_draw_full_track_row`, `ui_draw_selected_track_title`, `ui_load_track_page_indices`, `ui_redraw_track_heading`

### `src/ui/text_renderer.asm`

- → `src/core/mapper_kspos.asm`: `restore_process_pages`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`, `vram_set_write_address`
- → `src/ui/game_intro.asm`: `ui_show_loading_track_message`
- → `src/ui/metadata_playback.asm`: `ui_draw_help_hint`
- → `src/ui/overlay_loader.asm`: `ui_tracks_per_page`
- → `src/ui/text_layout.asm`: `call_main_bios`, `ui_write_vdp_register`
- → `src/ui/track_browser.asm`: `ui_draw_selected_track_title`

### `src/ui/menu_backend.asm`

- → `src/core/startup_io.asm`: `fcb_close_current`, `fcb_open_current`, `read_at`
- → `src/platform/hardware.asm`: `menu_detect_hardware`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vram_set_write_address`
- → `src/runtime/compat_helpers.asm`: `fcb_prepare_filename`
- → `src/runtime/track_engine.asm`: `mul16x16_24`
- → `src/ui/text_layout.asm`: `ui_line_fill_spaces`, `ui_text_line`
- → `src/ui/track_browser.asm`: `ui_filename_slot_address`

### `src/platform/hardware.asm`

- → `src/core/mapper_kspos.asm`: `map_p2`, `mapper_alloc_user_primary`, `restore_process_pages`
- → `src/platform/runtime_audio.asm`: `opl4_fm_wait`, `opl4_wave_wait`
- → `src/runtime/service_runtime_image.asm`: `probe_writable_memory_byte`
- → `src/ui/overlay_loader.asm`: `menu_scan_scc_slots_preserve_slot_state`
- → `src/ui/text_layout.asm`: `ui_line_append_string`, `ui_line_fill_spaces`, `ui_line_terminate`
- → `src/ui/text_renderer.asm`: `install_runtime_images`

### `src/runtime/service_runtime_image.asm`

- → `src/core/mapper_kspos.asm`: `map_p2`, `mapper_alloc_user_primary`, `restore_process_pages`
- → `src/core/startup_io.asm`: `read_at`
- → `src/platform/hardware.asm`: `menu_probe_scc_slot`
- → `src/platform/runtime_audio.asm`: `opl4_write_wave`
- → `src/runtime/engine_calls_audio.asm`: `mute_fmpac_before_disk_io`, `prepare_engine_page2`
- → `src/runtime/stream_decode.asm`: `stream_begin`, `stream_end`, `zx_decode_stream`, `zx_set_output_size`
- → `src/runtime/track_engine.asm`: `mul16x16_24`
- → `src/ui/overlay_loader.asm`: `ui_load_menu_binary`
- → `src/ui/startup_splash.asm`: `ui_run_menu_overlay`

### `src/runtime/hvar_runtime_image.asm`

- → `src/core/mapper_kspos.asm`: `restore_process_pages`
- → `src/core/startup_io.asm`: `read_at`
- → `src/platform/runtime_audio.asm`: `validate_required_hardware`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`, `vram_set_write_address`
- → `src/runtime/stream_decode.asm`: `stream_begin`, `zx_decode_stream`, `zx_set_output_size`
- → `src/runtime/track_engine.asm`: `load_track_context`, `mul16x16_24`
- → `src/ui/overlay_loader.asm`: `vdp_write_data_word`
- → `src/ui/status_errors.asm`: `ui_build_hardware_line`
- → `src/ui/text_layout.asm`: `ui_write_field`
- → `src/ui/track_browser.asm`: `ui_read_track_title`

### `src/runtime/service_img5_tail.asm`

- → `src/core/startup_io.asm`: `read_at`
- → `src/platform/vdp.asm`: `vdp_irq_begin`, `vdp_irq_end`, `vram_set_read_address`, `vram_set_write_address`
- → `src/runtime/track_engine.asm`: `mul16x16_24`
- → `src/ui/input.asm`: `ui_capture_keys`, `ui_poll_action`
- → `src/ui/text_renderer.asm`: `ui_restore_text2_mode_only`

