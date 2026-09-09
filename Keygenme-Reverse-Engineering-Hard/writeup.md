# Keygenme

- **Kategori:** Reverse Engineering
- **Kesulitan:** Hard
- **Author:** LT 'syreal' Jones
- **Event:** picoCTF 2022
- **Flag:** `picoCTF{br1ng_y0ur_0wn_k3y_abb48a6c}`

> *"Can you get the flag? Reverse engineer this binary."*

Sebuah ELF 64-bit ter-*strip* yang meminta *license key*. Flag-nya **adalah** license key yang valid — jadi soal ini benar-benar keygen: kunci tidak dibandingkan dengan konstanta, melainkan **dibangun saat runtime** dari dua digest MD5, lalu dicocokkan dengan input kita.

Bagian yang bikin soal ini "Hard" bukan kriptografinya (MD5 dipakai apa adanya, tanpa salt, tanpa iterasi). Yang bikin repot: 8 dari 9 karakter terakhir kunci dipanen lewat **offset stack mentah** seperti `[rbp-0x3b]` dan `[rbp-0x5a]` — bukan lewat indeks array yang enak dibaca. Untuk tahu karakter mana yang diambil, tata letak stack-nya harus direkonstruksi dulu.

---

## 1. Ringkasan Solusi (TL;DR)

1. `main` (`0x148b`) cuma: `printf` prompt → `fgets(buf, 37, stdin)` → panggil validator `0x1209` → cetak valid/invalid.
2. Validator menanam prefix flag sebagai **immediate 64-bit** (`movabs`), bukan string di `.rodata`: `picoCTF{br1ng_y0ur_0wn_k3y_` (27 karakter).
3. Hitung dua MD5 lewat `libcrypto`: `MD5(prefix)` dan `MD5("}")`, lalu ubah keduanya jadi string hex 32 karakter dengan `sprintf("%02x")` ke dua buffer stack yang bersebelahan.
4. Kunci akhir = 27 karakter prefix + **9 byte** yang di-*copy* satu per satu dari offset stack mentah — 8 di antaranya nyomot dari kedua string hex tadi, plus `}` di ujung.
5. Input harus **tepat 36 karakter** (`cmp rax, 0x24`) dan sama persis byte-per-byte.
6. Replay langkah-langkah itu di Python → `picoCTF{br1ng_y0ur_0wn_k3y_abb48a6c}`.

---

## 2. Recon

```console
$ file keygenme
keygenme: ELF 64-bit LSB pie executable, x86-64, dynamically linked,
          interpreter /lib64/ld-linux-x86-64.so.2,
          BuildID[sha1]=054f04db..., for GNU/Linux 3.2.0, stripped
```

`strings` sudah membocorkan banyak:

```
libcrypto.so.1.1          <- OpenSSL
sprintf  strlen  fgets  puts
%02x                      <- format hex
Enter your license key:
That key is valid.
That key is invalid.
picoCTF{H                 <- ???
br1ng_y0H
ur_0wn_kH
```

Tiga potongan terakhir itu jelas prefix flag, tapi perhatikan huruf **`H`** yang menempel di tiap ujungnya. Itu bukan bagian dari flag — itu byte `0x48`, yaitu **prefix REX.W dari instruksi `mov` berikutnya**. Artinya string ini **tidak** disimpan di `.rodata`; ia ditanam sebagai *immediate* di dalam aliran instruksi, dan `strings` kebetulan membacanya sebagai teks karena semua byte-nya printable.

Kombinasi `libcrypto` + `%02x` + `sprintf` langsung memberi bentuk soalnya: ada digest yang di-hex-kan.

---

## 3. `main` — Kerangkanya

Tidak ada `objdump`/`gdb` di mesin saya (Windows), jadi disassembly saya lakukan pakai **capstone** dengan section header ELF di-parse manual:

```python
from capstone import *
md = Cs(CS_ARCH_X86, CS_MODE_64)
for ins in md.disasm(text_bytes, text_vaddr):
    print(f"{ins.address:x}:\t{ins.mnemonic}\t{ins.op_str}")
```

`main` di `0x148b`:

```asm
14ad: lea  rdi, [rip+0xb55]     ; "Enter your license key: "
14b9: call printf
14be: mov  rdx, [rip+0x2b4b]    ; stdin
14c5: lea  rax, [rbp-0x30]
14c9: mov  esi, 0x25            ; 37
14d1: call fgets                ; fgets(buf, 37, stdin)
14dd: call 0x1209               ; <-- validator
14e2: test al, al
14e4: je   0x14f4
14e6: lea  rdi, [rip+0xb35]     ; "That key is valid."
14fb: lea  rdi, [rip+0xb3a]     ; "That key is invalid."
```

