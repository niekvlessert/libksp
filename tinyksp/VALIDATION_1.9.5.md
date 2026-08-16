# TinyKSP 1.9.5 validation

- Complete 1.9.4 source tree was used as the baseline.
- The libvgm adapter and all modified TinyKSP C++ sources compile and link
  against an API-compatible libvgm test target.
- Source archive integrity and internal SHA-256 checks were verified.
- The build configuration uses the upstream `vgm-emu` target with only the
  YMF278B device selected.

Audio comparison with the Dawn of Sorrow KSP and the real YRW801 ROM must be
performed on the target system; the ROM is intentionally not distributed.
