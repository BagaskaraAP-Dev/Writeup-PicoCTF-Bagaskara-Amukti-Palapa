#!/usr/bin/env python3
"""
matrix_vm.py - emulator + disassembler untuk VM stack 16-bit di dalam binary
picoCTF "MATRIX" (picoMini by redpwn).

Binary-nya cuma sebuah interpreter kecil; seluruh logika game ada di bytecode
yang disimpan di .rodata pada VA 0x20f0.

Pemakaian:
    python3 matrix_vm.py disasm        # disassembly bytecode VM
    python3 matrix_vm.py maze          # gambar peta labirin 16x16
    python3 matrix_vm.py run <moves>   # jalankan VM secara lokal
"""
import struct
import sys

BINARY = "matrix"
CODE_VA = 0x20F0       # basis bytecode VM
MAZE_VA = 0x174        # offset tabel labirin, relatif terhadap basis bytecode
GRID_W = 16

# ---------------------------------------------------------------- ELF loader

def load_code(path=BINARY):
    d = open(path, "rb").read()
    e_shoff = struct.unpack("<Q", d[0x28:0x30])[0]
    e_shnum = struct.unpack("<H", d[0x3C:0x3E])[0]
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * 64
        addr, off, size = struct.unpack("<QQQ", d[o + 16 : o + 40])
        secs.append((addr, off, size))
    for addr, off, size in secs:
        if size and addr <= CODE_VA < addr + size:
            base = off + (CODE_VA - addr)
            return d[base : base + 0x800]
    raise RuntimeError("bytecode tidak ketemu")


CODE = load_code()

# ------------------------------------------------------------------- opcodes
# Diambil dari jump table di VA 0x201c (handler VM ada di 0x1350).
OPS = {
    0x00: "NOP",
    0x01: "HALT",    # exit_code = pop(); status = 0
    0x10: "DUP",
    0x11: "DROP",
    0x12: "ADD",
    0x13: "SUB",     # second - top
    0x14: "SWAP",
    0x20: ">R",      # data stack -> return stack
    0x21: "R>",      # return stack -> data stack
    0x30: "JMP",     # pc = pop()
    0x31: "JZ",      # addr = pop(); if pop() == 0: pc = addr
    0x32: "JNZ",
    0x33: "JLZ",     # if second < 0 (signed)
    0x34: "JLEZ",    # if second <= 0 (signed)
    0x80: "PUSH8",   # push sign-extended imm8
    0x81: "PUSH16",  # push imm16 little-endian
    0xC0: "IN",      # push getc(stdin)
    0xC1: "OUT",     # putc(pop() & 0xff, stdout)
}


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def disasm(end=0x5D2):
    pc = 0
    out = []
    while pc < end:
        op = CODE[pc]
        if op == 0x80:
            v = CODE[pc + 1]
            v = v - 256 if v >= 128 else v
            note = f"  ; {chr(v)!r}" if 32 <= v < 127 else ""
            out.append(f"{pc:03x}: PUSH8  {v}{note}")
            pc += 2
        elif op == 0x81:
            v = struct.unpack("<H", CODE[pc + 1 : pc + 3])[0]
            out.append(f"{pc:03x}: PUSH16 0x{v:03x}")
            pc += 3
        else:
            out.append(f"{pc:03x}: {OPS.get(op, 'BAD_%02x' % op)}")
            pc += 1
    return "\n".join(out)


# --------------------------------------------------------------------- maze
CELL = {
    b"\x30\x00\x00\x00": ".",  # JMP  -> lanjut (lorong kosong)
    b"\x81\xfb\x00\x30": "#",  # JMP 0x0fb -> "You were eaten by a grue."
    b"\x81\x7f\x05\x30": "K",  # JMP 0x57f -> z += 1   (ambil kunci)
    b"\x81\x74\x05\x30": "G",  # JMP 0x574 -> butuh z > 0, lalu z -= 1 (gerbang)
    b"\x81\x85\x05\x30": "E",  # JMP 0x585 -> "Congratulations, you made it!"
}


def maze():
    grid = []
    for y in range(GRID_W):
        row = ""
        for x in range(GRID_W):
            off = MAZE_VA + 4 * (y * GRID_W + x)
            row += CELL[bytes(CODE[off : off + 4])]
        grid.append(row)
    return grid


