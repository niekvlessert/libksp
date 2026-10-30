#!/usr/bin/env python3
"""Forward ZX0 v2 codec with quick and optimal compression modes.

The pure-Python compressor is deterministic and greedy. When a native compiler
is available, the bundled BSD-licensed ``zx0_opt.c`` helper is built and used
for optimal ZX0 parsing. Decompression is identical in both modes.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable, Tuple

MAX_OFFSET = 32640
DEFAULT_AUTO_OPTIMAL_TIMEOUT_SECONDS = 10.0


class OptimalCompressionTimeout(RuntimeError):
    """The native optimal parser exceeded its per-page time budget."""


def auto_timeout_seconds() -> float:
    raw = os.environ.get('ZX0_AUTO_OPTIMAL_TIMEOUT_SECONDS', '').strip()
    if not raw:
        return DEFAULT_AUTO_OPTIMAL_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError('ZX0_AUTO_OPTIMAL_TIMEOUT_SECONDS must be a positive number') from exc
    if value <= 0:
        raise ValueError('ZX0_AUTO_OPTIMAL_TIMEOUT_SECONDS must be greater than zero')
    return value


class BitWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.bit_mask = 0
        self.bit_index = -1
        self.backtrack = True
    def byte(self, value: int) -> None:
        self.data.append(value & 0xFF)
    def bit(self, value: int | bool) -> None:
        if self.backtrack:
            if value:
                if not self.data:
                    raise RuntimeError('ZX0 backtrack without byte')
                self.data[-1] |= 1
            self.backtrack = False
            return
        if self.bit_mask == 0:
            self.bit_mask = 0x80
            self.bit_index = len(self.data)
            self.byte(0)
        if value:
            self.data[self.bit_index] |= self.bit_mask
        self.bit_mask >>= 1
    def gamma(self, value: int, invert: int = 0) -> None:
        if value <= 0:
            raise ValueError('gamma value must be positive')
        mask = 1 << (value.bit_length() - 1)
        while mask > 1:
            mask >>= 1
            self.bit(0)
            self.bit((1 if value & mask else 0) ^ invert)
        self.bit(1)


def compress(data: bytes, *, max_candidates: int = 128, min_match: int = 3) -> bytes:
    if not data:
        raise ValueError('cannot compress empty input')
    n = len(data)
    chains: dict[bytes, list[int]] = defaultdict(list)
    tokens: list[tuple] = []
    literal_start = 0

    def add_pos(pos: int) -> None:
        if pos + 2 >= n:
            return
        key = data[pos:pos + 3]
        lst = chains[key]
        lst.append(pos)
        cutoff = pos - MAX_OFFSET
        if len(lst) > max_candidates * 3:
            lst[:] = [x for x in lst if x >= cutoff][-max_candidates * 2:]

    add_pos(0)
    i = 1  # ZX0 stream must begin with at least one literal.
    while i < n:
        best_len = 0
        best_off = 0
        if i + min_match <= n:
            candidates = chains.get(data[i:i + 3], ())
            checked = 0
            for pos in reversed(candidates):
                off = i - pos
                if off > MAX_OFFSET:
                    break
                checked += 1
                if checked > max_candidates:
                    break
                limit = n - i
                length = 3
                while length < limit and data[i + length] == data[i + length - off]:
                    length += 1
                if length > best_len:
                    best_len, best_off = length, off
                    if length == limit:
                        break
        if best_len >= min_match:
            if i > literal_start:
                tokens.append(('lit', data[literal_start:i]))
            tokens.append(('match', best_off, best_len))
            end = i + best_len
            while i < end:
                add_pos(i)
                i += 1
            literal_start = i
        else:
            add_pos(i)
            i += 1
    if literal_start < n:
        tokens.append(('lit', data[literal_start:]))
    if not tokens or tokens[0][0] != 'lit':
        raise RuntimeError('ZX0 token stream does not begin with literals')

    w = BitWriter()
    last_offset = 1
    consumed = 0
    # ZX0 grammar alternates literal and match branches. Greedy tokens can have
    # adjacent matches; emit an empty-looking one-byte literal between them by
    # folding one source byte into the next literal when necessary.
    normalized: list[tuple] = []
    for tok in tokens:
        if normalized and normalized[-1][0] == tok[0]:
            if tok[0] == 'lit':
                normalized[-1] = ('lit', normalized[-1][1] + tok[1])
            else:
                # Adjacent matches are legal after a new-offset match. Keep as is.
                normalized.append(tok)
        else:
            normalized.append(tok)

    # Initial selector is consumed by the backtrack state; the decoder starts
    # directly with the first literal gamma code.
    w.bit(0)
    first = normalized.pop(0)
    raw = first[1]
    w.gamma(len(raw))
    for b in raw:
        w.byte(b)
    consumed += len(raw)

    for tok in normalized:
        if tok[0] == 'lit':
            raw = tok[1]
            # Literal follows match: selector 0 and gamma length.
            w.bit(0)
            w.gamma(len(raw))
            for b in raw:
                w.byte(b)
            consumed += len(raw)
            continue
        _kind, offset, length = tok
        if offset == last_offset:
            w.bit(0)
            w.gamma(length)
        else:
            w.bit(1)
            w.gamma((offset - 1) // 128 + 1, 1)
            lsb = (offset - 1) % 128
            w.byte((127 - lsb) << 1)
            w.backtrack = True
            w.gamma(length - 1)
            last_offset = offset
        consumed += length
    w.bit(1)
    w.gamma(256, 1)
    if consumed != len(data):
        raise RuntimeError(f'ZX0 consumed {consumed}, expected {len(data)}')
    packed = bytes(w.data)
    if decompress(packed, len(data)) != data:
        raise RuntimeError('ZX0 round-trip failed')
    return packed



def _native_candidates() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    result: list[Path] = []
    configured = os.environ.get('ZX0_OPT')
    if configured:
        result.append(Path(configured).expanduser())
    result.append(module_dir / 'zx0_opt')
    cache_root = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'ftm2ksp'
    result.append(cache_root / 'zx0_opt')
    return result


def _build_native_helper() -> Path | None:
    module_dir = Path(__file__).resolve().parent
    source = module_dir / 'zx0_opt.c'
    if not source.is_file():
        return None
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
    if not compiler:
        return None
    cache_root = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'ftm2ksp'
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    output = cache_root / 'zx0_opt'
    signature = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    stamp = cache_root / 'zx0_opt.sha256'
    if output.is_file() and os.access(output, os.X_OK) and stamp.is_file() and stamp.read_text().strip() == signature:
        return output
    temporary = output.with_suffix('.tmp')
    command = [compiler, '-O3', '-std=c99', '-o', str(temporary), str(source)]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120)
        if completed.returncode != 0:
            temporary.unlink(missing_ok=True)
            return None
        temporary.chmod(0o755)
        temporary.replace(output)
        stamp.write_text(signature + '\n', encoding='ascii')
        return output
    except (OSError, subprocess.SubprocessError):
        temporary.unlink(missing_ok=True)
        return None


def native_helper() -> Path | None:
    for candidate in _native_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return _build_native_helper()


def compress_optimal(data: bytes, *, timeout: float | None = None) -> bytes:
    if not data:
        raise ValueError('cannot compress empty input')
    helper = native_helper()
    if helper is None:
        raise RuntimeError('optimal ZX0 helper unavailable; install a C compiler or use --compression quick')
    try:
        completed = subprocess.run(
            [str(helper)], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        seconds = timeout if timeout is not None else 0.0
        raise OptimalCompressionTimeout(
            f'optimal ZX0 compression exceeded {seconds:g} seconds for a {len(data)}-byte block'
        ) from exc
    except OSError as exc:
        raise RuntimeError(f'cannot execute optimal ZX0 helper: {exc}') from exc
    if completed.returncode != 0:
        message = completed.stderr.decode('utf-8', 'replace').strip()
        raise RuntimeError('optimal ZX0 compression failed' + (': ' + message if message else ''))
    packed = completed.stdout
    if decompress(packed, len(data)) != data:
        raise RuntimeError('optimal ZX0 round-trip failed')
    return packed


def compress_best(data: bytes, mode: str = 'auto') -> Tuple[bytes, str]:
    if mode not in {'auto', 'optimal', 'quick'}:
        raise ValueError(f'unknown ZX0 compression mode {mode!r}')
    if mode == 'quick':
        return compress(data), 'quick-python'
    if mode == 'optimal':
        # Explicit optimal mode is the original unbounded v1.7 path.
        return compress_optimal(data), 'optimal-native'
    try:
        # Auto is still one native optimal pass. There is no quick pre-pass,
        # size cutoff, or second compression for successful pages.
        return compress_optimal(data, timeout=auto_timeout_seconds()), 'optimal-native'
    except OptimalCompressionTimeout:
        return compress(data), 'quick-python-optimal-timeout'
    except RuntimeError:
        return compress(data), 'quick-python-fallback'

def decompress(inp: bytes, expected: int) -> bytes:
    index = 0
    mask = 0
    bits = 0
    last = 0
    backtrack = False
    output = bytearray()
    offset = 1
    def read_byte() -> int:
        nonlocal index, last
        if index >= len(inp):
            raise ValueError('truncated ZX0 stream')
        last = inp[index]; index += 1; return last
    def read_bit() -> int:
        nonlocal mask, bits, backtrack
        if backtrack:
            backtrack = False
            return last & 1
        if mask == 0:
            bits = read_byte(); mask = 0x80
        result = 1 if bits & mask else 0
        mask >>= 1
        return result
    def gamma(inverted: int = 0) -> int:
        value = 1
        while read_bit() == 0:
            value = (value << 1) | (read_bit() ^ inverted)
        return value
    def literals(count: int) -> None:
        for _ in range(count): output.append(read_byte())
    def copy(count: int) -> None:
        if offset < 1 or offset > len(output):
            raise ValueError('invalid ZX0 back-reference')
        for _ in range(count): output.append(output[-offset])
    literals(gamma())
    while True:
        branch = read_bit()
        if branch == 0:
            copy(gamma())
            branch = read_bit()
            if branch == 0:
                literals(gamma())
                continue
        while True:
            msb = gamma(1)
            if msb == 256:
                if len(output) != expected:
                    raise ValueError(f'ZX0 size mismatch: {len(output)} != {expected}')
                return bytes(output)
            lsb = read_byte()
            offset = msb * 128 - (lsb >> 1)
            backtrack = True
            copy(gamma() + 1)
            branch = read_bit()
            if branch == 0:
                literals(gamma())
                break
