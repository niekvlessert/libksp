# Fray page-1 diagnostic console script.
#
# Run this from a fresh openMSX instance. It waits 30 seconds before typing
# the command, records FM writes and lightweight control markers, and saves
# periodic memory snapshots. The files are written under /tmp.

source "/Volumes/EXT_SSD/AI/libkss_conversion_tools/openmsx_debug/openmsx_trace.tcl"

set power on
set mute off
set master_volume 100
set PSG_volume 100

namespace eval ::fraydiag {
    variable state_file "/tmp/fray-page1-console-state.log"
    variable marker_fh ""
    variable marker_ids {}
    variable markers_enabled 0
    variable started 0

    proc snapshot {tag} {
        variable state_file
        set f [open $state_file a]
        set t [machine_info time]
        puts $f "SNAP tag=$tag time=$t"
        puts $f "PC=[format %04X [reg PC]] SP=[format %04X [reg SP]]"
        foreach item {{A8 0xA8} {FC 0xFC} {FD 0xFD} {FE 0xFE} {FF 0xFF}} {
            lassign $item name port
            puts $f "PORT_$name=[format %02X [debug read ioports $port]]"
        }
        foreach item {
            {4000 0x4000 0x40}
            {4CAB 0x4CAB 0x20}
            {4E00 0x4E00 0x40}
            {4E2A 0x4E2A 0x10}
            {4ECD 0x4ECD 0x20}
            {4F76 0x4F76 0x20}
            {580D 0x580D 0x20}
            {B800 0xB800 0x100}
        } {
            lassign $item name address length
            puts $f "$name=[binary encode hex [debug read_block memory $address $length]]"
        }
        close $f

        puts "FRAY_DIAG SNAP tag=$tag time=$t PC=[format %04X [reg PC]] A8=[format %02X [debug read ioports 0xA8]] FC=[format %02X [debug read ioports 0xFC]] FD=[format %02X [debug read ioports 0xFD]] FE=[format %02X [debug read ioports 0xFE]] FF=[format %02X [debug read ioports 0xFF]]"
    }

    proc on_marker {tag} {
        variable marker_fh
        puts $marker_fh [format "MARK %.9f TAG=%s PC=%04X SP=%04X AF=%04X BC=%04X DE=%04X HL=%04X" \
            [machine_info time] $tag [reg PC] [reg SP] [reg AF] [reg BC] [reg DE] [reg HL]]
    }

    proc finish {} {
        snapshot final
        catch {soundlog stop}
        variable marker_ids
        foreach id $marker_ids {
            catch {debug condition remove $id}
        }
        variable marker_fh
        variable markers_enabled
        catch {close $marker_fh}
        trace_stop
        set marker_path disabled
        if {$markers_enabled} {
            set marker_path /tmp/fray-page1-control-markers.log
        }
        puts "FRAY_DIAG DONE state=/tmp/fray-page1-console-state.log trace=/tmp/fray-page1-console-trace.log markers=$marker_path"
        exit
    }
}

proc ::fraydiag::start {} {
    variable started
    if {$started} {
        puts "FRAY_DIAG already started"
        return
    }
    set started 1

    catch {trace_stop}
    file delete -force /tmp/fray-page1-console-state.log
    file delete -force /tmp/fray-page1-console-trace.log
    file delete -force /tmp/fray-page1-control-markers.log

    # Keep this run deliberately light: FM writes, snapshots, and a few
    # control-entry markers. Per-read watchpoints and mapper callbacks make
    # openMSX too slow to reach playback.
    trace_mapper none
    trace_pc_range 0x4CAB 0x4ECD
    trace_pc_enabled off
    trace_disasm off
    trace_mem_ranges {}
    trace_io_ranges {{0x7C 0x7D}}
    trace_start {/tmp/fray-page1-console-trace.log}

    # trace_start also installs a continuous FC-FF RAM-mapper watchpoint.
    # Remove that one callback for this lightweight run; the snapshots still
    # record FC/FD/FE/FF and the relevant memory windows.
    set trace_ids $::omtrace::ids
    if {[llength $trace_ids] > 0} {
        set mapper_item [lindex $trace_ids end]
        lassign $mapper_item mapper_type mapper_id
        if {$mapper_type eq "watchpoint"} {
            catch {debug watchpoint remove $mapper_id}
            set ::omtrace::ids [lrange $trace_ids 0 end-1]
        }
    }

    if {$::fraydiag::markers_enabled} {
        set ::fraydiag::marker_fh [open /tmp/fray-page1-control-markers.log w]
        fconfigure $::fraydiag::marker_fh -buffering line -translation lf -encoding utf-8
        set ::fraydiag::marker_ids {}
        foreach item {{install 0x0E5B} {next_track 0x129C} {clean_exit 0x027D}} {
            lassign $item tag pc
            set id [debug condition create \
                -condition "\[reg PC\] == $pc" \
                -command [list ::fraydiag::on_marker $tag]]
            lappend ::fraydiag::marker_ids $id
        }
    }

    ::fraydiag::snapshot boot
    after realtime 25 {::fraydiag::snapshot pre_command}
    after realtime 30 {
        puts "FRAY_DIAG typing KSP1PLAY.COM FRAY.KSP 0 2 after 30 seconds"
        type "KSP1PLAY.COM FRAY.KSP 0 2"
    }
    after realtime 31 {type "\r"}
    after realtime 36 {::fraydiag::snapshot post_command}
    after realtime 40 {catch {soundlog start /tmp/fray-page1-console.wav}}
    after realtime 55 {::fraydiag::snapshot playback}
    after realtime 65 {::fraydiag::finish}
}

# Fresh launch: start once DOS has completed booting. From an already-running
# openMSX console, source this file and then run: ::fraydiag::start
after boot {::fraydiag::start}
