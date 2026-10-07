# Firmware, Embedded, and Hardware Reverse Engineering

Everything below the operating system. This is the layer where a device's security
properties are actually decided, and where the tooling is least standardized.

**Scope note**: hardware research has real physical and legal boundaries. Reading a flash
chip you own is different from reading one in a device you do not own. Automotive work
touches safety-critical systems. The authorization question is sharper here than anywhere
else in this skill — see [`compliance-and-scope.md`](compliance-and-scope.md) and §8 below.

---

## 1. Acquisition

You cannot analyse firmware you cannot read. Acquisition is usually the hard part.

### Software routes (try these first — no hardware needed)

| Route | How |
|---|---|
| **Vendor download portal** | Many vendors publish firmware updates openly. Search the support site before touching hardware. |
| **OTA update interception** | MITM the device's update check. Often the update URL is in a config file or a plain HTTP request. |
| **Companion app** | The mobile app often downloads and pushes firmware. Extract from the app's cache. |
| **Cloud API** | Some ecosystems serve firmware via an API with weak or no authentication. |
| **Update package from the update server** | Frequently a zip/tar containing the filesystem image. |

**Check for a software route first.** It is an order of magnitude less work than
hardware, and it is often available because vendors do not consider the update channel a
secret.

### Hardware interfaces

| Interface | Use | Tooling |
|---|---|---|
| **UART** | Serial console — often drops to a shell or bootloader | USB-TTL adapter (CP2102, FT232, CH340), `picocom`/`screen`/`minicom`, baud rate sweep |
| **JTAG** | Full CPU debug and memory access | OpenOCD, J-Link, Bus Pirate, JTAGulator (pin discovery) |
| **SWD** | ARM's 2-wire debug | OpenOCD, J-Link, ST-Link, Black Magic Probe |
| **SPI flash** | In-circuit or chip-off read of the firmware chip | CH341A programmer, flashrom, Bus Pirate, SOIC-8 clip |
| **I2C / eMMC / NAND** | Larger storage, embedded EEPROM | Dedicated readers; eMMC needs a specific adapter and often BGA rework |
| **Logic analyser** | Protocol decoding, pin discovery | Saleae, sigrok/PulseView (open source), DSLogic |
| **Glitching** | Fault injection to bypass secure boot | ChipWhisperer, voltage/clock glitching |

**`flashrom` is the workhorse** for SPI flash: it supports hundreds of chips and both
in-circuit (with a clip) and chip-off reading. The standard first hardware attempt is a
SOIC-8 clip on the flash chip with `flashrom -p ch341a_spi -r dump.bin`.

**Finding the pins** on an unknown board:

1. Look for a 4-pin header or unpopulated pads — often labelled `TX RX GND VCC` or
   `J1`/`CN1`.
2. Use a multimeter to identify ground (continuity to a known ground plane) and VCC
   (~3.3 V when powered).
3. For UART: identify the TX pin by watching for activity at boot with a logic analyser,
   or by sweeping baud rates and looking for readable output. RX is the other data pin.
4. **Never connect VCC from your adapter if the board is already powered.** Power the
   board normally and connect only GND/TX/RX.

### Secure boot and readout protection

These are what stop acquisition. **The most important 2025–2026 development is that
several long-assumed "locked means safe" protections have documented bypasses**, so treat
the table below as a starting point for verification, not as a guarantee.

