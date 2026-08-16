# TinyKSP 1.9.8 validation

Validated on Linux x86-64:

- release build with bundled libvgm;
- version output reports 1.9.8;
- existing PTY seek, arrow and channel-mute controls;
- automatic track-to-track and file-to-file wildcard progression;
- manual Right Arrow transition from the final playable track to the next KSP file.

The manual transition test opens two wildcard-matched KSP files, selects the second track with Right Arrow, presses Right Arrow again, and verifies that file 2 is opened.
