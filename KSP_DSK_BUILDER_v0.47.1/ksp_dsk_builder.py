#!/usr/bin/env python3
"""Build a 720 KB KSP1PLAY DSK from all .KSP files in a directory.

Default template: KSP1PLAY_v0.47.1_BASE.DSK next to this script.
The template contains the latest stable normal KSP1PLAY player core (v0.47.0;
package baseline v0.47.1).

Usage:
    python3 ksp_dsk_builder.py /path/to/ksps -o MYKSP.DSK
    python3 ksp_dsk_builder.py /path/to/ksps -o MYKSP.DSK --recursive
    python3 ksp_dsk_builder.py /path/to/ksps -o MYKSP.DSK --title-map INDEX.TXT
    python3 ksp_dsk_builder.py /path/to/ksps -o MYKSP.DSK --template OTHER_BASE.DSK
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

PACKAGE_VERSION = "0.47.1"
PLAYER_CORE_VERSION = "0.47.0"
DEFAULT_TEMPLATE_NAME = "KSP1PLAY_v0.47.1_BASE.DSK"
REQUIRED_PLAYER_FILES = ("KSPBOOT.BIN", "KSP1PLAY.COM", "KSPMENU.BIN")


def ascii_clean(text: str) -> str:
    """Convert display text to conservative printable ASCII for SCREEN 0 UI."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
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


def safe_83_ksp_name(source: Path, used: set[str]) -> str:
    stem = unicodedata.normalize("NFKD", source.stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9_]", "", stem).upper()
    if not stem:
        stem = "KSP"
    candidate = stem[:8] + ".KSP"
    if candidate not in used:
        used.add(candidate)
        return candidate
    for n in range(1, 100):
        suffix = f"~{n}"
        base = stem[: 8 - len(suffix)] + suffix
        candidate = base + ".KSP"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise ValueError(f"too many 8.3 filename collisions for {source.name}")


def parse_title_map(path: Optional[Path]) -> Dict[str, str]:
    if path is None or not path.exists():
        return {}
    result: Dict[str, str] = {}
    for raw in path.read_bytes().splitlines():
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        left, right = line.split("|", 1)
        key = left.strip().upper()
        title = ascii_clean(right)
        if key and title:
            result[key] = title
            result[Path(key).stem.upper()] = title
    return result


