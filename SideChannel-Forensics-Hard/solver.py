#!/usr/bin/env python3
"""
SideChannel (picoCTF 2022) - timing side-channel solver.

pin_checker mengecek PIN 8 digit dari kiri ke kanan dan menambah delay ~125 ms
untuk SETIAP digit prefix yang benar sebelum akhirnya menolak. Jadi lama eksekusi
membocorkan berapa banyak digit awal yang sudah cocok.

Strategi (tanpa reverse-engineer binary sama sekali):
  untuk tiap posisi 0..7:
    coba digit '0'..'9' (posisi sisa diisi '0' supaya panjang tetap 8),
    ukur waktu eksekusi (median beberapa run untuk meredam noise scheduler),
    digit dengan waktu PALING LAMA = digit yang benar di posisi itu.
  fix digit tsb, lanjut ke posisi berikutnya.

Biaya: 8 x 10 = 80 grup pengukuran, bukan 10^8 brute force.

Jalankan (butuh binary di WSL/Linux, x86 32-bit):
    python3 solver.py ./pin_checker
"""
import subprocess
import sys
import time
import statistics

LEN = 8
TRIALS = 8  # run per tebakan; median dipakai untuk meredam noise


def measure(binary: str, pin: str) -> float:
    """Median waktu eksekusi binary untuk satu tebakan PIN."""
    times = []
    for _ in range(TRIALS):
        t0 = time.perf_counter()
        subprocess.run(
            [binary],
            input=(pin + "\n").encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def solve(binary: str) -> str:
    known = ""
    for pos in range(LEN):
        best_digit, best_time = None, -1.0
        row = []
        for d in range(10):
            guess = known + str(d) + "0" * (LEN - pos - 1)
            t = measure(binary, guess)
            row.append((d, t))
            if t > best_time:
                best_time, best_digit = t, d
        known += str(best_digit)
        row.sort(key=lambda x: -x[1])
        top = ", ".join(f"{d}={t * 1000:.0f}ms" for d, t in row[:3])
        print(f"pos {pos}: chose {best_digit}   top: {top}   -> {known}")
        sys.stdout.flush()
    return known


def verify(binary: str, pin: str) -> None:
    out = subprocess.run(
        [binary], input=pin + "\n", capture_output=True, text=True
    )
    print("\nPIN:", pin)
    print("Lokal:", " | ".join(out.stdout.split("\n")).strip(" |"))


if __name__ == "__main__":
    bin_path = sys.argv[1] if len(sys.argv) > 1 else "./pin_checker"
    pin = solve(bin_path)
    verify(bin_path, pin)
    print("\nLangkah terakhir: kirim PIN ke master server ->")
    print(f"  printf '{pin}\\n' | nc saturn.picoctf.net 55509")
