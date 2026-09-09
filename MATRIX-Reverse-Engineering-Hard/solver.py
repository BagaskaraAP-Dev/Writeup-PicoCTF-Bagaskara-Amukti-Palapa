#!/usr/bin/env python3
"""
solver.py - cari jalan keluar labirin MATRIX lewat BFS di atas emulator VM,
lalu kirim ke server picoCTF untuk mengambil flag.

    python3 solver.py            # BFS + gambar peta + solusi
    python3 solver.py --remote   # sekalian kirim ke mars.picoctf.net:31259
"""
import sys
from collections import deque

from matrix_vm import VM, maze, render

HOST, PORT = "mars.picoctf.net", 31259
MOVES = b"udlr"


def bfs():
    """BFS pada state VM itu sendiri, bukan pada koordinat (x, y).

    State VM = (pc, data stack, return stack). Jumlah kunci `z` ada di dalam
    stack, jadi dedup ini otomatis membedakan 'posisi sama tapi kunci beda' —
    tak perlu memodelkan aturan kunci/gerbang secara manual sama sekali.
    """
    start = VM()
    start.step_until_input()
    seen = {start.key()}
    queue = deque([(start, b"")])
    while queue:
        vm, path = queue.popleft()
        for mv in MOVES:
            nxt = vm.clone()
            nxt.step_until_input(feed=mv)
            new_path = path + bytes([mv])
            if nxt.halted:
                if nxt.result == 0:          # exit_code 0 => binary cetak flag
                    return new_path, bytes(nxt.out), len(seen)
                continue                     # mati kena grue / gerbang terkunci
            k = nxt.key()
            if k in seen:
                continue
            seen.add(k)
            queue.append((nxt, new_path))
    raise RuntimeError("tidak ada jalan keluar")


def trace(path):
    """Lacak jalur di atas grid untuk visualisasi."""
    grid = maze()
    delta = {"u": (0, -1), "d": (0, 1), "l": (-1, 0), "r": (1, 0)}
    x, y, z = 1, 1, 0
    seq, log = [(x, y)], []
    for mv in path.decode():
        dx, dy = delta[mv]
        x, y = x + dx, y + dy
        cell = grid[y][x]
        if cell == "K":
            z += 1
            log.append(f"({x:2d},{y:2d}) ambil kunci  -> z={z}")
        elif cell == "G":
            z -= 1
            log.append(f"({x:2d},{y:2d}) lewat gerbang -> z={z}")
        elif cell == "E":
            log.append(f"({x:2d},{y:2d}) EXIT")
            break
        seq.append((x, y))
    return grid, seq, log


def remote(path):
    import socket
    import time

    s = socket.create_connection((HOST, PORT), timeout=15)
    s.sendall(path + b"\n")
    time.sleep(3)
    s.settimeout(5)
    buf = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    return buf.decode("latin1")


if __name__ == "__main__":
    path, out, states = bfs()
    grid, seq, log = trace(path)

    print(render(grid, seq))
    print()
    for line in log:
        print(" ", line)
    print(f"\nstate dijelajahi : {states}")
    print(f"panjang solusi   : {len(path)} gerakan")
    print(f"solusi           : {path.decode()}")
    print(f"\noutput lokal     : {out.decode('latin1').strip()!r}")

    if "--remote" in sys.argv:
        print("\n--- mars.picoctf.net:31259 ---")
        print(remote(path))
