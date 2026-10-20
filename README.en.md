# Power Metering Protocol Analyzer

**English summary.** A Windows desktop toolkit for Chinese power-line / metering communication protocols — plus international **DLMS/COSEM (IEC 62056)** and **HDLC** — that turns raw hex frames into field-level tables, validates checksums, builds frames, and talks to meters over serial / BLE / TCP.

> This project's primary documentation, UI and issue tracker are in Chinese, because its main audience is engineers working on State Grid / China Southern Power Grid metering equipment. This page is a short orientation for international users; the [Chinese README](README.md) is authoritative.

[![Release](https://img.shields.io/github/v/release/Liruitao1993/South_Network_Protocol_Analysis_Tool?label=release&color=2ea44f)](https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool/releases/latest) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)]()

![Single-frame parsing of a DL/T 698.45 frame](docs/images/readme-single-frame.png)

## Why it might be useful

| Problem on site | What this tool does |
| --- | --- |
| A hex frame is unreadable without flipping through a 300-page standard | Parses **15 protocols** down to field level (A-XDR, BER-TLV, bit fields, timestamps), with **two-way highlighting** between a parsed row and the exact bytes in the input box |
| A capture log has hundreds of frames to sift by eye | **Batch parsing** from file / clipboard / pcap, automatic frame extraction, filtering, and Excel / CSV / JSON export; click a row to jump back to the source line |
| Checksums never match and hand-built frames risk wrong bytes | **Protocol validation** (start chars, length field, checksum, CRC — verdict per item) and **frame generators**; a "mimic this frame" mode back-fills every parameter from a real frame and rebuilds the checksum byte-exactly |
| Too many tools: serial terminal, BLE scanner, packet capture | Serial + **BLE** transceive, BLE⇄serial bridging, **TCP capture with stream reassembly**, and a live monitor — in one program |
| Manual test runs need repeatable evidence | **Test plans** (ordered sending, timeout matching, result recording) plus a **Lua** scripting hook, exporting an Excel report |
| The conclusion must be presented to others | **Sequence diagrams** (concentrator⇄node, PNG export), **frame diff** (byte and field level, with plain-language notes), **spectrum plotting** |

## Protocol coverage

| # | Protocol | Standard | Byte order | Checksum |
| --- | --- | --- | --- | --- |
| 0 | China Southern Power Grid | Q/CSG1209021-2019 | little | octet sum |
| 1 | PLC RF (Wansheng, overseas) | Wansheng V1_04 | big | sum & 0xFF |
| 2 | **HDLC / State Grid DLMS** | **IEC 62056-46** | big | CRC-16/FCS (CCITT) |
| 3 | **DLMS APDU (State Grid)** | **IEC 62056-46** | big | — |
| 4 | **DLMS Wrapper raw** | **IEC 62056-46** | big | — |
| 5 | **DLMS APDU raw** | **IEC 62056-46** | big | — |
| 6 | **DL/T 645-2007 meter protocol** | **DL/T 645-2007** | BCD, LSB first | sum & 0xFF |
| 7 | State Grid Q/GDW 10376 | Q/GDW 10376.2-2024 | little | octet sum |
| 8 | **DL/T 698.45** | **DL/T 698.45-2017** | little (link) / **big (A-XDR)** | CRC-16 (`x-25`) |
| 9 | Next-gen PLC carrier (sensing-integrated) | — | little | CRC-32 (MAC) + CRC-24 (PBCS) |
| 10 | State Grid next-gen dual-mode | — | little | CRC-32 (MAC) |
| 11 | HDC 1.0 dual-mode | Q/GDW 12087.42-2020 | little (MAC big) | CRC-24 + CRC-32 |
| 12 | Modular terminal function module interface | Q/GDW | little / big (A-XDR) | CRC-16/PPP FCS |
| 13 | Yiwa custom 645 | V1.0 | mixed | octet sum (±0x33) |
| 14 | CSG uplink communication | Q/CSG 11109004-2013 | little | octet sum |

Rows 2–6 and 8 are relevant if you work with **DLMS/COSEM** or Chinese meter protocols.

## Download

Windows 10/11 x64, single portable `.exe` (~100 MB, Python runtime embedded). No installer, no Python, no network required.

👉 **[Latest release](https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool/releases/latest)**

First launch takes a few seconds (the one-file build self-extracts to a temp directory). Antivirus false positives are a known PyInstaller one-file artifact — allowlist the file, or build from source with `pyinstaller 南网协议解析工具.spec`.

## Run from source

```bash
pip install pyside6 crcmod lupa openpyxl scapy reflex
python main_gui.py
```

Command line:

```bash
python main_gui.py --parse "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" --protocol 0
python main_gui.py --file sample.log --protocol 2
python main_gui.py --clipboard
```

## Scope and caveats

- The UI, documentation and release notes are Chinese-first. Issues in English are welcome and will be answered in English.
- Some content is specific to Chinese utility practice: `FCCS` / `PBCS` / `ICV` fields are often left zero in test-bench logs (filled by transmitter hardware), so the parser reports "not populated" instead of "checksum failed".
- Not a DLMS client library: it is an analyzer/debugger, not a conforming DLMS stack for production metering.

## Contributing

Issues and PRs are welcome — a frame sample plus the protocol/standard number is the fastest path to a fix. See [AGENTS.md](AGENTS.md) for architecture, byte-order and checksum conventions (Chinese).

## License

[MIT](LICENSE) © 2026 Liruitao
