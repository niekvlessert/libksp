from __future__ import annotations

import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

TEMPLATE_NAME = "KSP1PLAY_v0.47.1_BASE.DSK"
EXPECTED_PLAYER_CORE = "0.47.0"
EXPECTED_BUILDER = "0.47.1"
REQUIRED_PLAYER_FILES = ("KSPBOOT.BIN", "KSP1PLAY.COM", "KSPMENU.BIN")


def ascii_clean(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def decode_83(raw: bytes) -> str:
    base = raw[:8].decode("ascii", "replace").rstrip()
    ext = raw[8:11].decode("ascii", "replace").rstrip()
    return base + (("." + ext) if ext else "")


def encode_83(name: str) -> bytes:
    name = name.upper()
    if name.count(".") > 1:
        raise ValueError(f"not an 8.3 filename: {name}")
    if "." in name:
        base, ext = name.rsplit(".", 1)
    else:
        base, ext = name, ""
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$%'-@~`!(){}^#&"
    if not (1 <= len(base) <= 8 and len(ext) <= 3):
        raise ValueError(f"not an 8.3 filename: {name}")
    if any(ch not in allowed for ch in base + ext):
        raise ValueError(f"unsupported DOS filename character in: {name}")
    return base.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")


def safe_83_ksp_name(stem: str, used: set[str]) -> str:
    raw = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"[^A-Za-z0-9_]", "", raw).upper() or "KSP"
    candidate = raw[:8] + ".KSP"
    if candidate not in used:
        used.add(candidate)
        return candidate
    for n in range(1, 100):
        suffix = f"~{n}"
        candidate = raw[:8-len(suffix)] + suffix + ".KSP"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise ValueError("too many 8.3 filename collisions")


@dataclass
class RootEntry:
    index: int
    name: str
    attr: int
    cluster: int
    size: int


