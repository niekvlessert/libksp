#!/usr/bin/env python3
from __future__ import annotations

import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: manual_next_file_smoke.py TINYKSP MULTITRACK.ksp")

binary = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix="tinyksp-manual-next-") as temp_name:
    temp = Path(temp_name)
    first = temp / "01-first.ksp"
    second = temp / "02-second.ksp"
    shutil.copyfile(fixture, first)
    shutil.copyfile(fixture, second)

    fake_bin = temp / "bin"
    fake_bin.mkdir()
    fake_mpv = fake_bin / "mpv"
    fake_mpv.write_text(
        "#!/usr/bin/env python3\n"
        "import sys,time\n"
        "while True:\n"
        "    data=sys.stdin.buffer.read(4096)\n"
        "    if not data: break\n"
        "    time.sleep(len(data)/176400.0)\n",
        encoding="utf-8",
    )
    fake_mpv.chmod(0o755)

    master, slave = pty.openpty()
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    process = subprocess.Popen(
        [str(binary), str(temp / "0?-*.ksp"), "--seconds", "25"],
        stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True,
    )
    os.close(slave)
    output = bytearray()

    def drain(duration: float) -> None:
        end = time.time() + duration
        while time.time() < end:
            readable, _, _ = select.select([master], [], [], 0.05)
            if not readable:
                continue
            try:
                output.extend(os.read(master, 8192))
            except OSError:
                return

    drain(0.5)
    os.write(master, b"\x1b[C")  # track 1 -> track 2
    drain(0.5)
    os.write(master, b"\x1b[C")  # final track -> next KSP
    drain(0.8)
    os.write(master, b"q")

    deadline = time.time() + 8.0
    while process.poll() is None and time.time() < deadline:
        drain(0.1)
    if process.poll() is None:
        process.kill()
        raise SystemExit("manual next-file test timed out")
    drain(0.2)
    os.close(master)

text = output.decode("utf-8", "replace").replace("\r", "\n")
checks = {
    "manual second track": "Now playing track 2/2: Second track",
    "manual file skip": "Skipping to next KSP file.",
    "main-loop transition": "Advancing to next KSP file.",
    "second file opened": "File 2/2:",
}
for description, needle in checks.items():
    if needle not in text:
        print(text, file=sys.stderr)
        raise SystemExit(f"missing {description}: {needle}")
if process.returncode != 0:
    raise SystemExit(f"tinyksp exited with {process.returncode}")
print("Right-arrow final-track to next-KSP test passed")