def extract_ksp_title(data: bytes) -> Optional[str]:
    """Best-effort top-level title extraction from KSP1 META.

    META can be stored packed. Current KSP packers often leave the early
    title= line literal even when the rest is compressed, so the raw payload
    is also searched. The function deliberately falls back instead of trying
    to implement every KSP resource codec.
    """
    if len(data) < 0x50 or data[:4] != b"KSP1":
        return None
    try:
        res_off = struct.unpack_from("<I", data, 0x28)[0]
        res_cnt = struct.unpack_from("<H", data, 0x2C)[0]
        res_size = struct.unpack_from("<H", data, 0x2E)[0]
    except struct.error:
        return None
    if not (24 <= res_size <= 128):
        return None
    candidates: List[bytes] = []
    for i in range(res_cnt):
        e = res_off + i * res_size
        if e + 20 > len(data):
            break
        if data[e:e+4] != b"META":
            continue
        off = struct.unpack_from("<I", data, e + 8)[0]
        packed = struct.unpack_from("<I", data, e + 12)[0]
        if 0 <= off < len(data) and 0 < packed <= len(data) - off:
            candidates.append(data[off:off+packed])
    # As a final fallback, scanning the full KSP is harmless and covers old packs.
    candidates.append(data)
    for payload in candidates:
        for key in (b"title=", b"game="):
            pos = payload.find(key)
            if pos < 0:
                continue
            start = pos + len(key)
            end = payload.find(b"\n", start, min(len(payload), start + 256))
            if end < 0:
                end = min(len(payload), start + 128)
            raw = payload[start:end].split(b"\r", 1)[0]
            # Packed META can contain a partially literal but already corrupted
            # title line. Accept the line only when the WHOLE value up to the
            # newline is printable ASCII; otherwise fall back to another key or
            # ultimately to the filename / INDEX.TXT override.
            if not raw or any(not (c == 9 or 32 <= c <= 126) for c in raw):
                continue
            title = ascii_clean(raw.decode("ascii", "strict"))
            if title:
                return title
    return None


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
            raise ValueError("DSK is too small")
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
        if self.bps != 512 or self.cluster_count >= 4085:
            raise ValueError("template is not a supported FAT12 image")
        expected = self.total_sectors * self.bps
        if len(self.data) != expected:
            raise ValueError(f"DSK size mismatch: header says {expected}, file is {len(self.data)}")

    def fat_get(self, n: int) -> int:
        o = self.fat_off + n + n // 2
        if n & 1:
            return ((self.data[o] >> 4) | (self.data[o+1] << 4)) & 0xFFF
        return (self.data[o] | ((self.data[o+1] & 0x0F) << 8)) & 0xFFF

    def _fat_set_one(self, fat_base: int, n: int, value: int) -> None:
        value &= 0xFFF
        o = fat_base + n + n // 2
        if n & 1:
            self.data[o] = (self.data[o] & 0x0F) | ((value & 0x0F) << 4)
            self.data[o+1] = (value >> 4) & 0xFF
        else:
            self.data[o] = value & 0xFF
            self.data[o+1] = (self.data[o+1] & 0xF0) | ((value >> 8) & 0x0F)

    def fat_set(self, n: int, value: int) -> None:
        for f in range(self.fat_count):
            self._fat_set_one(self.fat_off + f * self.spf * self.bps, n, value)

    def root(self) -> List[RootEntry]:
        out: List[RootEntry] = []
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
        for e in self.root():
            if e.name.upper() == target:
                return e
        return None

    def chain(self, first: int) -> List[int]:
        if first < 2:
            return []
        result: List[int] = []
        c = first
        seen = set()
        while 2 <= c < 0xFF8:
            if c in seen or c > self.cluster_count + 1:
                raise ValueError("corrupt FAT chain")
            seen.add(c)
            result.append(c)
            c = self.fat_get(c)
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
        ro = self.root_off + e.index * 32
        self.data[ro] = 0xE5
        return True

    def _free_root_index(self) -> int:
        for i in range(self.root_entries):
            off = self.root_off + i * 32
            if self.data[off] in (0x00, 0xE5):
                return i
        raise ValueError("root directory is full")

    def _free_clusters(self, count: int) -> List[int]:
        free = [c for c in range(2, self.cluster_count + 2) if self.fat_get(c) == 0]
        if len(free) < count:
            available = len(free) * self.cluster_bytes
            needed = count * self.cluster_bytes
            raise ValueError(f"disk full: need {needed} bytes of clusters, only {available} bytes free")
        return free[:count]

    def add_file(self, name: str, payload: bytes, attr: int = 0x20) -> None:
        raw_name = encode_83(name)
        self.delete_file(name)
        idx = self._free_root_index()
        nclusters = (len(payload) + self.cluster_bytes - 1) // self.cluster_bytes
        clusters = self._free_clusters(nclusters) if nclusters else []
        for i, c in enumerate(clusters):
            self.fat_set(c, 0xFFF if i == len(clusters) - 1 else clusters[i+1])
            off = self.data_off + (c - 2) * self.cluster_bytes
            chunk = payload[i*self.cluster_bytes:(i+1)*self.cluster_bytes]
            self.data[off:off+self.cluster_bytes] = chunk.ljust(self.cluster_bytes, b"\0")
        ro = self.root_off + idx * 32
        entry = bytearray(32)
        entry[:11] = raw_name
        entry[11] = attr & 0xFF
        struct.pack_into("<H", entry, 26, clusters[0] if clusters else 0)
        struct.pack_into("<I", entry, 28, len(payload))
        self.data[ro:ro+32] = entry
        # If we consumed a never-used (00) slot, ensure the next one remains an end marker.
        if idx + 1 < self.root_entries:
            nxt = self.root_off + (idx + 1) * 32
            if self.data[nxt] == 0x00:
                self.data[nxt:nxt+32] = b"\0" * 32

    def replace_file(self, name: str, payload: bytes, attr: Optional[int] = None) -> None:
        old = self.find(name)
        old_attr = old.attr if old else 0x20
        self.add_file(name, payload, old_attr if attr is None else attr)

    def free_bytes(self) -> int:
        return sum(1 for c in range(2, self.cluster_count + 2) if self.fat_get(c) == 0) * self.cluster_bytes

    def validate_mirrored_fats(self) -> None:
        first = bytes(self.data[self.fat_off:self.fat_off+self.spf*self.bps])
        for f in range(1, self.fat_count):
            off = self.fat_off + f*self.spf*self.bps
            if bytes(self.data[off:off+self.spf*self.bps]) != first:
                raise ValueError("FAT copies differ")


