# KSP1PLAY 0.9D startup trace

Run:

```text
KSP1DBG NEMESIS3.KSP 0 2
```

Send a photograph showing the **last `DBG xx` line** that appears.

| Code | Last completed operation |
|---|---|
| `01` | Banner written |
| `10` | KSP file opened |
| `11` | DOS2 mapper API found and original pages captured |
| `12` | 80-byte KSP header read |
| `13` | Header, engine and MSX profile validated |
| `20` | Starting complete-file preload into upper VRAM |
| `A1` | First 8 KiB copied to VRAM |
| `A2` | First 16 KiB copied to VRAM |
| `A3` | First 24 KiB copied to VRAM |
| `A4` | First 32 KiB copied to VRAM |
| `21` | Complete KSP file cached in VRAM |
| `22` | Mapper template segment allocated; about to decode engine template from VRAM |
| `23` | Engine template decoded into mapper RAM |
| `50` | Starting public-track lookup |
| `51` | Track and page descriptors loaded |
| `52` | Title displayed; starting page reconstruction and INIT |
| `53` | Runtime page installed and INIT completed |
| `E1` | VRAM file cache failed; disk fallback selected |
| `E2` | Template mapper allocation failed; disk fallback selected |

Interpretation:

- Stops before `A1`: problem is in the first DOS-read/VRAM-write cycle.
- Stops after one of `A1`–`A4`: problem is later in file-to-VRAM transfer.
- Stops at `22`: problem is decoding the common ZX0 template from cached VRAM.
- Stops at `52`: problem is selected-overlay reconstruction, SCC remapping, or INIT.
- Reaches `53` but remains silent: startup succeeded; debug PLAY/interrupt/SCC slot handling next.