class Fat12Image:
    def __init__(self, raw: bytes):
        self.data = bytearray(raw)
        if len(self.data) < 512:
            raise ValueError("DSK template is too small")
        self.bps = struct.unpack_from("<H", self.data, 11)[0]
        self.spc = self.data[13]
        self.reserved = struct.unpack_from("<H", self.data, 14)[0]
        self.fat_count = self.data[16]
        self.root_entries = struct.unpack_from("<H", self.data, 17)[0]
        total16 = struct.unpack_from("<H", self.data, 19)[0]
        total32 = struct.unpack_from("<I", self.data, 32)[0]
        self.total_sectors = total16 or total32
        self.spf = struct.unpack_from("<H", self.data, 22)[0]
        self.root_sectors = (self.root_entries * 32 + self.bps - 1) // self.bps
        self.fat_off = self.reserved * self.bps
        self.root_off = (self.reserved + self.fat_count * self.spf) * self.bps
        self.data_off = (self.reserved + self.fat_count * self.spf + self.root_sectors) * self.bps
        self.cluster_bytes = self.spc * self.bps
        data_sectors = self.total_sectors - (self.reserved + self.fat_count * self.spf + self.root_sectors)
        self.cluster_count = data_sectors // self.spc
        if self.bps != 512 or not self.spc or self.cluster_count >= 4085:
            raise ValueError("template is not a supported FAT12 DSK")
        expected = self.total_sectors * self.bps
        if len(self.data) != expected:
            raise ValueError(f"DSK size mismatch: BPB says {expected}, actual {len(self.data)}")

    def fat_get(self, n: int) -> int:
        o = self.fat_off + n + n // 2
        if n & 1:
            return ((self.data[o] >> 4) | (self.data[o+1] << 4)) & 0xFFF
        return (self.data[o] | ((self.data[o+1] & 0x0F) << 8)) & 0xFFF

    def _fat_set_one(self, base: int, n: int, value: int) -> None:
        value &= 0xFFF
        o = base + n + n // 2
        if n & 1:
            self.data[o] = (self.data[o] & 0x0F) | ((value & 0x0F) << 4)
            self.data[o+1] = (value >> 4) & 0xFF
        else:
            self.data[o] = value & 0xFF
            self.data[o+1] = (self.data[o+1] & 0xF0) | ((value >> 8) & 0x0F)

    def fat_set(self, n: int, value: int) -> None:
        for f in range(self.fat_count):
            self._fat_set_one(self.fat_off + f * self.spf * self.bps, n, value)

    def root(self) -> list[RootEntry]:
        out: list[RootEntry] = []
        for i in range(self.root_entries):
            off = self.root_off + i * 32
            e = self.data[off:off+32]
            if e[0] == 0x00:
                break
            if e[0] == 0xE5 or e[11] == 0x0F:
                continue
            out.append(RootEntry(i, decode_83(e[:11]), e[11], struct.unpack_from("<H", e, 26)[0], struct.unpack_from("<I", e, 28)[0]))
        return out

    def find(self, name: str) -> Optional[RootEntry]:
        target = name.upper()
        return next((e for e in self.root() if e.name.upper() == target), None)

    def chain(self, first: int) -> list[int]:
        if first < 2:
            return []
        result: list[int] = []
        c = first
        seen: set[int] = set()
        while 2 <= c < 0xFF8:
            if c in seen or c > self.cluster_count + 1:
                raise ValueError("corrupt FAT chain")
            seen.add(c); result.append(c); c = self.fat_get(c)
        return result

    def read_file(self, name: str) -> bytes:
        e = self.find(name)
        if e is None:
            raise FileNotFoundError(name)
        out = bytearray()
        for c in self.chain(e.cluster):
            off = self.data_off + (c - 2) * self.cluster_bytes
            out += self.data[off:off+self.cluster_bytes]
        return bytes(out[:e.size])

    def delete_file(self, name: str) -> bool:
        e = self.find(name)
        if e is None:
            return False
        for c in self.chain(e.cluster):
            self.fat_set(c, 0)
            off = self.data_off + (c - 2) * self.cluster_bytes
            self.data[off:off+self.cluster_bytes] = b"\0" * self.cluster_bytes
        self.data[self.root_off + e.index * 32] = 0xE5
        return True

    def _free_root_index(self) -> int:
        for i in range(self.root_entries):
            if self.data[self.root_off + i * 32] in (0x00, 0xE5):
                return i
        raise ValueError("root directory is full")

    def _free_clusters(self, count: int) -> list[int]:
        free = [c for c in range(2, self.cluster_count + 2) if self.fat_get(c) == 0]
        if len(free) < count:
            raise ValueError(f"disk full: need {count*self.cluster_bytes} bytes, only {len(free)*self.cluster_bytes} free")
        return free[:count]

    def add_file(self, name: str, payload: bytes, attr: int = 0x20) -> None:
        raw_name = encode_83(name)
        self.delete_file(name)
        idx = self._free_root_index()
        nclusters = (len(payload) + self.cluster_bytes - 1) // self.cluster_bytes
        clusters = self._free_clusters(nclusters) if nclusters else []
        for i, c in enumerate(clusters):
            self.fat_set(c, 0xFFF if i == len(clusters)-1 else clusters[i+1])
            off = self.data_off + (c - 2) * self.cluster_bytes
            chunk = payload[i*self.cluster_bytes:(i+1)*self.cluster_bytes]
            self.data[off:off+self.cluster_bytes] = chunk.ljust(self.cluster_bytes, b"\0")
        ro = self.root_off + idx * 32
        entry = bytearray(32); entry[:11] = raw_name; entry[11] = attr & 0xFF
        struct.pack_into("<H", entry, 26, clusters[0] if clusters else 0)
        struct.pack_into("<I", entry, 28, len(payload))
        self.data[ro:ro+32] = entry

    def validate_mirrored_fats(self) -> None:
        first = bytes(self.data[self.fat_off:self.fat_off+self.spf*self.bps])
        for f in range(1, self.fat_count):
            off = self.fat_off + f * self.spf * self.bps
            if bytes(self.data[off:off+self.spf*self.bps]) != first:
                raise ValueError("FAT copies differ")