| Protection | Device | Status | Research approach |
|---|---|---|---|
| **ESP32 ECDSA Secure Boot** | ESP32-H2/C5/C61/P4/S31 | **Active, unfixed defect** | Espressif advisory **AR2026-006 (V1.1, 2026-07-28)**: the ROM ECDSA secure boot does **not validate that the signature components r and s fall within the curve order**, so an invalid signature can be judged valid. ESP32-C5 additionally has an uninitialized ECDSA peripheral in ROM. **No software fix on current silicon**; hardware fix awaits a future tape-out. C2/C6 are unaffected (no ECDSA peripheral). Mitigation for new production: use RSA secure boot. ESP32-C61 has ECDSA only and no application-level workaround. |
| **STM32 RDP** | STM32 | **Level 2 is not an absolute barrier** | Level 1 has public glitching bypasses. For level 2: a boot-time voltage glitch can cause the RDP byte to be misread as level 1 (reopening debug and the system bootloader), then a second glitch skips the level-1 read check. See SECGlitcher (SEC Consult, 2024-01), Anvil Secure's end-to-end demo (2025-04), VoidStar's EMFI variant (CanSecWest 2024), and `joegrand/stm32-fault-injection`. Separately, **STM32-TraceRip** (Hardwear.io USA 2025) claims full application flash recovery on STM32G0 by observing CPU state during normal execution — no glitching or UV. ST's own **TN1489 (2023-10)** states that parts without SESIP/PSA certification covering physical attacks may be affected by FI, side-channel, and invasive attacks. |
| **nRF52 APPROTECT** | Nordic nRF52 | Bypassed on early revisions | LimitedResults' 2020 voltage glitch perturbs APPROTECT during boot and reopens SWD (Nordic advisory IN-133 / CVE-2020-27211). Later nRF52 revisions default it on and add a second software+hardware lock. |
| **nRF54L** | Nordic nRF54L | Hardened, but the vendor does not claim certainty | TAMPC glitch detection (voltage/EM timing violations → reset), a dedicated GLITCHDET supply pin, signal protectors, optional active shielding, and CRACEN (DPA masking plus fault checks on public-key operations). `UICR.ERASEPROTECT` blocks CTRL-AP `ERASEALL` recovery. **Nordic itself states glitch detection is not deterministic**, and a SySS 2025 report found the detector did not reliably block some EMFI. nRF54H20 uses lifecycle states rather than APPROTECT. The public PSA certificate (2026-01, SDK 3.1) is **Level 1, not Level 3**. |
| **ESP32 flash encryption + secure boot** | ESP32 (V3) | Bypassed | USENIX WOOT 2024 (Delvaux): a single EM glitch bypasses both secure boot and flash encryption simultaneously, entering ROM download mode to export decrypted flash. Espressif **AR2023-007** documents a CPA + FI combination on ESP32-C3/C6; there is also a public reproduction of a crowbar voltage glitch bypassing encrypted secure boot. |
| **MediaTek** | MediaTek SoCs | Multiple findings | The `bl2_ext` verification gap (Fenrir, ~2025): when `seccfg` is unlocked the Preloader can skip the `bl2_ext` signature check, but `bl2_ext` is what performs downstream verification at EL3 — so the trust chain collapses. Confirmed on Nothing Phone (2a) and CMF Phone 1. DA vulnerabilities CVE-2025-20656 (OOB write) and CVE-2025-20658 (privilege bypass), disclosed 2025-04. Hardwear.io NL 2025 performed EMFI on MT6878 to dump BootROM and reach EL3 code execution. **BootROM defects cannot be fixed by OTA.** |
| **Qualcomm** | Qualcomm SoCs | CVE-2026-25262 | PBL writes to an arbitrary address while processing a crafted ELF, related to EDL Sahara. Affects MDM9x07/9x45/9x65, MSM8909/8916/8952, SDX50. Reported 2025-03; Kaspersky presented related BootROM/Sahara analysis at Black Hat Asia 2026. Separately, **AVBTestKeyInTheWild** (EWSN/SPICES 2025) found real vendor firmware shipping with residual AOSP AVB test keys — the published private key lets images be re-signed and pass AVB. That is a signing/supply-chain failure, not a cryptographic break. |
| **ESP8266** | Espressif | Generally readable | Straightforward dump in most cases |
| **Broadcom** | Broadcom SoCs | **Not established** | No first-hand 2025–2026 material of comparable grade was located. **Absence of evidence is not evidence of absence** — treat as unknown rather than secure. |
| **Fuses / OTP** | Various | One-time programmable | Irreversible; the route is glitching or decapsulation |

**The operational consequence, stated plainly**: an assumption of the form "RDP2 is set /
APPROTECT is locked / the eFuse is blown, therefore the device is secure" does not hold for
parts that lack SESIP/PSA certification covering physical attacks. Verify per silicon
revision against current advisories rather than reasoning from the feature name.

The honest position: **if secure boot is properly implemented and the debug interface is
permanently locked, you are in glitching or decapsulation territory**, which is a
specialist discipline with real equipment cost. Do not promise a client that a locked
device will be readable.

### Firmware update formats

Two standardised lines worth recognising before you treat an update package as a black box:

- **IETF SUIT** — RFC 9019 (architecture), RFC 9124 (information model), current
  serialisation is the `draft-ietf-suit-manifest` CBOR manifest. A SUIT Envelope is the
  manifest digest plus a COSE_Sign/Sign1/Mac/Mac0 structure. Encrypted payloads are
  covered by `draft-ietf-suit-firmware-encryption`, and **changing the encryption structure
  requires re-signing**.
- **MCUboot** — a 32-byte little-endian header with magic `0x96f3b83d`, TLV info magics
  `0x6907` / `0x6908`, and a signature covering header + payload + protected TLV.
  `imgtool` signs and parses.

Vendor-private containers have no common 2025 format and must be identified per device.
Note also that a 2026 *Computers & Security* study of ~50 consumer devices still found
plaintext HTTP update channels in many of them — **capturing an update is frequently less
work than reading a chip.**

Sources: https://www.rfc-editor.org/rfc/rfc9019 ,
https://datatracker.ietf.org/doc/draft-ietf-suit-manifest/ ,
https://github.com/mcu-tools/mcuboot/blob/main/docs/design.md

---

## 2. Extraction and analysis

### Carving and unpacking

