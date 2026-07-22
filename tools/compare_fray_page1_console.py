#!/usr/bin/env python3
"""Compare two Fray openMSX diagnostic traces."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


AUDIO_GROUPS = {
    "fm": {"7C", "7D"},
    "psg": {"A0", "A1"},
    "moonsound": {"C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"},
}


def trace_events(path: Path, kind: str, after_time: float, until_time=None, ports=None):
    events = []
    pattern = re.compile(rf"^{kind}\s+([0-9.]+)\s+PC=([0-9A-F]+).*?(?:PORT=([0-9A-F]+).*?VALUE=([0-9A-F]+)|PAGE=([0-9]+) SEGMENT=([0-9A-F]+))")
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        event_time = float(match.group(1))
        if event_time < after_time:
            continue
        if until_time is not None and event_time > until_time:
            continue
        if kind == "IO":
            port, value = match.group(3), match.group(4)
            if ports is not None and port not in ports:
                continue
            key = (port, value)
        else:
            key = (match.group(5), match.group(6))
        events.append({
            "key": key,
            "time": match.group(1),
            "pc": match.group(2),
            "line": line,
        })
    return events


def first_difference(left, right):
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index]["key"] != right[index]["key"]:
            return index, left[index], right[index]
    if len(left) != len(right):
        return limit, left[limit:] or "<end>", right[limit:] or "<end>"
    return None


def print_difference_event(side, event):
    if isinstance(event, dict):
        print(f"  {side}: {event['key']} time={event['time']} PC={event['pc']}")
        print(f"         {event['line']}")
    elif isinstance(event, list):
        print(f"  {side}: {len(event)} unmatched events")
        for item in event[:3]:
            print(f"         {item['line']}")
        if len(event) > 3:
            print("         ...")
    else:
        print(f"  {side}: {event}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument(
        "--after-time",
        type=float,
        default=36.0,
        metavar="SECONDS",
        help="ignore events before this machine time (default: 36, after playback command)",
    )
    parser.add_argument(
        "--until-time",
        type=float,
        default=None,
        metavar="SECONDS",
        help="ignore events after this machine time (use the same emulated interval in both runs)",
    )
    args = parser.parse_args()

    end_text = "end" if args.until_time is None else f"{args.until_time:.3f}s"
    print(f"comparing events from {args.after_time:.3f}s through {end_text}")

    streams = [(label, "IO", ports) for label, ports in AUDIO_GROUPS.items()]
    streams.append(("mapper", "RAMMAP", None))
    for label, kind, ports in streams:
        left = trace_events(args.left, kind, args.after_time, args.until_time, ports)
        right = trace_events(args.right, kind, args.after_time, args.until_time, ports)
        diff = first_difference(left, right)
        print(f"{label}: left={len(left)} right={len(right)}")
        if diff is None:
            print(f"{label}: identical")
        else:
            index, left_event, right_event = diff
            if isinstance(left_event, list) or isinstance(right_event, list):
                left_extra = len(left_event) if isinstance(left_event, list) else 0
                right_extra = len(right_event) if isinstance(right_event, list) else 0
                print(
                    f"{label}: common prefix identical for {index} events; "
                    f"extra tail left={left_extra} right={right_extra}"
                )
            else:
                print(f"{label}: first value difference at event {index}")
            for side, event in (("left", left_event), ("right", right_event)):
                print_difference_event(side, event)
            left_context = [event["key"] for event in left[max(0, index - 4):index + 4]]
            right_context = [event["key"] for event in right[max(0, index - 4):index + 4]]
            print(f"  left context : {left_context}")
            print(f"  right context: {right_context}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