def make_index_line(dos_name: str, title: str) -> bytes:
    name = dos_name.upper()[:12].ljust(12)
    title = ascii_clean(title)[:65].ljust(65)
    rec = (name + "|" + title + "\r\n").encode("ascii")
    if len(rec) != 80:
        raise AssertionError("INDEX record must be 80 bytes")
    return rec


def load_template(path: Path) -> tuple[bytes, str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            matches = [n for n in zf.namelist() if Path(n).name.upper() == TEMPLATE_NAME.upper()]
            if not matches:
                raise ValueError(f"{path.name} does not contain {TEMPLATE_NAME}")
            return zf.read(matches[0]), f"{path}!{matches[0]}"
    return path.read_bytes(), str(path)


def locate_latest_template(tool_dir: Path, explicit: Optional[Path] = None) -> tuple[bytes, str]:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    else:
        candidates.extend([tool_dir / "player" / TEMPLATE_NAME, tool_dir / TEMPLATE_NAME])
        candidates.extend(sorted((tool_dir / "player").glob("KSP_DSK_BUILDER_v0.47.1*.zip")) if (tool_dir/"player").exists() else [])
        candidates.extend(sorted(tool_dir.glob("KSP_DSK_BUILDER_v0.47.1*.zip")))
    for p in candidates:
        if p.is_file():
            raw, source = load_template(p)
            verify_latest_template(raw, source)
            return raw, source
    where = tool_dir / "player" / TEMPLATE_NAME
    raise FileNotFoundError(
        f"latest KSP1PLAY template not found. Need {TEMPLATE_NAME} (DSK Builder {EXPECTED_BUILDER}, player core {EXPECTED_PLAYER_CORE}) "
        f"in {where} or pass --player-template <DSK-or-v0.47.1-ZIP>"
    )


def verify_latest_template(raw: bytes, source: str = "template") -> None:
    image = Fat12Image(raw)
    for req in REQUIRED_PLAYER_FILES:
        if image.find(req) is None:
            raise ValueError(f"{source}: missing required latest-player file {req}")
    com = image.read_file("KSP1PLAY.COM")
    if EXPECTED_PLAYER_CORE.encode("ascii") not in com:
        raise ValueError(
            f"{source}: KSP1PLAY.COM does not identify core {EXPECTED_PLAYER_CORE}; refusing to build with an older/unknown player"
        )


def build_single_ksp_disk(template_raw: bytes, ksp_data: bytes, source_name: str, title: str, output: Path) -> dict:
    verify_latest_template(template_raw)
    image = Fat12Image(template_raw)
    # Strip any catalog payload from a populated template but preserve player/runtime files.
    for e in list(image.root()):
        if e.name.upper().endswith(".KSP") or e.name.upper() in ("INDEX.TXT", "README.TXT"):
            image.delete_file(e.name)
    used = {e.name.upper() for e in image.root()}
    dos_name = safe_83_ksp_name(Path(source_name).stem, used)
    image.add_file(dos_name, ksp_data)
    image.add_file("INDEX.TXT", make_index_line(dos_name, title), attr=0x00)
    readme = (
        f"KSP1PLAY analyser test disk\r\n"
        f"Player core: {EXPECTED_PLAYER_CORE}\r\n"
        f"DSK builder baseline: {EXPECTED_BUILDER}\r\n"
        f"{dos_name} - {ascii_clean(title)}\r\n"
    ).encode("ascii", "replace")
    image.add_file("README.TXT", readme)
    image.validate_mirrored_fats()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image.data)
    # Read back the inserted file through FAT to catch malformed allocation/catalog edits.
    verify = Fat12Image(output.read_bytes())
    if verify.read_file(dos_name) != ksp_data:
        raise ValueError("post-build DSK verification failed: inserted KSP differs")
    return {"output": str(output), "dos_name": dos_name, "title": title, "bytes": len(image.data),
            "player_core": EXPECTED_PLAYER_CORE, "builder_baseline": EXPECTED_BUILDER}
