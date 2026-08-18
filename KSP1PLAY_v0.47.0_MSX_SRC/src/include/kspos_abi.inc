; KSPOS gateway ABI in page 0 and shared state in page 3.
KSPOS_INFO                equ 0006Bh
KSPOS_API_VERSION         equ 0006Fh
KSPOS_FLAGS               equ 00070h
KSPOS_TOTAL_SEGMENTS      equ 00071h
KSPOS_FREE_SEGMENTS       equ 00072h
KSPOS_PLAYER_P0           equ 00073h
KSPOS_RUNTIME_P0          equ 00074h
KSPOS_ORIGINAL_P3         equ 00075h
KSPOS_ENGINE_P3           equ 00076h
KSPOS_UNAVAILABLE_COUNT   equ 00077h
KSPOS_RANGE0_START        equ 00078h
KSPOS_RANGE0_END          equ 0007Ah
KSPOS_RANGE1_START        equ 0007Ch
KSPOS_RANGE1_END          equ 0007Eh
KSPOS_CALL_INIT           equ 00081h
KSPOS_CALL_PLAY           equ 00088h
KSPOS_CALL_STOP           equ 0008Fh
KSPOS_TARGET_INIT         equ 000F0h
KSPOS_TARGET_PLAY         equ 000F2h
KSPOS_TARGET_STOP         equ 000F4h
KSPOS_SAVED_PLAYER_SP     equ 000F6h

ENGINE_DIRECT_CALL_PATCH  equ 00000h

; Shared page-3 state.
HVAR_PRESENT              equ 0C300h
IMPLEMENTATION_TRACK      equ 0C312h
CURRENT_ENGINE             equ 0C314h
PREPARED_ENGINE            equ 0C316h
AVAILABLE_HARDWARE         equ 0C318h
VISIBLE_TRACK_COUNT        equ 0C319h
FIRST_VISIBLE_TRACK        equ 0C31Bh
KSPOS_HW_CACHE_FLAGS       equ 0C31Eh
KSPOS_HW_CACHE_SCC_COUNT   equ 0C31Fh
TRACK_CACHE_INDICES        equ 0C320h
HVAR_CACHE_TRACK           equ 08BF0h

; C300h is also reused as a temporary title/sample-header workspace while
; playback is stopped and the corresponding overlay owns page 3.
SHARED_TITLE_BUFFER        equ 0C300h
MWK_SAMPLE_HEADER_BUFFER   equ SHARED_TITLE_BUFFER+64
MWK_OPL4_HEADER_BUFFER     equ SHARED_TITLE_BUFFER+80
