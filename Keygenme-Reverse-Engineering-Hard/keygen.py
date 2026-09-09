#!/usr/bin/env python3
"""
keygen.py - keygen untuk picoCTF 2022 "Keygenme".

Alih-alih menyalin hasil akhirnya, script ini menirukan fungsi validasi di
`0x1209` secara harfiah: sebuah stack palsu dipetakan sebagai dict
offset-dari-rbp -> byte, lalu setiap instruksi yang menulis ke stack
direplay dengan urutan yang sama persis seperti di binary.

Ini penting karena binary-nya memanen karakter dari hex digest lewat
**offset stack mentah** (`[rbp-0x3b]`, `[rbp-0x5a]`, ...), bukan lewat indeks
array. Dua buffer hex-nya juga bersebelahan dan NUL dari `sprintf` saling
menimpa, jadi menebak indeks tanpa memodelkan tata letaknya gampang meleset.

    python3 keygen.py            # cetak kunci
    python3 keygen.py -v         # tampilkan langkah antara
"""
import hashlib
import sys

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv

# --- stack palsu ---------------------------------------------------------
mem = {}


def wr(off, data):
    for i, b in enumerate(data):
        mem[off + i] = b


def rd(off, n=1):
    return bytes(mem[off + i] for i in range(n))


def strlen(off):
    n = 0
    while mem[off + n] != 0:
        n += 1
    return n


# --- 0x122e-0x1265 : konstanta movabs ------------------------------------
# Prefix flag ditanam sebagai immediate 64-bit, bukan sebagai string di
# .rodata -- itu sebabnya `strings` cuma memperlihatkan potongan seperti
# 'picoCTF{H' (huruf 'H' itu byte REX.W dari instruksi `mov` berikutnya).
wr(-0x90, (0x7B4654436F636970).to_bytes(8, "little"))  # "picoCTF{"
wr(-0x88, (0x30795F676E317262).to_bytes(8, "little"))  # "br1ng_y0"
wr(-0x80, (0x6B5F6E77305F7275).to_bytes(8, "little"))  # "ur_0wn_k"
wr(-0x78, (0x5F7933).to_bytes(4, "little"))            # "3y_\0"
wr(-0xB2, (0x7D).to_bytes(2, "little"))                # "}\0"

# --- 0x126e-0x12bf : MD5(prefix) dan MD5("}") ----------------------------
wr(-0xB0, hashlib.md5(rd(-0x90, strlen(-0x90))).digest())
wr(-0xA0, hashlib.md5(rd(-0xB2, strlen(-0xB2))).digest())

# --- 0x12da-0x1328 : sprintf("%02x") digest #1 -> rbp-0x70 ---------------
# sprintf ikut menulis NUL, dan NUL itulah yang nanti ditimpa buffer berikutnya.
for i in range(16):
    wr(-0x70 + 2 * i, ("%02x" % mem[-0xB0 + i]).encode() + b"\x00")

# --- 0x1340-0x138e : sprintf("%02x") digest #2 -> rbp-0x50 ---------------
for i in range(16):
    wr(-0x50 + 2 * i, ("%02x" % mem[-0xA0 + i]).encode() + b"\x00")

# --- 0x139c-0x13c6 : salin 27 byte prefix -> buffer kunci di rbp-0x30 ----
for i in range(0x1B):
    mem[-0x30 + i] = mem[-0x90 + i]

# --- 0x13c8-0x1407 : 9 byte terakhir, dipanen dari offset stack mentah ---
TAIL = [
    (-0x15, -0x3B),  # 13c8  hex2[21]
    (-0x14, -0x5A),  # 13cf  hex1[22]
    (-0x13, -0x5A),  # 13d6  hex1[22]
    (-0x12, -0x70),  # 13dd  hex1[0]
    (-0x11, -0x53),  # 13e4  hex1[29]
    (-0x10, -0x3B),  # 13eb  hex2[21]
    (-0x0F, -0x62),  # 13f2  hex1[14]
    (-0x0E, -0x58),  # 13f9  hex1[24]
    (-0x0D, -0xB2),  # 1400  '}'
]
for dst, src in TAIL:
    mem[dst] = mem[src]

KEY = rd(-0x30, 0x24)  # 0x1419: panjang harus tepat 0x24 = 36

if VERBOSE:
    hex1 = rd(-0x70, 32).decode()
    hex2 = rd(-0x50, 32).decode()
    print(f"prefix        : {rd(-0x90, 27).decode()}")
    print(f"MD5(prefix)   : {hex1}   <- rbp-0x70")
    print(f'MD5("}}")      : {hex2}   <- rbp-0x50')
    print("\n9 byte terakhir:")
    for n, (dst, src) in enumerate(TAIL):
        if src == -0xB2:
            asal = "literal '}'"
        elif src <= -0x51:
            asal = f"hex1[{src + 0x70:2d}]"
        else:
            asal = f"hex2[{src + 0x50:2d}]"
        print(f"  key[{27 + n}] <- [rbp-{-dst:#04x}] <- [rbp-{-src:#04x}]  = {asal} = {chr(mem[dst])!r}")
    print()

print(KEY.decode())
