source "/Volumes/EXT_SSD/AI/libkss_conversion_tools/openmsx_debug/openmsx_trace.tcl"

set power on

after boot {
    after realtime 30 {type "KSP1PLAY.COM FRAY.KSP 0 2"}
    after realtime 31 {type "\r"}
    after realtime 45 {
        set f [open "/tmp/fray-page1-snapshot.txt" w]
        puts $f "PC=[format %04X [reg PC]]"
        puts $f "PAGE0=[format %02X [debug read ioports 0xFC]]"
        puts $f "PAGE1=[format %02X [debug read ioports 0xFD]]"
        puts $f "PAGE2=[format %02X [debug read ioports 0xFE]]"
        puts $f "PAGE3=[format %02X [debug read ioports 0xFF]]"
        puts $f "A8=[format %02X [debug read ioports 0xA8]]"
        puts $f "4000=[binary encode hex [debug read_block memory 0x4000 0x40]]"
        puts $f "4CAB=[binary encode hex [debug read_block memory 0x4CAB 0x20]]"
        puts $f "4E00=[binary encode hex [debug read_block memory 0x4E00 0x40]]"
        puts $f "B800=[binary encode hex [debug read_block memory 0xB800 0x40]]"
        puts $f "580D=[binary encode hex [debug read_block memory 0x580D 0x20]]"
        close $f
        exit
    }
}