| Tool | Status (verified 2026-10) | Notes |
|---|---|---|
| **binwalk** | **Upstream near-stalled** | Latest tag is still **v3.1.0 (2024-10-31)**; master commits continue (2026-08) and `Cargo.toml` says 3.1.1, but **it was never tagged or published to crates.io**. Issue #935 (2026-02-13, "Project status and a new fork") says the project is unmaintained. |
| **binwalk-ng** | **Active, v4.0.0 (2026-09-29)** | Community fork (crate `binwalk-ng`, CLI still `binwalk`). Adds lzfse/zstd/lz4/rar/tar/SREC/Fritz!Box EVA/Broadcom ProgramStore handlers, mmap, rayon parallelism, and symlink-escape hardening. **The fork's ownership status is unconfirmed** — there is no handover announcement from ReFirmLabs/devttys0. |
| **unblob** | **Active, 26.6.4 (2026-06-04)** | YY.M.D versioning; main active through 2026-10. Adds minix, BTRFS stream, UFS1-2, Moxa FRM, Tesla Wall Connector SBFH, and an Airoha handler. ~20 external dependencies (binwalk needs none). |
| **sasquatch** | **Use the onekey-sec fork** | `devttys0/sasquatch` is stalled (last commit 2021-03, still patches squashfs-tools 4.3, many unmerged PRs). **`onekey-sec/sasquatch` is the maintained successor** (sasquatch-v4.5.1-6, 2026-01-27) — and it is what unblob installs. |
| **FACT** | **Active, v4.4.1 (2026-09-14)** | Fraunhofer FKIE. Note: the `FACT_docker` repo README states it is **currently unmaintained** — use the script install or Vagrant instead. Requires Python 3.10–3.12. |
| **EMBA** | **Active, v2.0.4 (2026-09-21)** | Notably **migrated from binwalk to binwalk-ng**. v2.0.0 (2025-12) claims 95% emulation success versus Firmadyne/FirmAE. SBOM generation with `cve-bin-tool`, VEX support, CISA minimum SBOM elements. |
| **firmwalker** | **Repository gone** | `craigz28/firmwalker` returns **HTTP 404**; the 2026-01-09 Wayback snapshot is still viewable (~1.2k stars). Use the `scriptingxss/firmwalker` or `zhibx/firmwalker_pro` mirrors. |
| **Trommel** | **Archived 2024-05-13** | `CERTCC/trommel` (CMU SEI — not CISA) is read-only; last commit 2020-06-23. |
| **Firmadyne / FirmAE** | Firmadyne stalled; FirmAE maintained | Firmadyne's last commit was 2024-07. FirmAE's only tag is still v1.0 (2020) with dependency/fix commits through 2026-06 — maintenance, not new releases. EMBA's wiki states neither is actively maintained. |
| **Practical order** | — | **unblob first, binwalk-ng to fill gaps.** |

**Do not trust a single extractor.** Filesystem extraction fails silently more often than
it fails loudly — you get a partial filesystem and do not notice the missing files. Verify
extraction completeness (file count, total size, presence of expected binaries) rather
than assuming success.

### Filesystem types in firmware

| Filesystem | Tool | Gotcha |
|---|---|---|
| **SquashFS** | `unsquashfs`, or **sasquatch** (patched for vendor modifications) | Vendors ship non-standard compression (LZMA variants, LZO, ZSTD) and modified headers that stock `unsquashfs` rejects. This is the single most common extraction failure. |
| **JFFS2** | `jefferson`, `mkfs.jffs2` | Needs the erase block size; wrong value produces garbage |
| **UBIFS** | `ubireader` | Requires the UBI volume layout first |
| **CramFS** | `cramfsck` | Old, common in cheap devices |
| **ext2/3/4** | `debugfs`, mount | Easy case |
| **YAFFS** | `unyaffs` | NAND-specific |
| **ROMFS** | `genromfs` / manual | Simple format |
| **ubi / ubiFS** | `ubireader_extract_images`, then `ubireader_extract_files` | Two-stage: UBI container, then UBIFS inside |

Entropy analysis per region is the fast way to find filesystem boundaries in an unknown
blob: compressed/encrypted regions show ~8.0, headers and tables show much lower.

### Binary analysis of embedded targets

Firmware binaries are usually **ARM (32/64), MIPS (big or little endian), RISC-V, or
Xtensa (ESP32)**.

| Target | Notes |
|---|---|
| **ARM Cortex-M bare metal** | Vector table at address 0 (or offset). The first word is the initial stack pointer, the second is the reset handler. Ghidra needs the base address set correctly or every reference is wrong. |
| **MIPS** | Endianness confusion is the classic trap. Check the ELF header; many routers are big-endian MIPS. |
| **Xtensa (ESP32)** | Ghidra support is limited; `esp32_image_parser` and Espressif's own tooling are usually faster. |
| **RISC-V** | Ghidra and radare2 both support it; tooling is younger. |

Practical workflow:

1. `file` the extracted binaries to get architecture and endianness.
2. Load into Ghidra with the **correct base address**. For bare-metal ARM, if the vector
   table is at 0x08000000, load there — not at 0.
