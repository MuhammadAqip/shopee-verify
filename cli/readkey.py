#!/usr/bin/env python3
r"""readkey.py — emit one logical key name per line.

Bash's `read -rsn1` cannot reliably capture the ESC byte (0x1b): it comes back
as an empty string indistinguishable from EOF, and quoted case patterns like
'\[A' match literally, never the real byte. So the escape-sequence parsing
lives here, in Python, where os.read gives exact bytes.

Prints one of: pgup pgdn up down home end quit help <digit> enter esc
Exits 0 on success. Exit 3 = stdin closed (real EOF).
"""
import os
import sys

MAP = {
    b"[5~": "pgup",
    b"[6~": "pgdn",
    b"[1~": "home",
    b"[4~": "end",
    b"[H": "home",
    b"[F": "end",
    b"OA": "up",
    b"OB": "down",
    b"[A": "up",
    b"[B": "down",
    b"[C": "right",
    b"[D": "left",
}


def read_byte():
    b = os.read(0, 1)
    return b if b else None


def main():
    c = read_byte()
    if c is None:
        return 3

    if c == b"\x1b":
        # ESC: pull the rest of a CSI/SS3 sequence if it is already queued.
        seq = b""
        for _ in range(6):
            nxt = read_byte()
            if nxt is None:
                break
            seq += nxt
            if nxt.isalpha() or nxt == b"~":
                break
        if not seq:
            print("esc")
            return 0
        # normalise SS3 ('O'...) to CSI ('['...)
        key = MAP.get(seq) or MAP.get(b"[" + seq[1:] if seq[:1] == b"O" else seq)
        print(key or "esc")
        return 0

    if c in (b"\n", b"\r"):
        print("enter")
        return 0
    if c in (b"q", b"Q"):
        print("quit")
        return 0
    if c == b"\x03":  # Ctrl-C — swallowed by raw mode, so map it to quit
        print("quit")
        return 0
    if c == b"\x04":  # Ctrl-D
        return 3
    if c in (b"h", b"H", b"?"):
        print("help")
        return 0
    if c.isdigit():
        print(c.decode())
        return 0
    print("other")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("quit")
        sys.exit(0)