Detail kecil yang manis: buffer `fgets` berukuran **37** = panjang kunci + 1. Jadi kalau kita mengetik 36 karakter lalu Enter, `fgets` berhenti tepat di 36 karakter dan **newline-nya tidak ikut masuk** — kalau tidak, `strlen` akan jadi 37 dan cek panjang gagal. Ukurannya memang dipilih pas.

Semua logika ada di `0x1209`.

---

## 4. Validator `0x1209`

### 4.1 Prefix Ditanam sebagai Immediate

```asm
122e: movabs rax, 0x7b4654436f636970
1238: movabs rdx, 0x30795f676e317262
1242: mov    [rbp-0x90], rax
1249: mov    [rbp-0x88], rdx
1250: movabs rax, 0x6b5f6e77305f7275
125a: mov    [rbp-0x80], rax
125e: mov    dword [rbp-0x78], 0x5f7933
1265: mov    word  [rbp-0xb2], 0x7d
```

Dibaca little-endian:

| immediate | byte | teks |
|---|---|---|
| `0x7b4654436f636970` | `70 69 63 6f 43 54 46 7b` | `picoCTF{` |
| `0x30795f676e317262` | `62 72 31 6e 67 5f 79 30` | `br1ng_y0` |
| `0x6b5f6e77305f7275` | `75 72 5f 30 77 6e 5f 6b` | `ur_0wn_k` |
| `0x5f7933` (dword) | `33 79 5f 00` | `3y_` + NUL |
| `0x7d` (word) | `7d 00` | `}` + NUL |

Jadi di `rbp-0x90` ada string **`picoCTF{br1ng_y0ur_0wn_k3y_`** (27 karakter), dan di `rbp-0xb2` ada string satu karakter **`}`**.

### 4.2 Dua MD5

```asm
126e: lea  rax, [rbp-0x90]
1278: call strlen              ; -> 27
1280: lea  rdx, [rbp-0xb0]     ; output
1287: lea  rax, [rbp-0x90]     ; input
1294: call 0x10f0              ; MD5(prefix, 27, rbp-0xb0)

1299: lea  rax, [rbp-0xb2]
12a3: call strlen              ; -> 1
12ab: lea  rdx, [rbp-0xa0]
12b2: lea  rax, [rbp-0xb2]
12bf: call 0x10f0              ; MD5("}", 1, rbp-0xa0)
```

Fungsi `0x10f0` dipanggil dengan pola `(data, len, out)` dan hasilnya nanti diformat sebagai 16 byte — persis tanda tangan OpenSSL `MD5(const unsigned char *d, size_t n, unsigned char *md)`. Digest mentahnya 16 byte, dan loop `%02x` berikutnya berjalan `i = 0..15`, konsisten.

### 4.3 Hex-kan Keduanya

```asm
; loop 1: i = 0..15
12e2: movzx eax, byte [rbp+rax-0xb0]     ; digest1[i]
12ed: lea   rcx, [rbp-0x70]
12fa: add   rcx, rdx                     ; rdx = 2*i
12ff: lea   rsi, [rip+0xcfe]             ; "%02x"
130e: call  sprintf                      ; sprintf(rbp-0x70 + 2i, "%02x", digest1[i])
1321: cmp   dword [rbp-0xc4], 0xf
1328: jle   0x12da

; loop 2: sama persis, digest2 -> rbp-0x50
```

Hasilnya dua string hex 32 karakter:

- **`hex1`** di `rbp-0x70` = hex dari `MD5("picoCTF{br1ng_y0ur_0wn_k3y_")`
- **`hex2`** di `rbp-0x50` = hex dari `MD5("}")`

⚠️ Kedua buffer ini **bersebelahan persis**. `hex1` mengisi `rbp-0x70` sampai `rbp-0x51`, dan NUL dari `sprintf` terakhirnya mendarat di `rbp-0x50` — yang **langsung ditimpa** oleh karakter pertama `hex2`. Hal yang sama terulang di ujung `hex2`. Tidak ada bug di sini, tapi ini yang membuat "tebak indeksnya" jadi rawan salah: `rbp-0x50` bisa dibaca sebagai `hex1[32]` **atau** `hex2[0]`, dan cuma tata letak yang menjawabnya.

