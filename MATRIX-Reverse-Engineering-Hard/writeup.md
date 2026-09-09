# MATRIX

- **Kategori:** Reverse Engineering
- **Kesulitan:** Hard
- **Author:** asphyxia
- **Event:** picoMini by redpwn (2021)
- **Flag:** `picoCTF{y0uv3_3sc4p3d_th3_m4ze...f0r_n0w-hYkq2D9PmrA5GpEq}`

> *"Enter the M A T R I X"*
> `nc mars.picoctf.net 31259`

Yang dikasih cuma satu ELF 64-bit ter-*strip* bernama `matrix`. Ternyata isinya **bukan** logika soal — binary-nya cuma sebuah **interpreter VM stack 16-bit** setebal ±600 byte, dan seluruh tantangannya ada di **bytecode** yang disimpan sebagai data di `.rodata`. Bytecode itu, setelah dibongkar, adalah sebuah **game labirin 16×16 bergaya text-adventure** dengan mekanik kunci & gerbang.

---

## 1. Ringkasan Solusi (TL;DR)

1. `matrix` adalah ELF stripped, PIE, dinamis. Fungsi `main` cuma menyiapkan struct lalu memanggil satu fungsi berulang-ulang → ciri khas **loop interpreter**.
2. Fungsi itu (`0x1350`) melakukan `fetch → cmp al, 0x34 → jump table` di `0x201c`. Dari 20-an handler-nya, terekstrak **ISA lengkap** VM stack 16-bit bergaya Forth: `DUP/DROP/ADD/SUB/SWAP`, `>R/R>`, `JMP/JZ/JNZ/JLZ/JLEZ`, `IN/OUT`, `PUSH8/PUSH16`, `HALT`.
3. Bytecode ada di VA `0x20f0`. Setelah di-disassemble, terlihat: parser input `u`/`d`/`l`/`r` yang meng-update `(x, y)`, lalu `idx = y*16 + x` dan **lompat ke `0x174 + 4*idx`** — sebuah **jump table 16×16** = petanya.
4. Tiap sel = 4 byte kode: lorong, tembok (mati), **kunci** (`z += 1`), **gerbang** (butuh `z > 0`, lalu `z -= 1`), dan **exit**.
5. VM ditulis ulang di Python, lalu **BFS langsung di atas state VM** (bukan di atas koordinat) → jalan keluar 63 gerakan ketemu otomatis.
6. Kirim string gerakan itu ke server → binary asli `fopen("flag.txt")` dan mencetak flag.

Kejutan utamanya: solusinya **bukan jalur terpendek di labirin**. Sel kunci bisa diinjak berkali-kali, jadi pemain harus **memantul bolak-balik di satu petak kunci** untuk menimbun 5 kunci sebelum menembus 5 gerbang.

---

## 2. Recon

```console
$ file matrix
matrix: ELF 64-bit LSB pie executable, x86-64, dynamically linked,
        interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=d315f81e...,
        for GNU/Linux 4.4.0, stripped

$ strings matrix
...
getc  fopen  putc  puts  fgets  malloc  free  setvbuf
Have a flag!
flag.txt
```

Import-nya sangat sedikit dan semuanya I/O karakter: `getc`, `putc`, `fopen`. Tidak ada `strcmp`, tidak ada tabel konstanta besar, tidak ada string "Wrong". String yang ada cuma `Have a flag!` dan `flag.txt`.

Padahal saat dijalankan, program mencetak banner panjang:

```
Welcome to the M A T R I X
Can you make it out alive?
```

Teks itu **tidak ada di `strings`**. Artinya banner dibangun karakter-per-karakter saat runtime — indikasi kuat bahwa ada mesin lain di dalam binary yang mengerjakannya.

---

## 3. `main`: Cuma Loop Interpreter

Karena `objdump`/`gdb` tidak tersedia di mesin saya (Windows), saya disassemble pakai **capstone** langsung dari section `.text` yang di-parse manual dari ELF header:

```python
from capstone import *
md = Cs(CS_ARCH_X86, CS_MODE_64)
for ins in md.disasm(text_bytes, text_vaddr):
    print(f"{ins.address:x}: {ins.mnemonic} {ins.op_str}")
```