def make_index_line(dos_name: str, title: str) -> bytes:
    name = dos_name.upper()[:12].ljust(12)
    title = ascii_clean(title)[:65].ljust(65)
    record = (name + "|" + title + "\r\n").encode("ascii")
    if len(record) != 80:
        raise AssertionError("INDEX.TXT record must be exactly 80 bytes")
    return record


def choose_title(path: Path, data: bytes, title_map: Dict[str, str]) -> str:
    for key in (path.name.upper(), path.stem.upper()):
        if key in title_map:
            return title_map[key]
    return extract_ksp_title(data) or ascii_clean(path.stem.replace("_", " ")) or "Untitled KSP"


def build(args: argparse.Namespace) -> Tuple[Path, List[Tuple[Path, str, str]]]:
    src = args.ksp_directory.resolve()
    if not src.is_dir():
        raise ValueError(f"not a directory: {src}")
    template = args.template.resolve()
    if not template.is_file():
        raise ValueError(f"template not found: {template}")

    candidates = src.rglob("*") if args.recursive else src.iterdir()
    ksps = sorted((p for p in candidates if p.is_file() and p.suffix.lower() == ".ksp"), key=lambda p: str(p).lower())
    if not ksps:
        raise ValueError(f"no .ksp files found in {src}")

    title_map_path = args.title_map
    if title_map_path is None:
        auto = next((p for p in src.iterdir() if p.is_file() and p.name.upper() == "INDEX.TXT"), None)
        if auto is not None:
            title_map_path = auto
    title_map = parse_title_map(title_map_path)

    image = Fat12Image(template.read_bytes())
    for req in REQUIRED_PLAYER_FILES:
        if image.find(req) is None:
            raise ValueError(f"template is missing required player file {req}")

    # A template may itself be a populated release DSK. Strip catalog content,
    # but never touch the three player files.
    for e in list(image.root()):
        if e.name.upper().endswith(".KSP") or e.name.upper() in ("INDEX.TXT", "README.TXT"):
            image.delete_file(e.name)

    used = {e.name.upper() for e in image.root()}
    catalog: List[Tuple[Path, str, str]] = []
    for p in ksps:
        data = p.read_bytes()
        if len(data) < 4 or data[:4] != b"KSP1":
            if args.skip_invalid:
                print(f"warning: skipping invalid KSP: {p}", file=sys.stderr)
                continue
            raise ValueError(f"invalid KSP1 file: {p}")
        dos_name = safe_83_ksp_name(p, used)
        title = choose_title(p, data, title_map)
        image.add_file(dos_name, data)
        catalog.append((p, dos_name, title))

    if not catalog:
        raise ValueError("no valid KSP files to add")

    index = b"".join(make_index_line(dos, title) for _, dos, title in catalog)
    image.add_file("INDEX.TXT", index, attr=0x00)

    readme_lines = [
        f"KSP1PLAY custom disk builder package {PACKAGE_VERSION}",
        f"Player core: {PLAYER_CORE_VERSION}",
        "",
        f"Games/packs: {len(catalog)}",
        "Generated by ksp_dsk_builder.py.",
        "INDEX.TXT uses fixed 80-byte records.",
        "",
    ]
    for _, dos, title in catalog:
        readme_lines.append(f"{dos} - {ascii_clean(title)}")
    readme = ("\r\n".join(readme_lines) + "\r\n").encode("ascii", "replace")
    image.add_file("README.TXT", readme)

    image.validate_mirrored_fats()
    out = args.output.resolve()
    if out.exists() and not args.force:
        raise ValueError(f"output already exists (use --force): {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image.data)
    return out, catalog


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Create a 720 KB KSP1PLAY DSK from all .KSP files in a directory.")
    parser.add_argument("ksp_directory", type=Path, help="directory containing .KSP files")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output .DSK path")
    parser.add_argument("--template", type=Path, default=script_dir / DEFAULT_TEMPLATE_NAME,
                        help=f"base player DSK (default: {DEFAULT_TEMPLATE_NAME} next to the script)")
    parser.add_argument("--title-map", type=Path, help="INDEX.TXT-style filename|title overrides")
    parser.add_argument("--recursive", action="store_true", help="also include .KSP files from subdirectories")
    parser.add_argument("--skip-invalid", action="store_true", help="skip files with .ksp extension that are not KSP1")
    parser.add_argument("-f", "--force", action="store_true", help="overwrite output if it already exists")
    args = parser.parse_args()
    try:
        out, catalog = build(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Created: {out}")
    print(f"KSP files: {len(catalog)}")
    for src, dos, title in catalog:
        print(f"  {src.name} -> {dos:12} | {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