3. Look for the RTOS (see below) to understand the calling conventions in use.
4. Anchor on strings and the network/update code paths — those are the ones that matter
   for security assessment.

### Emulation

Emulation is how you get dynamic analysis without hardware, and it fails in predictable
ways.

| Tool | Status (verified 2026-10) | Scope |
|---|---|---|
| **QEMU (system mode)** | Active, 11.1.2 (2026-09-28) | Full system emulation; the basis of most firmware emulation |
| **Firmadyne** | **Stalled** — no commits after 2024-07 | Automated QEMU-based firmware emulation; historically important |
| **FirmAE** | Maintained but no new release (only tag still v1.0 from 2020; fix commits through 2026-06) | Better success rate on real firmware than Firmadyne |
| **Qiling** | Active, v1.4.11 (2026-09-06) | OS-level API emulation; user-mode and partial system. Recently added RISC-V debugging/qdb and `clone3` support |
| **unicorn** | Release lagging (2.1.4, 2025-09) but `dev` active through 2026-08 | CPU-only emulation; you provide the OS semantics |
| **EMBA's emulation** | Active | Integrated into the analysis pipeline |

**Common failure modes** (expect these, they are the norm rather than the exception):

- **NVRAM** — the firmware expects a non-volatile config store that does not exist in the
  emulated environment. The web server fails to start.
- **Missing hardware peripherals** — a GPIO or watchdog register read returns 0 and the
  init sequence hangs.
- **Watchdog timers** — the firmware resets itself because the emulated watchdog is not
  being fed.
- **Hardcoded flash addresses** — code that assumes it is memory-mapped at a physical
  address that the emulator has not mapped.
- **Kernel version mismatch** — the firmware's kernel modules do not load in a generic
  kernel.

The practical fix for many of these is **user-mode emulation of the individual binary**
rather than full-system: `qemu-arm ./httpd` with `LD_PRELOAD` shims for the missing
interfaces. It is more manual but far more likely to work.

### Identifying the RTOS

| RTOS | Fingerprint |
|---|---|
| **FreeRTOS** | `xTaskCreate`, `vTaskStartScheduler`, `vTaskDelay`, `pvPortMalloc`; `configASSERT`; `pxCurrentTCB` when not stripped |
| **Zephyr** | `k_thread_create` / `k_sem_give` and other `k_*` symbols, `z_` prefixes, the `_kernel` symbol. The device model relies heavily on linker iterable sections and `SYS_INIT`, so **missing direct cross-references is normal**, not a sign of a wrong identification. |
| **VxWorks** | `taskSpawn`, `semTake`, `msgQSend`, `wdbAgent`; a `WIND version` banner; task names `tIdle` / `tRootTask`. **Often ships an embedded symbol table** — binwalk has a "VxWorks symbol table" signature that scans from the image tail, and the load base can be derived from (string virtual address − file offset). This makes VxWorks the most reliably fingerprintable RTOS of the set. |
| **ThreadX (Azure RTOS)** | `tx_thread_create`, `tx_kernel_enter`, `tx_queue_*`; the TCB ID constant `TX_THREAD_ID = 0x54485244` ("THRD"); version string `_tx_version_id` |
| **ESP-IDF (FreeRTOS-based)** | `esp_` prefixes, `IDF` version strings |
| **bare metal** | No scheduler symbols; a main loop and interrupt vectors |

RTOS identification tells you the calling conventions, the memory model, and where to look
for task structure — it is worth the five minutes.

**The realistic constraint**: assert strings, log strings, and task names are frequently
compiled out. String and symbol matching is therefore **confirmatory rather than
decisive** — absence proves nothing. Where strings are gone, the working approach is
decompiled-function-shape matching against known library signatures.

### Embedded binary analysis specifics

Two Ghidra details that change the workflow:

- **Ghidra natively supports Xtensa from 11.0** (language `Xtensa:LE:32:default`; version
  12.x uses language version ~4.1). Some relocations such as `R_XTENSA_SLOT0_OP` remain
  incomplete. This makes the third-party `ghidra-xtensa` plugins **obsolete on Ghidra
  ≥ 11.0** — do not install them on a modern Ghidra.
- **Loading a flash image**: use `saibotk/ghidra-esp32-flash-loader` (or the dynacylabs
  fork), or convert to ELF first with `tenable/esp32_image_parser`.
- **SVD files**: Ghidra has no built-in importer. The maintained option is **GhidraSVD
  v0.6.6 (2026-09)**. Prefer `esp-rs/esp-pacs` as the SVD source — the official
  `espressif/svd` is out of date. On Ghidra 12, the older Python SVD-Loader must be
  launched via `support/pyghidraRun`.

---

## 3. Hardware attack surfaces

Beyond reading memory, the physical interfaces themselves are attack surfaces.

### Side-channel and fault injection