`main` (`0x10d0`), disederhanakan:

```asm
mov  edi, 0x800
call malloc            ; buffer #1  -> r13
mov  edi, 0x800
call malloc            ; buffer #2  -> r12
lea  rax, [rip+0xfb1]  ; = 0x20f0   <-- pointer ke sesuatu di .rodata
mov  [rsp+0x10], rax
mov  word [rsp+0x18], ax        ; ax = 0
movaps [rsp+0x20], xmm0         ; {r13, r12}
movaps [rsp+0x30], xmm0         ; {0x1320, 0x1340}  <- getc / putc thunk

lea  rbp, [rsp+0xc]             ; -> status byte
lea  rbx, [rsp+0x10]            ; -> struct VM
loop:
  mov rsi, rbp
  mov rdi, rbx
  call 0x1350                   ; <-- single step
  test al, al
  jne  loop                     ; al != 0 -> lanjut
```

Dua `malloc(0x800)`, sebuah pointer ke `.rodata`, sebuah counter 16-bit yang di-nol-kan, dua pointer fungsi I/O, dan satu fungsi yang dipanggil berulang sampai balik `0`. Ini **jelas VM**. Struct-nya:

| offset | isi |
|---|---|
| `+0x00` | pointer bytecode = **`0x20f0`** |
| `+0x08` | **pc** (`uint16`) |
| `+0x10` | **data stack pointer** (buffer #1, elemen 2 byte, tumbuh ke atas) |
| `+0x18` | **return stack pointer** (buffer #2) |
| `+0x20` | pointer ke thunk `getc(stdin)` |
| `+0x28` | pointer ke thunk `putc(c, stdout)` |

Yang menarik ada di **setelah** loop:

```asm
cmp byte [rsp+0xc], 0
jne  error                 ; status != 0 -> return -1, tidak ada flag
cmp word [rsp+0xe], 0
je   print_flag            ; result == 0 -> buka flag.txt & cetak
```

```asm
print_flag:
  lea  rdi, [rip+0xe31]    ; "Have a flag!"
  call puts
  lea  rsi, [rip+0xe2d]    ; "r"
  lea  rdi, [rip+0xe28]    ; "flag.txt"
  call fopen
  ...  fgets / puts / fclose
```

**Kondisi menang jadi sangat jelas:** VM harus berhenti secara normal dan meninggalkan **nilai `0`** di slot hasil. Tidak ada perbandingan string sama sekali — semua penilaian terjadi di dalam bytecode.

---

## 4. Membongkar ISA dari Jump Table

Fungsi step di `0x1350`:

```asm
1350: push rbx
1351: mov  rbx, rdi
1354: mov  rdi, [rdi]              ; basis bytecode
1357: movzx eax, word [rbx+8]      ; pc
135b: lea  ecx, [rax+1]
1361: mov  word [rbx+8], cx        ; pc++
1365: movzx eax, byte [rdi+rax]    ; opcode = code[pc]
1369: cmp  al, 0x34
136b: ja   0x1380                  ; opcode besar ditangani terpisah
136d: lea  rdx, [rip+0xca8]        ; = 0x201c  <-- basis jump table
1374: movsxd rax, dword [rdx+rax*4]
1378: add  rax, rdx
137b: jmp  rax
```

> ⚠️ **Jebakan kecil:** `lea rdx, [rip+0xca8]` dengan `rip = 0x1374` menghasilkan **`0x201c`**, bukan `0x2020`. Awalnya saya salah baca dan seluruh peta opcode meleset satu slot — `HALT` kelihatan seperti `NOP`, dan opcode 1 jadi tampak "invalid". Selisih 4 byte ini bikin bytecode-nya sama sekali tidak masuk akal sampai dikoreksi.

Tabelnya jarang: mayoritas entri menunjuk ke `0x13e0` (handler "opcode tidak dikenal": set status = 1, stop → jalur error). Yang valid:

| opcode | handler | arti |
|---|---|---|
| `0x00` | `0x140b` | `NOP` |
| `0x01` | `0x1428` | **`HALT`** — `result = pop()`, `status = 0`, stop |
| `0x10` | `0x14c0` | `DUP` |
| `0x11` | `0x1418` | `DROP` |
| `0x12` | `0x15a0` | `ADD` |
| `0x13` | `0x1450` | `SUB` (`second - top`) |
| `0x14` | `0x1470` | `SWAP` |
| `0x20` | `0x1490` | `>R` — data stack → return stack |
| `0x21` | `0x14e0` | `R>` — return stack → data stack |
| `0x30` | `0x1510` | `JMP` — `pc = pop()` |
| `0x31` | `0x1530` | `JZ` — `addr = pop(); if pop() == 0: pc = addr` |
| `0x32` | `0x1560` | `JNZ` |
| `0x33` | `0x13f0` | `JLZ` (signed `< 0`) |
| `0x34` | `0x1580` | `JLEZ` (signed `<= 0`) |
| `0x80` | `0x15e0` | `PUSH8` — push imm8 *sign-extended*, `pc += 2` |
| `0x81` | `0x13b4` | `PUSH16` — push imm16 LE, `pc += 3` |
| `0xc0` | `0x15c0` | `IN` — push `getc(stdin)` |
| `0xc1` | `0x138e` | `OUT` — `putc(pop() & 0xff, stdout)` |

Kombinasi `>R` / `R>` plus dua stack terpisah menandakan VM ini didesain bergaya **Forth**. Perhatikan juga `HALT` di `0x1428`:

```asm
1428: xor  eax, eax
1433: mov  rdx, [rbx+0x10]
1437: mov  byte [rsi], 0        ; status = 0  (bersih)
143e: movzx edx, word [rdx-2]   ; pop
1447: mov  word [rsi+2], dx     ; result <- nilai puncak stack
144b: ret                       ; eax = 0 -> hentikan loop
```

Jadi target akhirnya: eksekusi bytecode sampai `HALT` **dengan `0` di puncak stack**.

---

## 5. Disassembly Bytecode

Dengan ISA di tangan, bytecode di `0x20f0` bisa dibaca. Bagian pertama ternyata cuma banner yang di-*push terbalik* lalu di-`OUT` satu per satu:

```
000: PUSH16 0x075        <- alamat kembali (lanjut ke 0x75 setelah cetak)
003: PUSH8  0            <- sentinel akhir string
005: PUSH8  10           ; '\n'
007: PUSH8  63           ; '?'
009: PUSH8  101          ; 'e'
00b: PUSH8  118          ; 'v'
...                        (huruf terbalik: "?evila tuo ti ekam uoy naC")
06f: PUSH8  87           ; 'W'
071: PUSH16 0x13b        <- rutin print
074: JMP
```

Rutin cetak di `0x13b` klasik: pop → kalau `0` selesai, kalau bukan `OUT` lalu ulang.

```
13b: DUP
13c: PUSH16 0x145
13f: JZ                  ; sentinel 0 -> selesai
140: OUT
141: PUSH16 0x13b
144: JMP
145: DROP
146: JMP                 ; kembali ke alamat yang tadi dipush di dasar
```

### 5.1 Inisialisasi & Parser Gerakan

```
075: PUSH8 1             ; x = 1
077: PUSH8 1             ; y = 1
079: PUSH8 0             ; z = 0   <-- jumlah kunci
07b: IN                  ; <-- loop utama mulai di sini
07c: DUP  PUSH8 117  SUB  PUSH16 0x0a0  JZ    ; 'u'
084: DUP  PUSH8 100  SUB  PUSH16 0x0aa  JZ    ; 'd'
08c: DUP  PUSH8 108  SUB  PUSH16 0x0b4  JZ    ; 'l'
094: DUP  PUSH8 114  SUB  PUSH16 0x0c0  JZ    ; 'r'
09c: PUSH16 0x0fb  JMP                        ; selain itu -> mati
```

Empat handler-nya cuma aritmatika stack sederhana:

```
0a0: DROP >R PUSH8 1 SUB R>   -> y -= 1      ('u')
0aa: DROP >R PUSH8 1 ADD R>   -> y += 1      ('d')
0b4: DROP >R >R PUSH8 1 SUB R> R>  -> x -= 1 ('l')
0c0: DROP >R >R PUSH8 1 ADD R> R>  -> x += 1 ('r')
```

Jadi state permainan hanyalah tiga word di data stack: **`[x, y, z]`**. Karakter selain `udlr` (termasuk `\n` dan EOF) langsung melompat ke `0x0fb`, yaitu:

```
0fb: PUSH16 0x138        <- alamat kembali
0fe: PUSH8 0
100: ... "You were eaten by a grue.\n" (terbalik) ...
134: PUSH16 0x13b  JMP   ; cetak
138: PUSH8 1
13a: HALT                ; result = 1 -> TIDAK ada flag
```

Ini penting dan gampang kelewat: **input tidak boleh diakhiri newline yang ikut terbaca sebagai gerakan**. Untungnya `E` di-`HALT` duluan sebelum `\n` sempat dibaca.

### 5.2 Perhitungan Indeks — dan Petanya

```
0cc: >R >R                  ; simpan y, z
0ce: PUSH16 0x0da           ; alamat kembali dari MUL
0d1: R> DUP >R
0d4: PUSH8 16
0d6: PUSH16 0x147  JMP      ; MUL(y, 16)
0da: SWAP DUP >R ADD        ; idx = y*16 + x
...
0e5: PUSH16 0x0ef
0e8: R>  PUSH8 2
0eb: PUSH16 0x161  JMP      ; SHL(idx, 2)  ->  idx*4
0ef: PUSH16 0x07b           ; alamat kembali = balik ke opcode IN
0f2: SWAP
0f3: PUSH16 0x174
0f6: ADD                    ; 0x174 + 4*idx
0f7: JMP                    ; <-- LOMPAT KE DALAM PETA
```

Rutin `0x147` (perkalian lewat penjumlahan berulang) dan `0x161` (geser kiri lewat `DUP ADD`) memang cuma helper aritmatika — VM ini tidak punya `MUL`/`SHL`.

Baris `0f7: JMP` inilah kuncinya. **Labirinnya bukan array data — labirinnya adalah kode.** Setiap petak adalah *jump stub* 4 byte di `0x174 + 4*(y*16 + x)`, dengan alamat balik `0x7b` (opcode `IN`) sudah menunggu di stack.

Rentang tabel: `0x174` sampai `0x574`, tepat `0x400` byte → **256 petak = grid 16×16**.

### 5.3 Lima Jenis Petak

| byte | disassembly | arti |
|---|---|---|
| `30 00 00 00` | `JMP` | **lorong** — langsung balik ke `IN` |
| `81 fb 00 30` | `PUSH16 0x0fb; JMP` | **tembok** — dimakan grue, `HALT 1` |
| `81 7f 05 30` | `PUSH16 0x57f; JMP` | **kunci** |
| `81 74 05 30` | `PUSH16 0x574; JMP` | **gerbang** |
| `81 85 05 30` | `PUSH16 0x585; JMP` | **exit** |

Ketiga handler spesialnya:

```
; 0x57f  KUNCI
57f: >R  PUSH8 1  ADD  R>  JMP        ; z += 1, lanjut

; 0x574  GERBANG
574: >R  DUP  PUSH16 0x0fb  JZ        ; z == 0  -> mati
57a: PUSH8 1  SUB  R>  JMP            ; z -= 1, lanjut

; 0x585  EXIT
585: DROP DROP DROP DROP              ; buang x, y, z, alamat kembali
589: PUSH16 0x5ce
58c: ... "Congratulations, you made it!\n" ...
5cd: JMP                              ; cetak, lalu:
5ce: PUSH16 0x0f8  JMP
0f8: PUSH8 0
0fa: HALT                             ; result = 0  -> FLAG!
```

Handler kunci di `0x57f` **tidak menandai petak sebagai sudah-diambil**. Ini yang nanti jadi inti soalnya.

---

## 6. Petanya

Tinggal decode 256 stub itu (`python3 matrix_vm.py maze`):

```
    0123456789012345
 0  ################
 1  #.....K#.#K..#.#
 2  ####G###.###.#.#
 3  #..........#.#.#
 4  ##.#.#####.#.G.#
 5  #..#.#K..#.#.#.#
 6  #.##.###.#.#.#.#
 7  #.#......#.#.#.#
 8  #.#.######.#.#.#
 9  #.#........#.#.#
10  #.###.######.#.#
11  #...#..G..#..#.#
12  #.###..#..#.#..#
13  #.#...###.#.#G##
14  #.#....#..G.#..#
15  ##############E#

#=tembok  .=lorong  K=kunci  G=gerbang  E=exit
start: x=1, y=1, z=0
```

Sekarang problem-nya kelihatan. Ada **3 petak kunci** — `(6,1)`, `(10,1)`, `(6,5)` — tapi **5 gerbang**: `(4,2)`, `(13,4)`, `(7,11)`, `(13,13)`, `(10,14)`. Kalau tiap kunci cuma bisa diambil sekali, soal ini **tidak punya solusi**.

Tapi tadi sudah terlihat: handler kunci cuma `z += 1`, tanpa mengubah petaknya. Jadi **satu petak kunci bisa diperah tanpa batas** — injak, mundur, injak lagi. Dua kunci lain (`(10,1)` dan `(6,5)`) sebenarnya umpan; keduanya duduk di lorong buntu.

Inilah kenapa soal ini "Hard": kalau kamu memodelkannya sebagai pathfinding biasa dengan asumsi "kunci = item sekali pakai" (asumsi normal di game), kamu akan menyimpulkan labirinnya mustahil dan menyalahkan analisismu sendiri.

---

## 7. Solver: BFS di Atas State VM

Trik yang bikin ini gampang: **jangan memodelkan aturan permainannya sama sekali.** Tulis ulang VM-nya di Python, jalankan sampai berhenti di opcode `IN`, lalu BFS dengan state pencarian = **state VM itu sendiri**.

```python
def bfs():
    start = VM()
    start.step_until_input()
    seen = {start.key()}                 # key = (pc, data stack, return stack)
    queue = deque([(start, b"")])
    while queue:
        vm, path = queue.popleft()
        for mv in b"udlr":
            nxt = vm.clone()
            nxt.step_until_input(feed=mv)
            new_path = path + bytes([mv])
            if nxt.halted:
                if nxt.result == 0:      # exit_code 0 -> binary cetak flag
                    return new_path
                continue                 # mati kena grue / gerbang terkunci
            k = nxt.key()
            if k in seen:
                continue
            seen.add(k)
            queue.append((nxt, new_path))
```

Karena `z` hidup **di dalam data stack**, `vm.key()` otomatis membedakan "posisi sama, jumlah kunci beda". Aturan kunci-bisa-dipakai-ulang, gerbang, tembok, bahkan kondisi menang — semuanya diwarisi gratis dari emulator. Tidak ada satu baris pun logika labirin di solver.

Yang mendasari ini: VM-nya deterministik dan state-nya kecil. Jadi `(pc, data stack, return stack)` adalah state lengkap, dan BFS di atasnya menghasilkan jalur terpendek yang benar secara konstruksi — tak mungkin salah karena asumsi game yang keliru.

Hasilnya: **2145 state** dijelajahi, solusi **63 gerakan**.

```
rrrrrlrlrlrlrllddddddlddrrddrrrdrddrruuuruuuuuuurrddddddddlddrd
```

Jalurnya, digambar di atas peta:

```
    0123456789012345
 0  ################
 1  #*****K#.#K..#.#
 2  ####G###.###.#.#
 3  #...*......#.#.#
 4  ##.#*#####.#*G*#
 5  #..#*#K..#.#*#*#
 6  #.##*###.#.#*#*#
 7  #.#**....#.#*#*#
 8  #.#*######.#*#*#
 9  #.#***.....#*#*#
10  #.###*######*#*#
11  #...#**G*.#**#*#
12  #.###..#**#*#**#
13  #.#...###*#*#G##
14  #.#....#.*G*#**#
15  ##############E#
```

Perhatikan pembukaannya: **`rrrrr` lalu `lrlrlrlr`**. Itu bukan sampah — itu 5 langkah ke petak kunci `(6,1)`, lalu memantul `l`,`r` empat kali untuk menginjaknya lagi dan lagi:

```
( 6, 1) ambil kunci   -> z=1
( 6, 1) ambil kunci   -> z=2
( 6, 1) ambil kunci   -> z=3
( 6, 1) ambil kunci   -> z=4
( 6, 1) ambil kunci   -> z=5
( 4, 2) lewat gerbang -> z=4
( 7,11) lewat gerbang -> z=3
(10,14) lewat gerbang -> z=2
(13, 4) lewat gerbang -> z=1
(13,13) lewat gerbang -> z=0
(14,15) EXIT
```

Lima kunci diambil dari **satu petak yang sama**, lalu dihabiskan tepat di lima gerbang. Sisanya nol.

---

## 8. Ambil Flag

```console
$ python3 solver.py --remote
...
solusi           : rrrrrlrlrlrlrllddddddlddrrddrrrdrddrruuuruuuuuuurrddddddddlddrd

--- mars.picoctf.net:31259 ---
Welcome to the M A T R I X
Can you make it out alive?
Congratulations, you made it!
Have a flag!
picoCTF{y0uv3_3sc4p3d_th3_m4ze...f0r_n0w-hYkq2D9PmrA5GpEq}
```

Atau manual:

```console
$ echo 'rrrrrlrlrlrlrllddddddlddrrddrrrdrddrruuuruuuuuuurrddddddddlddrd' | nc mars.picoctf.net 31259
```

**Flag:** `picoCTF{y0uv3_3sc4p3d_th3_m4ze...f0r_n0w-hYkq2D9PmrA5GpEq}`

---

## 9. File

| File | Keterangan |
|---|---|
| `matrix` | binary soal (ELF64 stripped) |
| `matrix_vm.py` | loader ELF, disassembler bytecode, emulator VM, ekstraktor peta |
| `solver.py` | BFS di atas state VM + pengiriman ke server |

```console
python3 matrix_vm.py disasm      # disassembly bytecode
python3 matrix_vm.py maze        # gambar peta 16x16
python3 matrix_vm.py run rrrrr   # jalankan VM secara lokal
python3 solver.py --remote       # solve + ambil flag
```

---

## 10. Catatan / Lessons Learned

- **Import yang miskin adalah petunjuk.** Cuma `getc`/`putc`/`fopen` tanpa `strcmp` atau tabel konstanta, tapi output-nya banner panjang yang tak muncul di `strings` → hampir pasti ada interpreter di dalamnya. Cek `main` dulu sebelum menggali fungsi lain.
- **`cmp reg, imm` diikuti `movsxd`/`jmp` dari sebuah tabel = jump table VM.** Handler-nya pendek-pendek dan berakhir `ret` — bacanya cepat, dan sekali ISA lengkap, sisa soal jadi masalah bytecode biasa.
- **Hitung basis RIP-relative dengan teliti.** `lea rdx, [rip+0xca8]` di `0x136d` panjangnya 7 byte, jadi `rip = 0x1374`, bukan `0x136d` — hasilnya `0x201c`, bukan `0x2023` atau `0x2020`. Salah 4 byte bikin seluruh peta opcode bergeser satu slot dan bytecode-nya jadi omong kosong. Kalau disassembly terasa "hampir masuk akal tapi ada yang aneh", curigai basis tabelnya.
- **Kode bisa jadi data.** Labirinnya tidak disimpan sebagai array yang bisa di-`grep`; ia adalah 256 *jump stub* 4 byte. Cara mengenalinya adalah lewat pola alamatnya (`base + 4*idx`), bukan lewat mencari blob data.
- **Emulasikan, jangan reimplementasi.** Menulis ulang VM (±100 baris) lalu BFS di atas state VM jauh lebih aman daripada mengekstrak aturan labirin ke solver terpisah. Solver-ku tidak tahu apa-apa soal kunci atau gerbang — dan justru karena itu ia tidak bisa salah asumsi.
- **Curigai asumsi "game" yang kamu bawa sendiri.** 3 kunci vs 5 gerbang bikin labirin ini tampak mustahil. Yang bikin bisa: handler kunci tidak pernah menghapus petaknya, jadi kunci bisa diperah berulang. Kalau modelmu bilang "tidak ada solusi", biasanya modelmu yang salah, bukan soalnya.

---

### Referensi

- picoCTF — *picoMini by redpwn* (2021), tantangan **MATRIX** oleh asphyxia
- Capstone Engine — framework disassembly (dipakai menggantikan `objdump`)
