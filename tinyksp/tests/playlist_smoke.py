#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: playlist_smoke.py TINYKSP MULTITRACK.ksp")

binary = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix="tinyksp-playlist-") as temp_name:
    temp = Path(temp_name)
    first = temp / "01-first.ksp"
    second = temp / "02-second.ksp"
    shutil.copyfile(fixture, first)
    shutil.copyfile(fixture, second)

    fake_bin = temp / "bin"
    fake_bin.mkdir()
    fake_mpv = fake_bin / ("mpv.exe" if os.name == "nt" else "mpv")
    fake_mpv.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "while sys.stdin.buffer.read(65536):\n"
        "    pass\n",
        encoding="utf-8",
    )
    fake_mpv.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env.setdefault("TERM", "dumb")
    result = subprocess.run(
        [str(binary), str(temp / "0?-*.ksp"), "--seconds", "1"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=30,
    )

text = result.stdout.replace("\r", "\n")
checks = {
    "first wildcard file": "File 1/2:",
    "second wildcard file": "File 2/2:",
    "automatic second track": "Now playing track 2/2: Second track",
    "next KSP transition": "Advancing to next KSP file.",
    "playlist completion": "Playlist finished.",
}
for description, needle in checks.items():
    if needle not in text:
        print(text, file=sys.stderr)
        raise SystemExit(f"missing {description}: {needle}")
if text.count("Track 1: 00:01 finished.") != 2:
    print(text, file=sys.stderr)
    raise SystemExit("track 1 did not finish exactly once in each KSP")
if text.count("Track 2: 00:01 finished.") != 2:
    print(text, file=sys.stderr)
    raise SystemExit("track 2 did not finish exactly once in each KSP")
if result.returncode != 0:
    raise SystemExit(f"tinyksp exited with {result.returncode}")
print("Wildcard and automatic track/file progression test passed")