| Technique | What it recovers | Equipment |
|---|---|---|
| **Power analysis (SPA/DPA)** | Cryptographic keys from a running device | ChipWhisperer, oscilloscope, shunt resistor |
| **Electromagnetic analysis** | Same, without contact | EM probe + scope |
| **Voltage glitching** | Secure boot bypass, RDP bypass, fault-injection to skip a check | ChipWhisperer, crowbar circuits |
| **Clock glitching** | Similar, timing-based | ChipWhisperer |
| **Laser fault injection** | Precise bit flips | Specialist lab equipment (decapsulation + laser) |

**The cost gradient is steep.** ChipWhisperer makes power analysis and glitching
accessible to a well-equipped hobbyist. Laser fault injection is a laboratory capability.

Hardware note: **ChipWhisperer-Pro is discontinued**; the current flagship is
**HuskyPlus** (Artix-7 A100T, ADS4129 250 MS/s, 327,828-sample buffer, 4-level triggering,
~$1100), supported by software from **6.0.0 (2025-03-26)**. The Husky (~$630–640) remains
on sale and covers most teaching and research work.

**The important framing**: side-channel work recovers *keys* and *bypasses checks*, which
means it is often the only route into a device whose firmware is properly encrypted. It is
also the technique most likely to permanently damage the device if done carelessly.

### TPM, secure element, and UEFI (2025–2026 findings)

Relevant if the device you are analysing has a boot chain above the SoC:

- **TPM 2.0 Module Library out-of-bounds read — CVE-2025-2884**, which can read sensitive
  data inside the TPM. AMD published advisories covering Pluton TPM / ASP fTPM.
- **Infineon OPTIGA TPM SLB 9672/9673** received a certified firmware update in 2026-08
  covering TCG findings VRT0010 (CVE-2026-6726) and VRT0009 (CVE-2025-2884). VRT0011
  (CVE-2026-6727) does not affect OPTIGA.
- **UEFI Secure Boot bypasses are dense**: CVE-2025-4275 (Insyde — missing NVRAM variable
  attribute validation), CVE-2025-3052 (Binarly — affects most UEFI devices), and ESET's
  2026-07 disclosure of 11 Microsoft-signed **UEFI shims** (≤ 0.9) that allow Secure Boot
  bypass.

### Wireless

| Protocol | Tooling | Status / note |
|---|---|---|
| **Bluetooth / BLE** | **Nordic nRF Sniffer** (nRF52840 dongle, ~$10) + Wireshark — supports encrypted-link decryption; **NCC Group Sniffle** (CC26x2, e.g. a Sonoff Zigbee 3.0 dongle) for stronger connection following; **bettercap** (v2.41.7, 2026-05) or nRF Connect for scanning/GATT enumeration | **BTLEjack is not archived but is inactive** (last release v2.1.1, 2022-11; last commit 2023-10). It only supports the 1 Mbps uncoded PHY and does not handle channel-map updates. Its follow/jam/hijack on micro:bit is still unique among free tools, but that path is unmaintained. |
| **Zigbee / Z-Wave** | **zigbee2mqtt** (active, 2.14.x, ~5,800 devices / 600 vendors); **Z-Attack-ng** (PentHertz, 2025, Python + ImGui, **beta S2 support**) | **KillerBee is not archived but development stalled** (last substantive commits 2022; README still warns against deprecated usb0.x and ApiMote v1). **ApiMote remains a 2013–14 v4beta design** with supply problems. Z-Wave Alliance said in late 2026-09 that the source project is complete but **member-only**. |
| **Wi-Fi** | **hcxdumptool** (active, 7.1.2, 2026-02); aircrack-ng | hcxdumptool ≥ 6.3.0 uses NL80211/RTNETLINK: **kernel ≥ 5.15 and a driver with monitor mode + full frame injection are required**. Recommended chipsets: rtl8xxxu/rtw88, ath9k_htc, rt2800usb. **Intel/Broadcom/Qualcomm built-in cards are explicitly not recommended.** Do not share a NIC with aircrack-ng. aircrack-ng's stable release is still 1.7 (2022-05) though master is active. **Monitor mode is a driver/chip property, never a tool guarantee.** |
| **Sub-GHz RF** | HackRF, RTL-SDR, `rtl_433`; **URH-NG** (`PentHertz/urh-ng`, beta, v0.0.2 build 20260710) | **The original Universal Radio Hacker repo (`jopohl/urh`) was archived 2026-03-29** (last version 2.10.0). URH-NG is the successor and is still beta. Flipper Zero's official stable release is still 1.4.3 (2025-12) with 1.5.1-rc in pre-release. |
| **NFC / RFID** | **Proxmark3 Iceman** (`RfidResearchGroup/proxmark3`, v4.23346 "Frosty Lemon", 2026-09-17) | The community standard; the official Proxmark firmware is effectively unmaintained. 2026 releases added iCLASS tear-off/blacktears and a Qt6 client, Ultralight AES, and a unified keygen; emulator memory grew 4096 → 8192 bytes. **Chameleon Ultra** firmware v2.2.0 (2026-07). **Proxmark5 firmware is still beta.** |
| **SDR (general)** | GNU Radio, `gqrx`, SDR# | — |

