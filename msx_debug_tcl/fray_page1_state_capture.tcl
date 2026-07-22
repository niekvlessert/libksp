# Low-overhead deterministic Fray state capture.
#
# Captures page 1 immediately before selected PLAY calls. There is no
# continuous instruction, I/O, mapper, or memory logging.

set power on
set mute off
set master_volume 100
set PSG_volume 100

namespace eval ::fraystate {
    variable frame 0
    variable breakpoint_id ""
    variable prefix "/tmp/fray-page1-state"
    variable timing_wp ""
    variable timing_events 0
    variable timing_last_port -1
    variable timing_last_time 0.0
    variable timing_min_a2d 1000000.0
    variable timing_min_d2a 1000000.0
    variable timing_a2d_count 0
    variable timing_d2a_count 0

    proc measure_fm_write {} {
        variable timing_wp
        variable timing_events
        variable timing_last_port
        variable timing_last_time
        variable timing_min_a2d
        variable timing_min_d2a
        variable timing_a2d_count
        variable timing_d2a_count

        set port [expr {$::wp_last_address & 0xFF}]
        set now [machine_info time]
        if {$timing_last_port >= 0} {
            set delta [expr {($now - $timing_last_time) * 1000000.0}]
            if {$timing_last_port == 0x7C && $port == 0x7D} {
                incr timing_a2d_count
                if {$delta < $timing_min_a2d} {
                    set timing_min_a2d $delta
                }
            } elseif {$timing_last_port == 0x7D && $port == 0x7C} {
                incr timing_d2a_count
                if {$delta < $timing_min_d2a} {
                    set timing_min_d2a $delta
                }
            }
        }
        set timing_last_port $port
        set timing_last_time $now
        incr timing_events
        if {$timing_events == 500} {
            debug watchpoint remove $timing_wp
            set timing_wp ""
            set f [open /tmp/fray-page1-fm-timing.txt w]
            puts $f [format "events=%d address_to_data_count=%d min_address_to_data_us=%.6f data_to_address_count=%d min_data_to_address_us=%.6f" \
                $timing_events $timing_a2d_count $timing_min_a2d \
                $timing_d2a_count $timing_min_d2a]
            close $f
        }
    }

    proc save_block {path address length} {
        set f [open $path wb]
        fconfigure $f -translation binary -encoding binary
        puts -nonewline $f [debug read_block memory $address $length]
        close $f
    }

    proc capture {} {
        variable frame
        variable prefix
        incr frame
        if {$frame == 1} {
            variable timing_wp
            file delete -force /tmp/fray-page1-fm-timing.txt
            set timing_wp [debug watchpoint create -type write_io \
                -address {0x7C 0x7D} -condition {} \
                -command {::fraystate::measure_fm_write}]
        }
        if {$frame ni {1 2 60 600}} {
            return
        }

        set stem [format "%s-frame-%04d" $prefix $frame]
        save_block "${stem}-page1.bin" 0x4000 0x4000
        save_block "${stem}-page2.bin" 0x8000 0x4000

        set f [open "${stem}-meta.txt" w]
        puts $f [format "frame=%d time=%.9f PC=%04X SP=%04X AF=%04X BC=%04X DE=%04X HL=%04X IX=%04X IY=%04X" \
            $frame [machine_info time] [reg PC] [reg SP] [reg AF] [reg BC] \
            [reg DE] [reg HL] [reg IX] [reg IY]]
        foreach item {{A8 0xA8} {FC 0xFC} {FD 0xFD} {FE 0xFE} {FF 0xFF}} {
            lassign $item name port
            puts $f "PORT_$name=[format %02X [debug read ioports $port]]"
        }
        close $f
        puts "FRAY_STATE captured frame $frame"

        if {$frame == 600} {
            finish
        }
    }

    proc finish {} {
        variable breakpoint_id
        catch {debug remove_bp $breakpoint_id}
        puts "FRAY_STATE DONE"
        exit
    }

    proc start {} {
        variable breakpoint_id
        variable prefix
        foreach path [glob -nocomplain "${prefix}-frame-*"] {
            file delete -force $path
        }
        set breakpoint_id [debug set_bp 0x4E00 {} {::fraystate::capture}]

        # Leave ample time for DOS startup. Enter is sent separately so the
        # complete command is already in the keyboard buffer before execution.
        after realtime 30 {type "KSP1PLAY.COM FRAY.KSP 0 2"}
        after realtime 31 {type "\r"}
        after realtime 90 {::fraystate::finish}
        puts "FRAY_STATE armed; command will start after 30 seconds"
    }
}

after boot {::fraystate::start}