### 4.4 Rakit Kunci

```asm
; salin 27 byte prefix -> buffer kunci di rbp-0x30
139c: movzx edx, byte [rbp+rax-0x90]
13b4: mov   [rbp+rax-0x30], dl
13bf: cmp   dword [rbp-0xbc], 0x1a       ; i <= 26
13c6: jle   0x139c
```

Lalu 9 byte terakhir — inti soalnya:

```asm
13c8: movzx eax, byte [rbp-0x3b]  |  13cc: mov [rbp-0x15], al
13cf: movzx eax, byte [rbp-0x5a]  |  13d3: mov [rbp-0x14], al
13d6: movzx eax, byte [rbp-0x5a]  |  13da: mov [rbp-0x13], al
13dd: movzx eax, byte [rbp-0x70]  |  13e1: mov [rbp-0x12], al
13e4: movzx eax, byte [rbp-0x53]  |  13e8: mov [rbp-0x11], al
13eb: movzx eax, byte [rbp-0x3b]  |  13ef: mov [rbp-0x10], al
13f2: movzx eax, byte [rbp-0x62]  |  13f6: mov [rbp-0xf],  al
13f9: movzx eax, byte [rbp-0x58]  |  13fd: mov [rbp-0xe],  al
1400: movzx eax, byte [rbp-0xb2]  |  1407: mov [rbp-0xd],  al
```

Tujuannya (`rbp-0x15` … `rbp-0xd`) sembilan byte berurutan, dan `rbp-0x30 + 27 = rbp-0x15` — tepat menyambung prefix. Total **27 + 9 = 36 = 0x24**.

### 4.5 Pengecekan

```asm
1414: call strlen
1419: cmp  rax, 0x24            ; panjang harus 36
141d: je   0x1426
141f: mov  eax, 0               ; kalau tidak -> invalid

1445: movzx edx, byte [rax]           ; input[i]
1450: movzx eax, byte [rbp+rax-0x30]  ; kunci[i]
1455: cmp  dl, al
1457: je   0x1460
1459: mov  eax, 0               ; beda -> invalid
1467: cmp  dword [rbp-0xb8], 0x23
146e: jle  0x1432
1470: mov  eax, 1               ; cocok semua -> valid
```

Perbandingan byte-per-byte biasa, tanpa *early exit* yang bocor timing dan tanpa transformasi apa pun pada input. Jadi kunci benar-benar ditentukan sepenuhnya oleh binary — tidak ada masukan eksternal.

---

## 5. Merekonstruksi Tata Letak Stack

Ini kunci untuk menerjemahkan `[rbp-0x3b]` dan kawan-kawan. Dari semua penulisan di atas:

| offset | isi | rentang |
|---|---|---|
| `rbp-0xb2` | `"}"` + NUL | `-0xb2 … -0xb1` |
| `rbp-0xb0` | digest MD5 #1 mentah (16 byte) | `-0xb0 … -0xa1` |
| `rbp-0xa0` | digest MD5 #2 mentah (16 byte) | `-0xa0 … -0x91` |
| `rbp-0x90` | `"picoCTF{br1ng_y0ur_0wn_k3y_"` + NUL | `-0x90 … -0x75` |
| `rbp-0x70` | **`hex1`** — 32 char | `-0x70 … -0x51` |
| `rbp-0x50` | **`hex2`** — 32 char | `-0x50 … -0x31` |
| `rbp-0x30` | buffer kunci akhir (36 byte) | `-0x30 … -0x0d` |

Konversi offset → indeks jadi gampang:

- ada di `-0x70 … -0x51` → `hex1[offset + 0x70]`
- ada di `-0x50 … -0x31` → `hex2[offset + 0x50]`

Dengan

```
hex1 = 438218d572e90162d0981cbbc7d43882
hex2 = cbb184dd8e05c9709e5dcaedaa0495cf
```

sembilan byte terakhir terbaca:

| # | instruksi | sumber | indeks | karakter |
|---|---|---|---|---|
| 27 | `[rbp-0x3b]` | `hex2` | `[21]` | `a` |
| 28 | `[rbp-0x5a]` | `hex1` | `[22]` | `b` |
| 29 | `[rbp-0x5a]` | `hex1` | `[22]` | `b` |
| 30 | `[rbp-0x70]` | `hex1` | `[0]`  | `4` |
| 31 | `[rbp-0x53]` | `hex1` | `[29]` | `8` |
| 32 | `[rbp-0x3b]` | `hex2` | `[21]` | `a` |
| 33 | `[rbp-0x62]` | `hex1` | `[14]` | `6` |
| 34 | `[rbp-0x58]` | `hex1` | `[24]` | `c` |
| 35 | `[rbp-0xb2]` | literal | — | `}` |

