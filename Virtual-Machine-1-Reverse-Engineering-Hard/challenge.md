# Virtual Machine 1

- **Kategori:** Reverse Engineering
- **Kesulitan:** Hard
- **Author:** LT 'syreal' Jones
- **Event:** picoCTF 2023

## Deskripsi Asli

> The enemy has upgraded their mechanical analog computer. Start an instance to begin.
>
> We grabbed this design doc from enemy servers: Download. We know that the rotation of the red axle is input and the rotation of the blue axle is output. Reverse engineer the mechanism and get past their checker program:

```text
nc saturn.picoctf.net 52430
```

Alamat di atas adalah instance saat penyelesaian pada 11 September 2026.
Instance bersifat sementara; host atau port untuk percobaan baru perlu
diambil dari halaman challenge.

## Berkas Soal

- [Arsip unduhan asli](Virtual-Machine-1.zip)
- [Model COLLADA hasil ekstraksi](VirtualMachine1.dae)

Arsip hanya berisi `VirtualMachine1.dae`. Source code checker tidak disertakan.

## Hints

1. The supporting structure for the machine has been removed from the given design doc.
2. Some gears are meshed strangely, such as tooth overlapping tooth. Consider such gears as meshed correctly.
3. Learn enough about gear ratios to abstract details from the design doc.
