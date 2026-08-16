#!/usr/bin/env python3
"""Build a bootable KSPOS FAT12 DSK from a directory or ZIP archive.

No third-party modules are required. The bundled default boot sector belongs to
KSP1PLAY/KSPOS v0.22.28 and must be used with its matching KSPBOOT.BIN.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

DEFAULT_BOOT_NAME = "KSPOS_BOOTSECTOR_v0.22.28.bin"
DEFAULT_KSPBOOT_SHA256 = "03a87eaed20844003cfa5840832355e56fb8e2e4dc72685e368b6c142f2d4ff0"
DEFAULT_KSPBOOT_SIZE = 31672
IGNORED_NAMES = {".DS_STORE", "THUMBS.DB", "DESKTOP.INI"}
VALID_83_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$~!#%&-{}()@'`")


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class Geometry:
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    root_entries: int
    total_sectors: int
    sectors_per_fat: int
    media_descriptor: int

    @property
    def root_sectors(self) -> int:
        return (self.root_entries * 32 + self.bytes_per_sector - 1) // self.bytes_per_sector

    @property
    def fat1_sector(self) -> int:
        return self.reserved_sectors

    @property
    def root_sector(self) -> int:
        return self.reserved_sectors + self.fat_count * self.sectors_per_fat

    @property
    def data_sector(self) -> int:
        return self.root_sector + self.root_sectors

    @property
    def data_sectors(self) -> int:
        return self.total_sectors - self.data_sector

    @property
    def cluster_bytes(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def cluster_count(self) -> int:
        return self.data_sectors // self.sectors_per_cluster

    @property
    def image_bytes(self) -> int:
        return self.total_sectors * self.bytes_per_sector


@dataclass
class InputFile:
    source_name: str
    disk_name: str
    data: bytes
    timestamp: datetime


def parse_geometry(boot_sector: bytes) -> Geometry:
    if len(boot_sector) != 512:
        raise BuildError(f"boot sector must be exactly 512 bytes, got {len(boot_sector)}")
    if boot_sector[510:512] != b"\x55\xAA":
        raise BuildError("boot sector has no 55 AA signature")

    bps = struct.unpack_from("<H", boot_sector, 11)[0]
    spc = boot_sector[13]
    reserved = struct.unpack_from("<H", boot_sector, 14)[0]
    fats = boot_sector[16]
    root_entries = struct.unpack_from("<H", boot_sector, 17)[0]
    total16 = struct.unpack_from("<H", boot_sector, 19)[0]
    media = boot_sector[21]
    spf = struct.unpack_from("<H", boot_sector, 22)[0]
    total32 = struct.unpack_from("<I", boot_sector, 32)[0]
    total = total16 or total32

    if bps != 512:
        raise BuildError(f"only 512-byte sectors are supported, boot sector says {bps}")
    if not spc or spc & (spc - 1):
        raise BuildError(f"invalid sectors-per-cluster value: {spc}")
    if not reserved or not fats or not root_entries or not total or not spf:
        raise BuildError("boot sector contains an incomplete FAT12 BPB")

    geom = Geometry(bps, spc, reserved, fats, root_entries, total, spf, media)
    if geom.cluster_count >= 4085:
        raise BuildError("the supplied geometry is not FAT12")
    if geom.data_sector >= geom.total_sectors:
        raise BuildError("invalid FAT geometry: data area starts beyond end of image")
    return geom


def normalize_83(name: str) -> str:
    raw = name.strip().upper()
    if raw in {".", "..", ""}:
        raise BuildError(f"invalid filename: {name!r}")
    if raw.count(".") > 1:
        raise BuildError(f"not an 8.3 filename: {name}")
    stem, dot, ext = raw.partition(".")
    if not stem or len(stem) > 8 or len(ext) > 3:
        raise BuildError(f"not an 8.3 filename: {name}")
    bad = sorted({c for c in stem + ext if c not in VALID_83_CHARS})
    if bad:
        raise BuildError(f"filename {name!r} contains unsupported character(s): {''.join(bad)}")
    return stem + (("." + ext) if dot else "")


def short_name_bytes(name: str) -> bytes:
    valid = normalize_83(name)
    stem, dot, ext = valid.partition(".")
    return stem.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")


def dos_datetime(dt: datetime) -> tuple[int, int]:
    year = min(2107, max(1980, dt.year))
    month = min(12, max(1, dt.month))
    day = min(31, max(1, dt.day))
    hour = min(23, max(0, dt.hour))
    minute = min(59, max(0, dt.minute))
    second = min(59, max(0, dt.second))
    date = ((year - 1980) << 9) | (month << 5) | day
    time = (hour << 11) | (minute << 5) | (second // 2)
    return date, time


def should_ignore(name: str, include_hidden: bool) -> bool:
    upper = name.upper()
    if upper in IGNORED_NAMES or upper.startswith("._"):
        return True
    return not include_hidden and name.startswith(".")


def load_directory(path: Path, include_hidden: bool) -> list[InputFile]:
    if not path.is_dir():
        raise BuildError(f"input directory does not exist: {path}")
    out: list[InputFile] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.upper()):
        if should_ignore(child.name, include_hidden):
            continue
        if child.is_dir():
            raise BuildError(
                f"subdirectories are not supported by this builder: {child.name}\n"
                "Put all KSPOS files directly in the input directory."
            )
        if not child.is_file():
            continue
        stat = child.stat()
        out.append(InputFile(child.name, normalize_83(child.name), child.read_bytes(), datetime.fromtimestamp(stat.st_mtime)))
    return out


def common_zip_prefix(infos: list[zipfile.ZipInfo]) -> str:
    parts = [PurePosixPath(i.filename).parts for i in infos if not i.is_dir()]
    if not parts:
        return ""
    first = parts[0][0] if len(parts[0]) > 1 else ""
    if first and all(len(p) > 1 and p[0] == first for p in parts):
        return first + "/"
    return ""


def load_zip(path: Path, include_hidden: bool) -> list[InputFile]:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise BuildError(f"invalid ZIP archive: {path}") from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX/")]
        prefix = common_zip_prefix(infos)
        out: list[InputFile] = []
        for info in infos:
            relative = info.filename[len(prefix):] if prefix and info.filename.startswith(prefix) else info.filename
            pure = PurePosixPath(relative)
            if len(pure.parts) != 1:
                raise BuildError(
                    f"ZIP contains a subdirectory entry: {info.filename}\n"
                    "The archive may have one common top-level folder, but no folders below it."
                )
            name = pure.name
            if should_ignore(name, include_hidden):
                continue
            try:
                dt = datetime(*info.date_time)
            except (TypeError, ValueError):
                dt = datetime(2026, 1, 1, 12, 0, 0)
            out.append(InputFile(info.filename, normalize_83(name), zf.read(info), dt))
        return out


def load_input(path: Path, include_hidden: bool) -> list[InputFile]:
    if path.is_dir():
        files = load_directory(path, include_hidden)
    elif path.is_file() and path.suffix.lower() == ".zip":
        files = load_zip(path, include_hidden)
    else:
        raise BuildError("input must be a directory or a .zip file")
    if not files:
        raise BuildError("input contains no usable files")

    seen: dict[str, str] = {}
    for item in files:
        key = item.disk_name.upper()
        if key in seen:
            raise BuildError(f"duplicate 8.3 filename after uppercasing: {seen[key]!r} and {item.source_name!r}")
        seen[key] = item.source_name

    priority = {"KSPBOOT.BIN": 0, "KSP1PLAY.COM": 1, "INDEX.TXT": 2, "README.TXT": 3}
    files.sort(key=lambda f: (priority.get(f.disk_name, 10), f.disk_name))
    return files


def set_fat12(fat: bytearray, cluster: int, value: int) -> None:
    offset = cluster + cluster // 2
    if offset + 1 >= len(fat):
        raise BuildError("FAT12 table is too small for allocated clusters")
    value &= 0xFFF
    if cluster & 1:
        fat[offset] = (fat[offset] & 0x0F) | ((value << 4) & 0xF0)
        fat[offset + 1] = (value >> 4) & 0xFF
    else:
        fat[offset] = value & 0xFF
        fat[offset + 1] = (fat[offset + 1] & 0xF0) | ((value >> 8) & 0x0F)


def get_fat12(fat: bytes, cluster: int) -> int:
    offset = cluster + cluster // 2
    if offset + 1 >= len(fat):
        raise BuildError("FAT chain points outside FAT")
    word = fat[offset] | (fat[offset + 1] << 8)
    return ((word >> 4) if cluster & 1 else word) & 0xFFF


def extract_root_file(image: bytes, wanted: str) -> bytes | None:
    if len(image) < 512:
        return None
    geom = parse_geometry(image[:512])
    if len(image) < geom.image_bytes:
        raise BuildError("template DSK is shorter than its BPB geometry")
    root_off = geom.root_sector * geom.bytes_per_sector
    fat_off = geom.fat1_sector * geom.bytes_per_sector
    fat_len = geom.sectors_per_fat * geom.bytes_per_sector
    fat = image[fat_off:fat_off + fat_len]
    target = short_name_bytes(wanted)

    for n in range(geom.root_entries):
        off = root_off + n * 32
        entry = image[off:off + 32]
        if not entry or entry[0] == 0x00:
            break
        if entry[0] == 0xE5 or entry[11] & 0x18:
            continue
        if entry[:11] != target:
            continue
        cluster = struct.unpack_from("<H", entry, 26)[0]
        size = struct.unpack_from("<I", entry, 28)[0]
        if size == 0:
            return b""
        out = bytearray()
        visited: set[int] = set()
        while 2 <= cluster < 0xFF8 and len(out) < size:
            if cluster in visited:
                raise BuildError("template DSK contains a FAT loop")
            visited.add(cluster)
            if cluster >= geom.cluster_count + 2:
                raise BuildError("template DSK FAT chain points outside data area")
            data_sector = geom.data_sector + (cluster - 2) * geom.sectors_per_cluster
            data_off = data_sector * geom.bytes_per_sector
            out += image[data_off:data_off + geom.cluster_bytes]
            cluster = get_fat12(fat, cluster)
        if len(out) < size:
            raise BuildError("template DSK contains a truncated KSPBOOT.BIN chain")
        return bytes(out[:size])
    return None


def load_boot_sector(args: argparse.Namespace, source_files: list[InputFile]) -> tuple[bytes, str | None]:
    script_dir = Path(__file__).resolve().parent
    reference_hash: str | None = None

    if args.template_dsk:
        template = args.template_dsk.read_bytes()
        if len(template) < 512:
            raise BuildError("template DSK is shorter than one sector")
        boot = template[:512]
        reference = extract_root_file(template, "KSPBOOT.BIN")
        if reference is None:
            raise BuildError("template DSK does not contain KSPBOOT.BIN")
        reference_hash = hashlib.sha256(reference).hexdigest()
    elif args.boot_sector:
        boot = args.boot_sector.read_bytes()
    else:
        boot_path = script_dir / DEFAULT_BOOT_NAME
        if not boot_path.is_file():
            raise BuildError(f"bundled boot sector is missing: {boot_path}")
        boot = boot_path.read_bytes()
        reference_hash = DEFAULT_KSPBOOT_SHA256

    parse_geometry(boot)

    kspboot = next((f for f in source_files if f.disk_name == "KSPBOOT.BIN"), None)
    if kspboot is None:
        raise BuildError("KSPBOOT.BIN is required for a bootable KSPOS disk")

    actual_hash = hashlib.sha256(kspboot.data).hexdigest()
    if reference_hash and actual_hash != reference_hash and not args.allow_mismatched_kspboot:
        raise BuildError(
            "KSPBOOT.BIN does not match the selected boot sector/template.\n"
            f"  selected reference SHA-256: {reference_hash}\n"
            f"  input KSPBOOT SHA-256:      {actual_hash}\n"
            "Use a DSK from the same player build with --template-dsk, or use\n"
            "--allow-mismatched-kspboot only when you know the boot code is compatible."
        )
    if not args.template_dsk and not args.boot_sector and len(kspboot.data) != DEFAULT_KSPBOOT_SIZE:
        raise BuildError(
            f"default v0.22.28 boot sector expects a {DEFAULT_KSPBOOT_SIZE}-byte KSPBOOT.BIN; "
            f"input has {len(kspboot.data)} bytes"
        )
    return boot, reference_hash


def build_image(files: list[InputFile], boot_sector: bytes) -> tuple[bytes, int, int]:
    geom = parse_geometry(boot_sector)
    if len(files) > geom.root_entries:
        raise BuildError(f"too many files: {len(files)}; root directory allows {geom.root_entries}")

    required_clusters = sum((len(f.data) + geom.cluster_bytes - 1) // geom.cluster_bytes for f in files if f.data)
    if required_clusters > geom.cluster_count:
        capacity = geom.cluster_count * geom.cluster_bytes
        payload = sum(len(f.data) for f in files)
        raise BuildError(
            f"files do not fit: {payload} bytes of file data needs {required_clusters} clusters; "
            f"disk has {geom.cluster_count} clusters ({capacity} bytes before cluster rounding)"
        )

    image = bytearray(geom.image_bytes)
    image[:512] = boot_sector
    fat = bytearray(geom.sectors_per_fat * geom.bytes_per_sector)
    fat[0] = geom.media_descriptor
    fat[1] = 0xFF
    fat[2] = 0xFF
    root = bytearray(geom.root_sectors * geom.bytes_per_sector)
    next_cluster = 2

    for index, item in enumerate(files):
        size = len(item.data)
        cluster_count = (size + geom.cluster_bytes - 1) // geom.cluster_bytes if size else 0
        first_cluster = next_cluster if cluster_count else 0

        for i in range(cluster_count):
            cluster = next_cluster + i
            set_fat12(fat, cluster, 0xFFF if i == cluster_count - 1 else cluster + 1)
            data_sector = geom.data_sector + (cluster - 2) * geom.sectors_per_cluster
            data_off = data_sector * geom.bytes_per_sector
            chunk = item.data[i * geom.cluster_bytes:(i + 1) * geom.cluster_bytes]
            image[data_off:data_off + len(chunk)] = chunk
        next_cluster += cluster_count

        entry_off = index * 32
        root[entry_off:entry_off + 11] = short_name_bytes(item.disk_name)
        root[entry_off + 11] = 0x20
        date, time = dos_datetime(item.timestamp)
        struct.pack_into("<H", root, entry_off + 22, time)
        struct.pack_into("<H", root, entry_off + 24, date)
        struct.pack_into("<H", root, entry_off + 26, first_cluster)
        struct.pack_into("<I", root, entry_off + 28, size)

    for fat_index in range(geom.fat_count):
        off = (geom.reserved_sectors + fat_index * geom.sectors_per_fat) * geom.bytes_per_sector
        image[off:off + len(fat)] = fat
    root_off = geom.root_sector * geom.bytes_per_sector
    image[root_off:root_off + len(root)] = root

    used_bytes = required_clusters * geom.cluster_bytes
    free_bytes = (geom.cluster_count - required_clusters) * geom.cluster_bytes
    return bytes(image), used_bytes, free_bytes


def print_manifest(files: Iterable[InputFile]) -> None:
    print("Files written:")
    for item in files:
        print(f"  {item.disk_name:<12} {len(item.data):>8} bytes")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a bootable KSPOS FAT12 DSK from a directory or ZIP archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 kspos_dsk_builder.py SHOVEL_DIR SHOVEL.DSK\n"
            "  python3 kspos_dsk_builder.py SHOVEL_FILES.zip SHOVEL.DSK\n"
            "  python3 kspos_dsk_builder.py NEW_DIR NEW.DSK --template-dsk KNOWN_GOOD.DSK\n"
        ),
    )
    parser.add_argument("source", type=Path, help="directory or ZIP containing KSPOS disk files")
    parser.add_argument("output", type=Path, help="output .DSK path")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--template-dsk", type=Path, help="take boot sector and KSPBOOT reference from a matching DSK")
    group.add_argument("--boot-sector", type=Path, help="use this raw 512-byte boot sector")
    parser.add_argument(
        "--allow-mismatched-kspboot",
        action="store_true",
        help="disable the KSPBOOT/boot-sector safety check (advanced and potentially unbootable)",
    )
    parser.add_argument("--include-hidden", action="store_true", help="include dotfiles except known OS metadata files")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.output.exists() and not args.force:
            raise BuildError(f"output already exists: {args.output} (use --force to overwrite)")
        files = load_input(args.source, args.include_hidden)
        boot_sector, _ = load_boot_sector(args, files)
        image, used_bytes, free_bytes = build_image(files, boot_sector)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
        print_manifest(files)
        print(f"Wrote: {args.output}")
        print(f"Image size: {len(image)} bytes ({len(image) // 1024} KiB)")
        print(f"Allocated file data: {used_bytes} bytes")
        print(f"Free cluster space: {free_bytes} bytes")
        print(f"DSK SHA-256: {hashlib.sha256(image).hexdigest()}")
        return 0
    except (BuildError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
