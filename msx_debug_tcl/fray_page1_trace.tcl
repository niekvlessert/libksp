# Deterministic openMSX trace for the page-1 Fray pack.
source "/Volumes/EXT_SSD/AI/libkss_conversion_tools/openmsx_debug/openmsx_trace.tcl"

set power on

after boot {
    trace_mapper none
    trace_pc_range 0x4C00 0x5800
    trace_pc_enabled on
    trace_disasm on
    # Any write through C000h-FFFFh is a DOS page-3 write in this profile.
    trace_mem_ranges {}
    trace_io_ranges {{0x7C 0x7D} {0xA0 0xA1} {0xFC 0xFF}}
    trace_start {/tmp/fray-page1-trace.log}
    after realtime 30 {type "KSP1PLAY.COM FRAY.KSP 0 2"}
    after realtime 31 {type "\r"}
    after realtime 50 {
        trace_stop
        exit
    }
}
