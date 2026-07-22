# Focused deterministic trace for KSP1PLAY/Nemesis 3 track 7.
# Mount the repository's msx directory as drive A; this script starts the
# player from the MSX-DOS2 prompt after boot.

source "/Volumes/EXT_SSD/AI/libkss_conversion_tools/openmsx_debug/openmsx_trace.tcl"

set trace_dir "/tmp/libksp-nem3-track7"
file mkdir $trace_dir

set power on
set mute off
set master_volume 100
set PSG_volume 100
set SCC_volume 100

after boot {
    trace_mapper none
    trace_pc_enabled off
    trace_mem_ranges {{0x9000 0x9000} {0x9800 0x988F}}
    trace_io_ranges {{0xA0 0xA1}}
    trace_start [file join $::trace_dir audio-writes.log]
    soundlog start [file join $::trace_dir audio.wav]

    after realtime 8 {type "KSP1PLAY.COM NEMESIS3.KSP 7 2"}
    after realtime 10 {type "\r"}

    after realtime 35 {
        set state [open [file join $::trace_dir state.txt] w]
        foreach regname {PC SP AF BC DE HL IX IY} {
            puts $state "$regname=[format %04X [reg $regname]]"
        }
        foreach port {0xA8 0xFD 0xFE 0xFF} {
            puts $state "PORT_[format %02X $port]=[format %02X [debug read ioports $port]]"
        }
        puts $state "PAGE1_HEAD=[binary encode hex [debug read_block memory 0x4000 0x40]]"
        close $state
        soundlog stop
        trace_stop
        exit
    }
}
