; Fixed host-layout reservations between embedded runtimes.
; These bytes are intentionally zero-filled and are part of the binary ABI.
ds 46,0
recon_overlay_storage_end:
service_overlay_tail_storage:
ds 79,0