**Universal Radio Hacker** is the tool for an unknown RF protocol: it records, demodulates,
and helps you find the framing. Many consumer devices (remotes, sensors, alarms) use
trivially replayable fixed-code or rolling-code schemes.

### Automotive

| Layer | Standard | Tooling |
|---|---|---|
| **Physical / data link** | CAN, CAN FD, LIN, FlexRay, Automotive Ethernet | CAN-to-USB adapter (CANsub, Macchina M2, CANtact, PEAK, Vector) |
| **Transport** | ISO-TP (ISO 15765-2) | `can-utils`, `isotp` Python library |
| **Diagnostics** | UDS (ISO 14229), OBD-II | `udsoncan` (Python), `can-utils` |
| **Truck / heavy vehicle** | SAE J1939 | `python-j1939`, Wireshark dissectors |
| **Pass-through API** | SAE J2534 | Vendor DLLs; `j2534` wrappers |
| **Signal description** | DBC, KCD, ARXML | `cantools` (Python), SavvyCAN, `canmatrix` |

Core tooling:

- **SocketCAN** — Linux's CAN subsystem. `ip link set can0 up type can bitrate 500000`,
  then `candump can0`, `cansend`, `cansniffer`, `canbusload`.
- **SavvyCAN** — cross-platform Qt GUI built specifically for CAN RE. Features that
  matter: the **sniffer view** (highlights which IDs change at byte/bit level — ideal for
  spotting state changes like door locks), the **range state view** (tracks per-byte value
  ranges — ideal for continuous signals like speed or temperature), flow view, and a
  fuzzing tool for probing ECU responses.
- **`cantools`** — Python library for DBC/ARXML. Decode captures, build DBC files
  programmatically.
- **ICSim** — instrument cluster simulator, for practising CAN work safely.

**CAN RE workflow**:

```text
1. Capture a baseline with the vehicle/system idle.
2. Trigger ONE action. Capture again.
3. Diff. The CAN IDs that changed are the candidates for that action.
4. For continuous signals: use the range state view over a driving/operating session —
   a byte whose value range matches the expected physical range is your signal.
5. For state signals: use the sniffer view to catch the bit that flips on the action.
6. Build the DBC entry. Confirm by decoding a fresh capture.
7. For requests: sweep the request space and watch for response activity (the fuzzing
   tool automates this).
```

**Safety boundary**: injecting frames into a live vehicle CAN bus can disable brakes,
steering assist, or airbags. Work on a bench setup or a simulator unless you have
explicit authorization and a controlled environment. This is not a formality — the
consequence is physical.

Keyless-entry relay attacks and CAN injection attacks (headlight-CAN to unlock) are
well-documented classes. The mitigation side (message authentication, gateway
segmentation) is the active research area.

---

## 4. Legal context for hardware research

Hardware research has a specific and *favorable* legal carve-out in the US, and it is
time-limited.

**DMCA §1201 triennial exemptions** — the ninth proceeding (final rule effective
**2024-10-28**) covers, among others:

- **Computer programs — security research** on devices or machines primarily designed for
  individual consumers, for good-faith security research
- **Vehicle operational data** — a new exemption allowing owners, lessees, or those acting
  on their behalf to access, store, and share operational data including diagnostic and
  telematics data
- **Retail-level commercial food preparation equipment** for diagnosis, maintenance, and
  repair
- **Text and data mining** for scholarly research and teaching

These run until **2027-10-28**. The tenth triennial proceeding opened **2026-06-09** (notice
of inquiry, 91 FR 34795). Renewal and new-exemption petitions were due **2026-08-24**;
written comments on renewals were due **2026-09-28**. If renewed, the next term runs
**2027-10 to 2030-10**. **Verify current status before relying on any of them** — as of
2026-10 there is no final rule for the tenth proceeding.

Note the scope limits that matter for hardware work:

- The exemption covers **only the act of circumvention under §1201(a)(1)**. It does **not**
  authorise distributing circumvention tools (§1201(a)(2)/(b)).
- The regulation **explicitly states it is not a safe harbour or defence** against liability
  under other law — CFAA in particular.
- The security-research class is codified at **37 CFR §201.40(b)(18)** (renumbered from
  (b)(16)). Its conditions are cumulative: lawfully obtained device or authorised system;
  **sole** purpose of good-faith security research; an environment **designed to avoid any
  harm to persons or the public**; information used **primarily to promote** the security of
  that class of device or its users; and **not** used in a way that facilitates copyright
  infringement.
- Related classes: (b)(15) devices designed primarily for consumer use, (b)(16) retail-level
  commercial food preparation equipment (new in 2024), (b)(17) medical devices, plus the
  vehicle repair and **vehicle operational data** classes.

**Right to repair** intersects here: the vehicle-repair exemption was reaffirmed, and the
operational-data exemption was added specifically to cover data access beyond repair. Note
that the exemption explicitly extends to those acting on the owner's behalf — which
matters for independent researchers and repair shops.

