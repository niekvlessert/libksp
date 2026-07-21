# Changelog

## 0.6

- Fix `zx_read_bit` corrupting register `B` while `BC` holds the active Elias-gamma value or copy length.
- Fix `print_u16` losing its decimal-buffer pointer and writing the track number into low memory near `0009h`.
- Add a chunked 512-byte ZX0 regression model covering the exact Nemesis 3 template and all 24 compressed overlays.
- Add build-time source checks preventing both register-corruption bugs from returning.
- Update the banner to `KSP1PLAY 0.6`.

## 0.5

- Preserve `BC`, `DE`, and `HL` across DOS/mapper input-buffer refills in the streaming ZX0 decoder.
- Add stage-specific template, sparse, complete-page, and hybrid decoding errors.
- Stop DOS text output before non-ASCII UTF-8 bytes to prevent console control garbage.

## 0.4

- Preserve uppercase quoted character literals in the bundled assembler.
- Validate and package the exact uploaded Nemesis 3 KSP.
