; Page-3 playback-control helper. The first three addresses are the stable
; jump-table calls; the *_IMPL names identify their resident implementations.
UI_P3_CALL_CURSOR_UP       equ 0C35Ch
UI_P3_CALL_CURSOR_DOWN     equ 0C35Fh
UI_P3_CALL_PAUSE_TOGGLE    equ 0C362h
UI_P3_CURSOR_UP_IMPL       equ 0C365h
UI_P3_CURSOR_DOWN_IMPL     equ 0C36Eh
UI_P3_CURSOR_SET           equ 0C375h
UI_P3_PAUSE_TOGGLE_IMPL    equ 0C3A1h
UI_P3_PAUSE_PSG_RESTORE    equ 0C3C0h
UI_P3_PAUSE_SCC            equ 0C3C5h
UI_P3_PAUSE_SCC_ADDR       equ 0C3DEh
UI_P3_PAUSE_SCC_RESTORE    equ 0C3EEh
UI_P3_PAUSE_SCC_REMAP      equ 0C3F2h
UI_P3_PAUSE_DONE           equ 0C3F5h
UI_P3_PAUSE_PSG            equ 0C3F8h
UI_P3_PAUSE_SCC_ENABLE     equ 0C3F9h
UI_P3_OVERLAY_END          equ 0C3FAh
