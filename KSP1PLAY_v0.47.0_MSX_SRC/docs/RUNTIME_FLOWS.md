# Runtime flows

## Startup

```text
start
  -> initialize stack / defaults
  -> get_mapper_api
  -> capture_original_pages
  -> kspos_detect_and_prepare
  -> hardware capability setup
  -> ui_application
```

Failure before the UI uses the startup error paths and restores the machine state
as far as the completed initialization permits.

## Package selection and load

```text
ui_application
  -> ui_prepare_menu_overlay
  -> ui_menu
  -> ui_release_menu_overlay
  -> ui_load_pack
       -> open/read KSP header
       -> validate package tables
       -> prepare HVAR/metadata state when present
       -> choose required hardware implementation
       -> prepare page/cache state
  -> ui_prepare_game_title
  -> ui_game_intro
  -> UI_PRELOAD_IMG5_GALLERY
  -> ui_install_selected_track
```

## Track install

```text
ui_install_selected_track
  -> select_track
       -> resolve logical/visible track
       -> load track descriptor/context
  -> ui_prepare_selected_engine
       -> prepare required engine/page resources
  -> install_current_track
       -> materialize required pages
       -> patch engine gateways
       -> prepare_engine_page2
       -> initialize track engine
       -> call_init
```

Treat the install path transactionally. Any new failure path must leave mapper,
interrupt and audio state suitable for cleanup or return to the browser.

## Playback hot path

```text
ui_play_screen
  -> ui_play_loop
       -> wait_vblank_without_keyclick
       -> call_play             (unless muted/paused)
       -> ui_service_view_redraw
       -> ui_poll_playback_action
       -> action-specific handler
       -> ui_play_loop
```

The normal PLAY path is timing-sensitive and must remain free of package-file,
FAT and BDOS disk activity.

## Track next/previous

```text
next_track / previous_track
  -> stop/restore active process pages
  -> resolve next visible logical track through HVAR when needed
  -> update selected track
  -> install selected track
  -> reset playback-time state
  -> redraw current presentation
```

## Stop / return to browser

Cleanup paths stop and mute the engine, restore mapper/slot state, restore the
interrupt hook and return the display/input state to the stopped-state UI.

## Metadata / images

Metadata drawing is delegated to the HVAR runtime when loaded. IMG5 preload and
presentation use service-runtime code and VRAM buffers. These subsystems are not
ordinary calls into KSPMENU even though some phases reuse `8000h`.