Ekornya: **`abb48a6c}`**

Perhatikan hanya **satu** karakter (`a`, dua kali) yang datang dari `hex2`; sisanya dari `hex1`. `MD5("}")` sebenarnya nyaris tidak terpakai — ia ada terutama untuk memaksa kita memodelkan dua buffer yang bersebelahan itu dengan benar.

---

## 6. Keygen

Daripada menyalin hasil akhirnya, `keygen.py` **menirukan validator secara harfiah**: stack palsu berupa dict `offset → byte`, lalu setiap penulisan direplay dengan urutan yang sama seperti binary (termasuk NUL dari `sprintf` yang saling menimpa).

```python
mem = {}

# 0x122e-0x1265 : konstanta movabs
wr(-0x90, (0x7B4654436F636970).to_bytes(8, "little"))  # "picoCTF{"
wr(-0x88, (0x30795F676E317262).to_bytes(8, "little"))  # "br1ng_y0"
wr(-0x80, (0x6B5F6E77305F7275).to_bytes(8, "little"))  # "ur_0wn_k"
wr(-0x78, (0x5F7933).to_bytes(4, "little"))            # "3y_\0"
wr(-0xB2, (0x7D).to_bytes(2, "little"))                # "}\0"

# 0x126e-0x12bf : dua MD5
wr(-0xB0, hashlib.md5(rd(-0x90, strlen(-0x90))).digest())
wr(-0xA0, hashlib.md5(rd(-0xB2, strlen(-0xB2))).digest())

# 0x12da-0x138e : sprintf("%02x") -> dua buffer bersebelahan
for i in range(16):
    wr(-0x70 + 2 * i, ("%02x" % mem[-0xB0 + i]).encode() + b"\x00")
for i in range(16):
    wr(-0x50 + 2 * i, ("%02x" % mem[-0xA0 + i]).encode() + b"\x00")

# 0x139c-0x13c6 : salin prefix
for i in range(0x1B):
    mem[-0x30 + i] = mem[-0x90 + i]

# 0x13c8-0x1407 : 9 byte dari offset stack mentah
for dst, src in [(-0x15,-0x3B), (-0x14,-0x5A), (-0x13,-0x5A), (-0x12,-0x70),
                 (-0x11,-0x53), (-0x10,-0x3B), (-0x0F,-0x62), (-0x0E,-0x58),
                 (-0x0D,-0xB2)]:
    mem[dst] = mem[src]

KEY = rd(-0x30, 0x24)
```

Enaknya cara ini: aku tidak perlu memutuskan sendiri `[rbp-0x3b]` itu `hex1` atau `hex2`. Tata letaknya muncul sendiri dari urutan penulisan, persis seperti di binary.

```console
$ python3 keygen.py
picoCTF{br1ng_y0ur_0wn_k3y_abb48a6c}

$ python3 keygen.py -v
prefix        : picoCTF{br1ng_y0ur_0wn_k3y_
MD5(prefix)   : 438218d572e90162d0981cbbc7d43882   <- rbp-0x70
MD5("}")      : cbb184dd8e05c9709e5dcaedaa0495cf   <- rbp-0x50

9 byte terakhir:
  key[27] <- [rbp-0x15] <- [rbp-0x3b]  = hex2[21] = 'a'
  key[28] <- [rbp-0x14] <- [rbp-0x5a]  = hex1[22] = 'b'
  key[29] <- [rbp-0x13] <- [rbp-0x5a]  = hex1[22] = 'b'
  key[30] <- [rbp-0x12] <- [rbp-0x70]  = hex1[ 0] = '4'
  key[31] <- [rbp-0x11] <- [rbp-0x53]  = hex1[29] = '8'
  key[32] <- [rbp-0x10] <- [rbp-0x3b]  = hex2[21] = 'a'
  key[33] <- [rbp-0x0f] <- [rbp-0x62]  = hex1[14] = '6'
  key[34] <- [rbp-0x0e] <- [rbp-0x58]  = hex1[24] = 'c'
  key[35] <- [rbp-0x0d] <- [rbp-0xb2]  = literal '}' = '}'
```

---

## 7. Verifikasi dengan Binary Aslinya

