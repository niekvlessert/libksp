#!/usr/bin/env python3
from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: live_controls_smoke.py TINYKSP ADAPTIVE_MULTITRACK.ksp")

binary = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix="tinyksp-mpv-") as temp:
    fake_mpv = Path(temp) / "mpv"
    fake_mpv.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys,time\n"
        "from pathlib import Path\n"
        "log=os.environ.get('TINYKSP_TEST_MPV_ARGS')\n"
        "if log: Path(log).write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        "while True:\n"
        "    data=sys.stdin.buffer.read(4096)\n"
        "    if not data: break\n"
        "    time.sleep(len(data)/176400.0)\n",
        encoding="utf-8",
    )
    fake_mpv.chmod(0o755)

    master, slave = pty.openpty()
    env = os.environ.copy()
    env["PATH"] = temp + os.pathsep + env.get("PATH", "")
    mpv_args_log = Path(temp) / "mpv-args.txt"
    env["TINYKSP_TEST_MPV_ARGS"] = str(mpv_args_log)
    process = subprocess.Popen(
        [str(binary), str(fixture), "--track", "1", "--variant", "1", "--seconds", "25"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
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

    drain(0.35)
    os.write(master, b"1")       # Mute SCC-A 1 before seeking
    drain(0.20)
    os.write(master, b".")       # Unshifted period must not seek
    time.sleep(0.15)
    os.write(master, b",")       # Unshifted comma must not seek
    time.sleep(0.15)
    os.write(master, b">")       # Shift+. safe seek forward 10 seconds
    drain(0.35)
    os.write(master, b"<")       # Shift+, safe seek backward 10 seconds
    drain(0.35)
    os.write(master, b"u")       # Clear preserved seek mute before track test
    drain(0.20)
    os.write(master, b"\x1b[C")       # Standard Right: next track
    drain(0.40)
    os.write(master, b"\x1b[D")       # Standard Left: previous track
    drain(0.40)
    os.write(master, b"\x1b[1;2C")    # Parameterized Right must still be a track key
    drain(0.40)
    os.write(master, b"\x1bOD")       # SS3 Left must still be a track key
    drain(0.40)
    os.write(master, b"1")       # SCC-A 1
    drain(0.25)
    os.write(master, b"\t")      # PSG page
    drain(0.25)
    os.write(master, b"1")       # PSG A
    drain(0.25)
    os.write(master, b"u")       # unmute all
    drain(1.25)
    os.write(master, b"q")       # stop

    deadline = time.time() + 8.0
    while process.poll() is None and time.time() < deadline:
        drain(0.1)
    if process.poll() is None:
        process.kill()
        raise SystemExit("live control test timed out")
    drain(0.2)
    os.close(master)
    mpv_args = mpv_args_log.read_text(encoding="utf-8") if mpv_args_log.exists() else ""

text = output.decode("utf-8", "replace")
for required in ("--no-config", "--terminal=no", "--input-terminal=no", "--cache=no", "--demuxer-readahead-secs=0"):
    if required not in mpv_args:
        print(mpv_args, file=sys.stderr)
        raise SystemExit(f"mpv isolation option missing: {required}")
seek_section = text.split("Seek: 00:10", 1)
if len(seek_section) != 2 or "1=SCC-A 1 [MUTED]" not in seek_section[1].split("Seek: 00:00", 1)[0]:
    print(text.replace("\r", "\n"), file=sys.stderr)
    raise SystemExit("channel mute was not preserved across forward seek")
checks = {
    "forward seek": "Seek: 00:10",
    "backward seek": "Seek: 00:00",
    "right-arrow next track": "Now playing track 2/2: Second track",
    "left-arrow previous track": "Now playing track 1/2: First track",
    "variant preservation": "Playback type: Dual SCC + PSG",
    "SCC number-key mute": "1=SCC-A 1 [MUTED]",
    "channel-page switch and PSG mute": "1=PSG A [MUTED]",
    "seconds progress": "00:01",
    "quit key": "stopped.",
}
if text.count("Seek: 00:10") != 1 or text.count("Seek: 00:00") != 1:
    print(text.replace("\r", "\n"), file=sys.stderr)
    raise SystemExit("unshifted comma/period or arrow keys incorrectly triggered seeking")
if text.count("Now playing track 2/2: Second track") < 2 or text.count("Now playing track 1/2: First track") < 2:
    print(text.replace("\r", "\n"), file=sys.stderr)
    raise SystemExit("standard/parameterized arrow decoding did not switch tracks consistently")
for description, needle in checks.items():
    if needle not in text:
        print(text.replace("\r", "\n"), file=sys.stderr)
        raise SystemExit(f"missing {description}: {needle}")
if process.returncode != 0:
    raise SystemExit(f"tinyksp exited with {process.returncode}")
print("PTY mpv-isolation/progress/seek/arrow/channel-key test passed")
