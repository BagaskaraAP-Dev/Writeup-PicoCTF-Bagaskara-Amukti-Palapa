# Virtual Machine 1 - picoCTF 2023

## Model

Sumber: `VirtualMachine1.dae`, hasil ekstraksi `Virtual-Machine-1.zip`.
COLLADA ini dibuat oleh LeoCAD dan berisi 127 instance komponen LDraw.
Poros merah adalah node 2; poros biru adalah node 120. Nomor node di sini
menggunakan indeks mulai dari nol dalam `library_visual_scenes`.

Komponen utama:

| ID LDraw | Komponen |
| --- | --- |
| 3647 | Gear 8 gigi |
| 4019 | Gear 16 gigi |
| 3648b | Gear 24 gigi |
| 32270 | Gear bevel ganda 12 gigi |
| 6589 | Gear bevel 12 gigi |
| 3649 | Gear 40 gigi |
| 6573 | Rumah diferensial dengan gear 16 dan 24 gigi |

Gear satu poros berputar dengan kecepatan yang sama. Untuk gear yang
bersinggungan, besar rasio putarannya adalah jumlah gigi penggerak dibagi
jumlah gigi yang digerakkan. Kecepatan rumah diferensial adalah rata-rata
kecepatan kedua porosnya, dengan memperhitungkan arah putaran.

## Penyederhanaan

1. Bagian awal menghasilkan dua masukan diferensial dengan besar kecepatan
   6 dan 8 kali input. Rumah diferensial node 21 menghasilkan (6 + 8) / 2 = 7.
2. Cabang tengah pertama menghasilkan kecepatan 18 dan 20 kali input
   bagian tengah. Diferensial node 66 menghasilkan (18 + 20) / 2 = 19.
3. Jalur dari diferensial itu diperbesar 10 kali menjadi 190. Jalur lain
   menghasilkan 192. Diferensial node 84 menghasilkan (190 + 192) / 2 = 191.
4. Bagian akhir mengulang mekanisme 6 dan 8 pada diferensial node 116,
   sehingga memberikan faktor 7 lagi.

Besar rasio keseluruhan: 7 * 191 * 7 = 9359.
Jawaban checker: `output = input * 9359`.

Percobaan awal memakai -9359 dan ditolak. Checker kemudian meminta jeda
360 detik. Solver memakai rasio positif setelah dibandingkan dengan
laporan penyelesaian challenge. Hasil verifikasi langsung berikutnya
tersimpan dalam transkrip checker; flag hanya ditulis jika dikirim server.

## Menjalankan Solver

```powershell
node .\solve.cjs saturn.picoctf.net 52430
```

Jika instance baru memiliki port berbeda, ubah argumen port. Solver membaca
angka input dari server, menghitung dengan BigInt, dan menyimpan flag yang
diterima ke `flag.txt`. Solver tidak mengulangi koneksi secara otomatis.

## Referensi Pembanding

- [Katalog LDraw: gear 8 gigi](https://library.ldraw.org/parts/6669)
- [Katalog LDraw: diferensial 6573](https://library.ldraw.org/parts/list?tableSearch=6573.dat)
- [Write-up peserta, bagian Virtual Machine 1](https://github.com/4C-75-63-6B-79/picoCTF_2023#virtual-machine-1)

Perhitungan berasal dari posisi dan jenis komponen pada berkas lokal.
Write-up dipakai untuk memeriksa penggunaan rasio positif setelah percobaan
bertanda negatif ditolak. Flag dari write-up tidak dipakai sebagai hasil
instance pengguna.

## Verifikasi Langsung

Pada 11 September 2026 sekitar 18:29 WIB, checker di
`saturn.picoctf.net:52430` memberikan input `12044`.
Solver mengirim `12044 * 9359 = 112719796`, lalu server menjawab
`That's correct!` dan mengirim:

```text
picoCTF{m0r3_g34r5_3g4d_4261e7cd}
```

Flag disimpan dalam `flag.txt`. Gambar model dari berkas COLLADA tersedia
di `machine.png` dan dapat dibuat ulang melalui `render-model.ps1`.