Analisis statis saja belum cukup meyakinkan — saya jalankan binary-nya. Saya di Windows, jadi lewat WSL. Kendalanya: binary butuh `libcrypto.so.1.1` (OpenSSL 1.1), sedangkan Kali sekarang cuma punya `libcrypto.so.3`.

```console
$ ldd keygenme
        libcrypto.so.1.1 => not found
```

Simbol yang dipakai cuma **satu** (`MD5`), jadi tidak perlu memasang OpenSSL 1.1 — cukup buat *shim* mungil yang mengekspor `MD5` dengan tag versi `OPENSSL_1_1_0`, lalu meneruskannya ke EVP milik OpenSSL 3:

```c
/* shim.c */
#include <openssl/evp.h>
#include <stddef.h>
unsigned char *MD5(const unsigned char *d, size_t n, unsigned char *md) {
    static unsigned char buf[16];
    unsigned int len = 16;
    if (!md) md = buf;
    EVP_Digest(d, n, md, &len, EVP_md5(), NULL);
    return md;
}
```

```
/* ver.map — versioned symbol wajib, kalau tidak dynamic linker menolak */
OPENSSL_1_1_0 { global: MD5; local: *; };
```

```console
$ gcc -shared -fPIC -o libcrypto.so.1.1 shim.c -Wl,--version-script=ver.map -lcrypto
$ echo 'picoCTF{br1ng_y0ur_0wn_k3y_abb48a6c}' | LD_LIBRARY_PATH=. ./keygenme
Enter your license key: That key is valid.

$ echo 'picoCTF{br1ng_y0ur_0wn_k3y_deadbeef}' | LD_LIBRARY_PATH=. ./keygenme
Enter your license key: That key is invalid.
```

**Flag:** `picoCTF{br1ng_y0ur_0wn_k3y_abb48a6c}`

---

## 8. File

| File | Keterangan |
|---|---|
| `keygenme` | binary soal (ELF64 stripped, PIE) |
| `keygen.py` | keygen — replay validator lewat simulasi stack |

```console
python3 keygen.py         # cetak kunci
python3 keygen.py -v      # tampilkan langkah antara
```

---

## 9. Catatan / Lessons Learned

- **String yang "hampir bersih" di `strings` itu petunjuk.** `picoCTF{H`, `br1ng_y0H`, `ur_0wn_kH` — huruf `H` yang menempel adalah byte REX.W (`0x48`) dari instruksi berikutnya, tanda bahwa string itu ditanam sebagai *immediate* `movabs`, bukan data di `.rodata`. Kalau string flag muncul terpotong-potong per 8 byte, hampir pasti pola ini.
- **Ukuran buffer bisa jadi bagian dari soal.** `fgets(buf, 37, stdin)` bukan angka sembarangan: 36 karakter kunci + 1, pas supaya newline tidak ikut terbaca dan `strlen` tetap 36.
- **Offset stack mentah harus dipetakan, bukan ditebak.** `[rbp-0x3b]` tidak berarti apa-apa sampai kamu tahu buffer mana yang menempati alamat itu. Bikin tabel tata letak stack dulu — apalagi kalau ada dua buffer bersebelahan yang NUL-nya saling menimpa, di mana satu alamat bisa dibaca sebagai akhir buffer A atau awal buffer B.
- **Replay, jangan simpulkan.** Menirukan urutan penulisan ke stack palsu (`dict` offset → byte) lebih aman daripada menyimpulkan "karakter ke-N dari hash". Simulasinya menghasilkan tata letak yang sama dengan binary secara otomatis, jadi salah baca offset ketahuan sendiri.
- **Dependensi library lawas tidak selalu jadi penghalang.** Kalau binary cuma memakai satu-dua simbol, bikin *shim* ber-versi jauh lebih cepat daripada memasang ulang OpenSSL 1.1 — asal jangan lupa `--version-script`, karena dynamic linker mencocokkan **simbol berversi** (`MD5@OPENSSL_1_1_0`), bukan sekadar nama.
- **Menjalankan binary tetap langkah terakhir yang layak.** Analisis statis saya sudah benar, tapi konfirmasi "That key is valid." vs "That key is invalid." yang menutup kemungkinan salah baca offset.

---

### Referensi

- picoCTF 2022 — tantangan **Keygenme** oleh LT 'syreal' Jones
- Capstone Engine — framework disassembly (dipakai menggantikan `objdump`)
- OpenSSL — `MD5(3)` dan *symbol versioning* pada `libcrypto`
