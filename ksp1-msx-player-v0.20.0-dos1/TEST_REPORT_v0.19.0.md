# KSP1PLAY 0.19.0 test report

- Bundled two-pass assembler completed successfully.
- All existing KSP 1.00/1.01, sparse, HPOL, ZX0, dual-SCC, MoonSound, FMPAC and graphical UI model tests passed.
- New lifecycle model verifies that all package allocations are freed before state is reset.
- New lifecycle model verifies allocation ownership is not erased at the start of the next package load.
- New exit model verifies physical key release, BIOS KILBUF use and native 80-column SCREEN 0 initialization.
- Runtime emulator/physical-MSX testing remains required for repeated package-switch stress testing.