def render(grid, path=None):
    view = [list(r) for r in grid]
    if path:
        for x, y in path:
            if view[y][x] == ".":
                view[y][x] = "*"
    lines = ["    " + "".join(str(i % 10) for i in range(GRID_W))]
    for i, r in enumerate(view):
        lines.append(f"{i:2d}  " + "".join(r))
    return "\n".join(lines)


# ----------------------------------------------------------------- emulator
class VM:
    """VM stack 16-bit. Berhenti (pause) tepat di opcode IN kalau input habis,
    sehingga state-nya bisa di-snapshot untuk BFS."""

    __slots__ = ("pc", "ds", "rs", "out", "halted", "result")

    def __init__(self):
        self.pc = 0
        self.ds = []
        self.rs = []
        self.out = bytearray()
        self.halted = False
        self.result = None

    def clone(self):
        v = VM.__new__(VM)
        v.pc, v.ds, v.rs = self.pc, list(self.ds), list(self.rs)
        v.out = bytearray(self.out)
        v.halted, v.result = self.halted, self.result
        return v

    def key(self):
        return (self.pc, tuple(self.ds), tuple(self.rs))

    def step_until_input(self, feed=None, limit=1_000_000):
        """Jalan sampai butuh input. `feed` (kalau ada) dipakai untuk permintaan
        input pertama; permintaan berikutnya membuat VM pause."""
        fed = False
        ds = self.ds
        for _ in range(limit):
            if self.halted:
                return
            here = self.pc
            op = CODE[here]
            self.pc = (here + 1) & 0xFFFF
            if op == 0x00:
                pass
            elif op == 0x01:
                self.result = s16(ds.pop())
                self.halted = True
                return
            elif op == 0x10:
                ds.append(ds[-1])
            elif op == 0x11:
                ds.pop()
            elif op == 0x12:
                a, b = ds.pop(), ds.pop()
                ds.append((a + b) & 0xFFFF)
            elif op == 0x13:
                a, b = ds.pop(), ds.pop()
                ds.append((b - a) & 0xFFFF)
            elif op == 0x14:
                ds[-1], ds[-2] = ds[-2], ds[-1]
            elif op == 0x20:
                self.rs.append(ds.pop())
            elif op == 0x21:
                ds.append(self.rs.pop())
            elif op == 0x30:
                self.pc = ds.pop() & 0xFFFF
            elif op == 0x31:
                a, b = ds.pop(), ds.pop()
                if s16(b) == 0:
                    self.pc = a & 0xFFFF
            elif op == 0x32:
                a, b = ds.pop(), ds.pop()
                if s16(b) != 0:
                    self.pc = a & 0xFFFF
            elif op == 0x33:
                a, b = ds.pop(), ds.pop()
                if s16(b) < 0:
                    self.pc = a & 0xFFFF
            elif op == 0x34:
                a, b = ds.pop(), ds.pop()
                if s16(b) <= 0:
                    self.pc = a & 0xFFFF
            elif op == 0xC0:
                if feed is not None and not fed:
                    ds.append(feed)
                    fed = True
                else:
                    self.pc = here  # rewind ke opcode IN, lalu pause
                    return
            elif op == 0xC1:
                self.out.append(ds.pop() & 0xFF)
            elif op == 0x80:
                v = CODE[self.pc]
                self.pc = (here + 2) & 0xFFFF
                ds.append((v - 256 if v >= 128 else v) & 0xFFFF)
            elif op == 0x81:
                ds.append(struct.unpack("<H", CODE[self.pc : self.pc + 2])[0])
                self.pc = (here + 3) & 0xFFFF
            else:
                self.halted = True
                self.result = None
                return
        self.halted = True


def run(moves=b""):
    """Jalankan bytecode dengan rangkaian gerakan; balikkan (output, exit_code)."""
    vm = VM()
    vm.step_until_input()
    for m in moves:
        if vm.halted:
            break
        vm.step_until_input(feed=m)
    return bytes(vm.out), vm.result


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "maze"
    if cmd == "disasm":
        print(disasm())
    elif cmd == "maze":
        print(render(maze()))
        print("\n#=tembok  .=lorong  K=kunci(z+1)  G=gerbang(butuh z>0, z-1)  E=exit")
        print("start: x=1, y=1, z=0")
    elif cmd == "run":
        out, res = run(sys.argv[2].encode() if len(sys.argv) > 2 else b"")
        sys.stdout.write(out.decode("latin1"))
        print(f"[exit_code={res}]  (0 = flag dicetak)")
    else:
        print(__doc__)