**EU** — two instruments with concrete dates:

- **Cyber Resilience Act, Regulation (EU) 2024/2847** — in force since 2024-12-10.
  **Article 14 reporting obligations apply from 2026-09-11** (the ENISA single reporting
  platform opened the same day): **24-hour** early warning, **72-hour** formal
  notification, and a **14-day** final report for actively exploited vulnerabilities (or
  **1 month** after the 72-hour notice for severe incidents), routed via national CSIRTs
  and ENISA. Chapter IV applies from 2026-06-11. **Full application is 2027-12-11**
  (Annex I essential requirements, vulnerability handling, technical documentation,
  conformity assessment, CE marking, market surveillance). Reporting obligations also cover
  products placed on the market before 2027-12-11; the Article 24(3) open-source steward
  duty starts 2027-12-11.
- **Right-to-repair Directive (EU) 2024/1799** — adopted 2024-06-13, in force 2024-07-30,
  **member-state transposition deadline was 2026-07-31**. On **2026-09-25** the Commission
  sent formal notices (first infringement step, INF/26/1834) to **18 member states**:
  Belgium, Bulgaria, Czechia, Estonia, Spain, France, Croatia, Italy, Cyprus, Latvia,
  Luxembourg, Malta, Netherlands, Poland, Portugal, Romania, Slovenia, Sweden. Later
  milestones: the European repair platform's common interface **2027-07-31**, the platform
  fully operational **2028-01-01**, and notification of at least one national repair
  promotion measure by **2029-07-31**.

**IoT security labelling — the US Cyber Trust Mark is still being built.** This is worth
stating precisely because it is often described as operational when it is not:

- It is a **voluntary** FCC labelling program for wireless consumer IoT.
- **UL Solutions withdrew as Lead Administrator on 2025-12-19.** The FCC accepted
  applications from 2026-01-07 to 2026-02-09, then **designated ioXt Alliance as Lead
  Administrator from 2026-04-13**. On **2026-08-11** the FCC reopened the Cybersecurity
  Label Administrator application window. On **2026-09-28/30** it recognised A2LA and ANAB
  as certification bodies (Public Notice DA-26-1029).
- **As of the 2026-08-11 official page update, the FCC had not announced that it is
  accepting product labelling applications.**
- **Executive Order 14306 (2025-06-06)** directs the FAR Council to amend the FAR so that
  agencies require the mark from suppliers of **consumer IoT products** (as defined in
  47 CFR 8.203(b)) from **2027-01-04**. That definition **excludes FDA-regulated medical
  devices and NHTSA-regulated vehicles/vehicle equipment** — considerably narrower than
  "all connected products". **No final FAR rule has been located**, so the date is not a
  self-executing procurement bar.

**What is not covered**: circumventing protection to access content (piracy), or to
access another person's device or data. The exemptions are for security research on
devices you are entitled to research.

---

## 5. Tool status (verified 2026-10)

