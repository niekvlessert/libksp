# KSP1PLAY 0.12D page CRC diagnostic

This build calculates IEEE CRC32 over CPU memory `4000h-7FFFh` after the KSP
page has been reconstructed and before INIT is called. It compares that value
with the final-page CRC stored in the KSP page table.

Output:

```text
CRC E=727ABE9F A=727ABE9F OK
```

- `E` is the expected KSP page CRC.
- `A` is the actual CRC calculated on the MSX.
- `OK` proves the reconstructed page is byte-exact.
- `!!` proves corruption in caching, ZX0 decoding, template copying, or sparse
  overlay application.

Relevant Nemesis 3 expected values:

```text
track 3   E77AC8BD
track 7   727ABE9F
track 8   82AD9BCC
track 11  C33C382E
track 12  6980BE8B
```

Run, for example:

```text
KSP1PLAY NEMESIS3.KSP 7 2
```
