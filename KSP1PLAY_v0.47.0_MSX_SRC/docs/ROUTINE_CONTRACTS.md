# Key routine contracts

These are orientation contracts for cross-subsystem and timing-sensitive entry
points. The source remains authoritative for exact clobbers in small helpers.

## `start`

- Purpose: initialize process state, mapper/KSPOS integration and enter the UI.
- Preconditions: player loaded at `0100h`, normal KSPOS boot environment.
- Side effects: establishes stack, mapper snapshots, runtime state and display.
- Normal result: control enters `ui_application`; terminal errors use error/exit paths.

## `read_at`

- Purpose: read package bytes at a 24-bit file position into RAM.
- Inputs: package offset/count/destination as set by its callers and FCB state.
- Output: success/failure status used by package/parser callers.
- Constraint: not permitted in the normal PLAY hot path.

## `select_track`

- Purpose: validate a logical/visible selection and resolve its package track context.
- Input: selected logical track in `HL`.
- Output: carry set on invalid/failed selection; selected implementation state on success.
- Side effects: may invoke HVAR selection logic and update shared track state.

## `install_current_track`

- Purpose: materialize required pages and install the selected track/engine state.
- Preconditions: selected package/track context is valid and playback transition is safe.
- Output: carry indicates install failure.
- Side effects: page/cache state and engine gateways may change.

## `prepare_engine_page2`

- Purpose: establish the page-2 mapping required by the prepared engine.
- Constraint: mapper ownership must agree with cleanup/restore paths.

## `call_init`, `call_play`, `call_stop`

- Purpose: invoke the active engine through the KSPOS/player gateway contract.
- `call_play` is timing-sensitive and must remain free of disk/FAT/BDOS work.
- Stop/error paths must not leave audio hardware or mapper pages owned incorrectly.

## `ui_application`

- Purpose: top-level stopped-state/browser/playback state machine.
- Owns transitions among menu, package preparation, game presentation, playback,
  error handling and final exit.

## `ui_load_pack`

- Purpose: open and validate the selected package, initialize package state and
  prepare the selected hardware/engine context.
- Output: carry/error code on failure.
- Constraint: failures must remain recoverable by the application error path.

## `ui_poll_action` / playback action dispatch

- Purpose: convert keyboard state to `ACTION_CODE_*` values.
- Output: zero/no action or a named action code from `ui_constants.inc`.
- Rule: add new actions by extending the constants and dispatch deliberately;
  do not introduce magic numeric comparisons.

## `install_runtime_images`

- Purpose: copy fixed host images to the runtime addresses required by the
  current phase.
- Preconditions: mapper/display state permits the copy.
- Rule: use host/target constants from ABI/memory includes; never infer the
  destination from where the bytes happen to be stored.

## `page_runtime_available`

- Purpose: report whether the page-materialization runtime is available for the
  current operation.
- Callers must retain their normal failure/compatibility path when unavailable.

## `menu_detect_hardware`

- Purpose: build the capability state used for package implementation selection.
- Includes SCC/SCC+ slot probing and other configured sound-hardware checks.
- Must leave slot mapping suitable for subsequent player setup.