| Tool | Domain | Status |
|---|---|---|
| **binwalk** | Extraction | **Upstream near-stalled.** Latest tag v3.1.0 (2024-10-31); 3.1.1 written in Cargo.toml but never tagged or published. Issue #935 (2026-02) says unmaintained. The v2 Python fork is EOL (2025-12-12) and archived (2026-01-13). |
| **binwalk-ng** | Extraction | **Active, v4.0.0 (2026-09-29).** Community fork; CLI still `binwalk`. **Ownership handover is unconfirmed** — no announcement from ReFirmLabs/devttys0. |
| **unblob** | Extraction | **Active, 26.6.4 (2026-06-04)**; main active through 2026-10. |
| **sasquatch** | SquashFS | **Use `onekey-sec/sasquatch`** (v4.5.1-6, 2026-01-27). `devttys0/sasquatch` stalled since 2021-03. |
| **FACT** | Firmware analysis framework | **Active, v4.4.1 (2026-09-14)**. Python 3.10–3.12. **The `FACT_docker` repo is explicitly unmaintained** — use script install or Vagrant. |
| **EMBA** | Firmware analysis + SBOM | **Active, v2.0.4 (2026-09-21)**; **migrated to binwalk-ng**. |
| **firmwalker** | Filesystem grep | **Repository gone (404).** Use the `scriptingxss/firmwalker` or `zhibx/firmwalker_pro` mirrors. |
| **Trommel** | Filesystem grep | **Archived 2024-05-13** (CMU SEI). |
| **Firmadyne** | Emulation | **Stalled** — no commits after 2024-07. |
| **FirmAE** | Emulation | Maintained but unreleased since v1.0 (2020); fix commits through 2026-06. |
| **Qiling** | Emulation | Active, v1.4.11 (2026-09-06) |
| **unicorn** | CPU emulation | Release lagging (2.1.4, 2025-09); `dev` active |
| **angr** | Symbolic execution | Very active, 10.0.1 (2026-10) |
| **Triton** | Dynamic binary analysis | Slow — last release still v0.9 (2022-02); master through 2026-05, `dev-v1.0` untagged |
| **flashrom** | Flash reading/writing | **Active, v1.8.0 (2026-08-27)**; mainline at v2.0.0-devel |
| **OpenOCD** | JTAG/SWD | Upstream release stalled (stable 0.12.0, 2023-01); git and vendor forks active |
| **Saleae Logic 2** | Logic analysis | Active (stable 2.4.46) |
| **sigrok / PulseView** | Logic analysis | **Effectively dead.** PulseView stable is still 0.4.2 (2020-03); libsigrok 0.5.2 (2019-12). The maintainer publicly described burnout and a "fundamentally outdated" architecture in 2025-10, with no handover. Nightly builds still appear. **Plan a replacement if you depend on it.** |
| **JTAGulator** | Pin discovery | Firmware stopped at 1.12 (2023-06). Manufacturing and maintenance moved to **EXPLIoT** in 2025-07. |
| **Bus Pirate 5/6** | Multi-protocol | Shipping; **no numbered stable firmware** — automatic builds from main, flashed as `.uf2`. |
| **ChipWhisperer** | Side-channel / glitching | Software 6.0.0 (2025-03); HuskyPlus is the flagship. **ChipWhisperer-Pro discontinued.** |
| **Proxmark3 Iceman** | NFC/RFID | Very active (v4.23346, 2026-09-17) |
| **BTLEjack** | BLE | Not archived but **inactive** (last commit 2023-10) |
| **KillerBee** | Zigbee | Not archived but **stalled** (substantive commits end 2022) |
| **zigbee2mqtt** | Zigbee | Active (2.14.x) |
| **Universal Radio Hacker** | RF protocol RE | **Original repo archived 2026-03-29.** Successor is **URH-NG** (beta). |
| **SavvyCAN / can-utils / cantools** | CAN | Active |
| **Ghidra / radare2 / rizin / Cutter / Binary Ninja / IDA** | Binary RE | Active |
| **Capstone** | Disassembly framework | Active |

**Also archived or superseded**: `kyechou/firmanal` (archived 2024-08-14),
`compsecdirect/autodyne` (archived 2025-08-11).

---

## 6. Decision path

```text
Device to analyse
  |
  1. Software route available?
  |    vendor download / OTA / companion app / cloud API
  |    -> YES: take it. No hardware needed.
  |    -> Recognise standard update containers: SUIT (RFC 9019 + COSE) or
  |       MCUboot (magic 0x96f3b83d, TLV 0x6907/0x6908, imgtool)
  |
  2. Physical access required. Identify interfaces:
  |    UART (4-pin header, unpopulated pads) -> serial console
  |    SPI flash (SOIC-8 chip)               -> CH341A + flashrom + clip
  |    JTAG/SWD                               -> OpenOCD; JTAGulator for pin discovery
  |
  3. Readout protected?
  |    -> identify the scheme AND the silicon revision, then check current advisories
  |    -> ESP32 ECDSA secure boot (H2/C5/C61/P4/S31): AR2026-006, no software fix
  |    -> STM32 RDP2: documented glitch bypasses; not an absolute barrier
  |    -> nRF52 APPROTECT: bypassed on early revisions; nRF54L hardened but
  |       Nordic does not claim its glitch detection is deterministic
  |    -> no known bypass: glitching territory. Specialists only.
  |
  4. Extract
  |    -> unblob FIRST, binwalk-ng to fill gaps
  |    -> verify extraction completeness, do not assume success
  |    -> SquashFS with vendor compression? -> onekey-sec/sasquatch
  |
  5. Identify
  |    -> architecture + endianness (file, readelf)
  |    -> RTOS (FreeRTOS/Zephyr/VxWorks/ThreadX/bare metal)
  |    -> set the correct load base address in Ghidra
  |    -> Xtensa: Ghidra >= 11.0 has native support; drop the old plugins
  |
  6. Dynamic
  |    -> full-system emulation (QEMU/FirmAE) -- expect NVRAM/peripheral failures
  |    -> or user-mode emulation of a single binary + LD_PRELOAD shims
  |
  7. Wireless / automotive interfaces present?
       -> see §3; bench setup before live systems
```

---

## 7. Relationship to other documents

- Native binary RE technique: [`binary-native-reverse-engineering.md`](binary-native-reverse-engineering.md),
  [`software-reverse-engineering.md`](software-reverse-engineering.md)
- Mobile app RE (companion apps often carry firmware): [`mobile-app-reverse-engineering.md`](mobile-app-reverse-engineering.md)
- Protocol analysis (including custom RF/TCP): [`protocol-reverse-engineering-advanced.md`](protocol-reverse-engineering-advanced.md)
- Authorization and DMCA exemptions: [`compliance-and-scope.md`](compliance-and-scope.md),
  [`legal-ethical.md`](legal-ethical.md)
