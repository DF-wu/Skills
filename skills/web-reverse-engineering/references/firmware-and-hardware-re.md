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

These are what stop acquisition, and each has a specific character:

| Protection | Device | Behaviour | Research approach |
|---|---|---|---|
| **STM32 RDP** | STM32 | Level 1 blocks debug reads; level 2 is permanent | RDP level 1 has known bypasses on some families; level 2 is one-way |
| **nRF52 APPROTECT** | Nordic nRF52 | Blocks debug access | Known bypasses via voltage glitching on some revisions |
| **ESP32 secure boot + flash encryption** | Espressif | Encrypted flash, signed bootloader | eFuse-based; irreversible once enabled |
| **ESP8266** | Espressif | Generally readable | Straightforward dump in most cases |
| **Broadcom / MediaTek / Qualcomm Secure Boot** | SoCs | Chain of trust from ROM | Vendor-specific; often requires a signed exploit or a glitch |
| **Fuses / OTP** | Various | One-time programmable lock bits | Irreversible; if blown, the route is glitching or decapsulation |

The honest position: **if secure boot is properly implemented and the debug interface is
permanently locked, you are in glitching or decapsulation territory**, which is a
specialist discipline with real equipment cost. Do not promise a client that a locked
device will be readable.

---

## 2. Extraction and analysis

### Carving and unpacking

| Tool | Status | Notes |
|---|---|---|
| **binwalk** | **v3 is a Rust rewrite** | Significantly faster and more accurate than v2. The CLI differs from v2 in places — check your version. The `ospg/binwalk` v2 fork declared **EOL at 2025-12-12**. |
| **unblob** | Active | 30+ formats. Reported to outperform binwalk 2.x in both speed and accuracy in independent testing. Has ~20 dependencies (binwalk has none required). Detects fewer file types than binwalk. |
| **FACT** | Active through 2024 | Firmware Analysis and Comparison Tool. Full-featured static analysis framework with plug-ins and version comparison. Requires Python 3.10–3.12. |
| **EMBA** | Active | The firmware security analyzer. SBOM generation with `cve-bin-tool` integration, VEX support, complies with the 2025 CISA minimum SBOM elements. Integrated a Binwalk v3 + unblob extraction pipeline (Dec 2024) with parallel execution. |
| **EMBArk** | Released 2024 | Enterprise firmware scanning environment; the GUI/enterprise layer over EMBA. |
| **Firmwalker / Trommel** | Mature | Simple "search the extracted filesystem for interesting things" scripts. Still useful. |
| **Firmadyne / FirmAE** | Firmadyne is dated; FirmAE is the improved fork | Automated emulation and pentesting of firmware. |
| **unblob + binwalk together** | — | Common practical approach: run unblob first (better extraction), fall back to binwalk for types unblob does not cover. |

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

| Tool | Scope |
|---|---|
| **QEMU (system mode)** | Full system emulation; the basis of most firmware emulation |
| **Firmadyne** | Automated QEMU-based firmware emulation; dated but historically important |
| **FirmAE** | Improved fork — better success rate on real firmware |
| **Qiling** | Emulation framework with OS-level API emulation; good for user-mode and partial system |
| **unicorn** | CPU-only emulation; you provide the OS semantics |
| **EMBA's emulation** | Integrated into the analysis pipeline |

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
| **FreeRTOS** | `xTaskCreate`, `vTaskDelay`, `pvPortMalloc` symbol strings; `configASSERT` |
| **Zephyr** | `z_` prefixed symbols, `k_thread`, device tree strings |
| **VxWorks** | `wdb`, `usrRoot`, `taskSpawn`, `WIND_` version strings |
| **ThreadX (Azure RTOS)** | `tx_thread_create`, `_tx_` prefixes |
| **ESP-IDF (FreeRTOS-based)** | `esp_` prefixes, `IDF` version strings |
| **bare metal** | No scheduler symbols; a main loop and interrupt vectors |

RTOS identification tells you the calling conventions, the memory model, and where to look
for task structure — it is worth the five minutes.

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

**The important framing**: side-channel work recovers *keys* and *bypasses checks*, which
means it is often the only route into a device whose firmware is properly encrypted. It is
also the technique most likely to permanently damage the device if done carelessly.

### Wireless

| Protocol | Tooling |
|---|---|
| **Bluetooth / BLE** | nRF Connect, bettercap, BTLEjack, dedicated sniffer hardware (nRF52840 dongle), Wireshark with the BLE plugin |
| **Zigbee / Z-Wave** | KillerBee, ApiMote, zigbee2mqtt, Wireshark with the Zigbee dissector |
| **Wi-Fi** | Monitor mode (`airmon-ng`), `wpa_supplicant`, `hcxdumptool`, Wireshark |
| **Sub-GHz RF** | Flipper Zero, HackRF, RTL-SDR, `rtl_433`, Universal Radio Hacker (URH) |
| **NFC / RFID** | Proxmark3, Chameleon Mini, `libnfc` |
| **SDR (general)** | GNU Radio, `gqrx`, SDR# |

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

These run until **2027-10-28**. The tenth triennial proceeding opened in 2026 with a
renewal deadline of 2026-08-24. **Verify current status before relying on any of them.**

**Right to repair** intersects here: the vehicle-repair exemption was reaffirmed, and the
operational-data exemption was added specifically to cover data access beyond repair. Note
that the exemption explicitly extends to those acting on the owner's behalf — which
matters for independent researchers and repair shops.

**EU**: the right-to-repair directive and the Cyber Resilience Act create obligations on
manufacturers, which in practice increases the availability of security-relevant
information. The DSM Directive's text-and-data-mining provisions (§5 of
[`compliance-and-scope.md`](compliance-and-scope.md)) cover research corpora.

**IoT security labelling**: the US Cyber Trust Mark program and the EU Cyber Resilience
Act both push toward mandatory security disclosure. Verify current status — the labelling
program has moved through phases and the specifics change.

**What is not covered**: circumventing protection to access content (piracy), or to
access another person's device or data. The exemptions are for security research on
devices you are entitled to research.

---

## 5. Tool status (verify before depending)

| Tool | Domain | Status |
|---|---|---|
| binwalk | Extraction | **v3 (Rust) is the current line.** v2 fork EOL 2025-12-12. |
| unblob | Extraction | Active, well-maintained, security-hardened pipeline |
| FACT | Firmware analysis framework | Active through 2024; Python 3.10–3.12 |
| EMBA | Firmware analysis + SBOM | Active, Binwalk v3 + unblob integrated |
| EMBArk | Enterprise firmware scanning | Released 2024 |
| Firmadyne | Emulation | Dated |
| FirmAE | Emulation | Active fork |
| Qiling | Emulation | Active |
| unicorn | CPU emulation | Active |
| angr | Symbolic execution | Active |
| Triton | Dynamic binary analysis | Active |
| flashrom | Flash reading/writing | Active |
| OpenOCD | JTAG/SWD | Active |
| Saleae / sigrok | Logic analysis | Active (sigrok is the open-source stack) |
| ChipWhisperer | Side-channel / glitching | Active |
| Proxmark3 | NFC/RFID | Active (Iceman fork is the community standard) |
| SavvyCAN | CAN RE | Active |
| `cantools` | CAN/DBC | Active |
| Universal Radio Hacker | RF protocol RE | Active |
| Ghidra / radare2 / rizin / Cutter | Binary RE | Active |
| Capstone | Disassembly framework | Active |

---

## 6. Decision path

```text
Device to analyse
  |
  1. Software route available?
  |    vendor download / OTA / companion app / cloud API
  |    -> YES: take it. No hardware needed.
  |
  2. Physical access required. Identify interfaces:
  |    UART (4-pin header, unpopulated pads) -> serial console
  |    SPI flash (SOIC-8 chip)               -> CH341A + flashrom + clip
  |    JTAG/SWD                               -> OpenOCD; JTAGulator for pin discovery
  |
  3. Readout protected?
  |    -> identify the scheme (RDP, APPROTECT, eFuse, secure boot)
  |    -> known bypass exists?  apply it
  |    -> no: glitching territory. Specialists only.
  |
  4. Extract
  |    -> binwalk v3, then unblob for anything missed
  |    -> verify extraction completeness, do not assume success
  |    -> SquashFS with vendor compression? -> sasquatch
  |
  5. Identify
  |    -> architecture + endianness (file, readelf)
  |    -> RTOS (FreeRTOS/Zephyr/VxWorks/ThreadX/bare metal)
  |    -> set the correct load base address in Ghidra
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

---

## 中文摘要

**获取优先走软件路径**：厂商下载门户、OTA 更新拦截、配套 App 缓存、云 API。软件路径的工作量比硬件低一个数量级，而且经常可行——因为厂商通常不把更新通道当秘密。

**硬件接口**：UART（4 针排针/空焊盘，串口控制台常直接给 shell）、SPI flash（SOIC-8 芯片 + CH341A + `flashrom` + 夹子，**标准首次硬件尝试**）、JTAG/SWD（OpenOCD；引脚发现用 JTAGulator）、逻辑分析仪（Saleae、开源 sigrok/PulseView）。**引脚识别**：万用表找地（对地导通）与 VCC（约 3.3V）；UART 的 TX 用逻辑分析仪在启动时看活动，或扫波特率。**板子已上电时绝不要从适配器接 VCC**，只接 GND/TX/RX。

**安全启动与读保护**：STM32 RDP（L1 已知绕过、L2 永久）、nRF52 APPROTECT（部分版本可用电压毛刺绕过）、ESP32 安全启动 + flash 加密（eFuse，启用后不可逆）、SoC 级安全启动链。**诚实结论：若安全启动正确实现且调试接口永久锁定，就进入毛刺注入或开盖领域**——这是有真实设备成本的专业分支，不要向客户承诺锁定设备一定能读。

**提取与解包**：
- **binwalk**：**v3 是 Rust 重写**，比 v2 显著更快更准，但 CLI 有差异需确认版本；`ospg/binwalk` 的 v2 分支已宣告 **2025-12-12 EOL**。
- **unblob**：活跃，30+ 格式，独立测试中速度和准确率常大幅优于 binwalk 2.x；代价是约 20 个依赖（binwalk 无必需依赖），且检测的文件类型少于 binwalk。
- **FACT**（Python 3.10–3.12）、**EMBA**（含 SBOM 生成 + `cve-bin-tool` 集成，符合 2025 CISA SBOM 最低要素，2024-12 起集成 binwalk v3 + unblob 并行提取管线）、**EMBArk**（2024 发布的企业版）。
- **实用做法：先 unblob，再用 binwalk 补漏。**
- **不要相信单一提取器**：文件系统提取**静默失败多于报错失败**——你会拿到一个不完整的文件系统而不自知。要验证完整性（文件数、总大小、预期二进制是否存在）。

**固件文件系统**：**SquashFS 是最常见的失败点**——厂商使用非标准压缩（LZMA 变体、LZO、ZSTD）和修改过的头部，标准 `unsquashfs` 会拒绝，需要 **sasquatch**。其他：JFFS2（`jefferson`，需正确的擦除块大小）、UBIFS（`ubireader`，两阶段：先 UBI 容器再 UBIFS）、CramFS、YAFFS、ROMFS。**熵分析是找文件系统边界最快的办法**（压缩/加密区约 8.0，头部与表低得多）。

**嵌入式二进制分析**：架构多为 ARM/MIPS/RISC-V/Xtensa。**Ghidra 必须设置正确的加载基址**，否则所有引用都是错的（裸机 ARM 若向量表在 0x08000000 就加载到那里，不是 0）。**MIPS 的端序混淆是经典陷阱**（很多路由器是大端）。先识别 RTOS（FreeRTOS `xTaskCreate`/`vTaskStartScheduler`、Zephyr `z_`/`k_thread`、VxWorks `taskSpawn`/`WIND_`、ThreadX `tx_thread_create`），它决定调用约定与内存模型。

**模拟**：QEMU 系统模式、Firmadyne（已老旧）、**FirmAE**（改进分支，成功率更高）、Qiling、unicorn、EMBA 集成模拟。**常见失败模式是常态而非例外**：NVRAM 缺失、外设寄存器读 0 导致初始化挂起、看门狗复位、硬编码 flash 物理地址未映射、内核版本不匹配。**实用解法往往是退到单二进制用户态模拟**（`qemu-arm ./httpd` + `LD_PRELOAD` 垫片），更手工但成功率高得多。

**硬件攻击面**：侧信道与故障注入（功耗分析 DPA、电磁分析、电压/时钟毛刺、激光注入）——**成本梯度很陡**：ChipWhisperer 让功耗分析与毛刺对装备良好的爱好者可行，激光注入是实验室能力。侧信道常是**固件被正确加密时唯一的进入路径**，也是操作不慎最容易永久损坏设备的路径。无线：BLE（nRF Connect、bettercap、BTLEjack、nRF52840 嗅探器）、Zigbee/Z-Wave（KillerBee、ApiMote、zigbee2mqtt）、Wi-Fi（监听模式）、Sub-GHz（Flipper Zero、HackRF、RTL-SDR、**Universal Radio Hacker**）、NFC（Proxmark3，社区标准是 Iceman 分支）。

**汽车**：SocketCAN（`ip link set can0 up type can bitrate 500000` → `candump`/`cansend`/`cansniffer`）、**SavvyCAN**（为 CAN 逆向专门设计：**sniffer view** 高亮逐字节/位变化的 ID——适合识别门锁这类状态变化；**range state view** 跟踪逐字节取值范围——适合解码速度、温度这类连续信号；另有 fuzzing 工具探测 ECU 响应）、`cantools`（DBC/ARXML）、ICSim（安全练习用仪表盘模拟器）。标准：ISO-TP（15765-2）、UDS（14229）、J1939、J2534。

**CAN 逆向流程**：空闲基线抓包 → 触发**一个**动作 → 再抓 → diff → 变化的 CAN ID 即候选 → 连续信号用 range state view（字节取值范围匹配物理量程）→ 状态信号用 sniffer view（抓翻转的位）→ 写 DBC → 用新抓包验证解码 → 请求类则扫请求空间并观察响应。

**安全边界（不是形式主义）**：向行驶车辆的 CAN 总线注入帧可能使刹车、转向助力或安全气囊失效。除非有明确授权和受控环境，否则在台架或模拟器上工作。

**法律**：美国 DMCA §1201 第九次三年期豁免（2024-10-28 生效）覆盖消费者设备的**善意安全研究**、**车辆运行数据**（含诊断与遥测）、商用食品制备设备维修、学术文本与数据挖掘，**有效期至 2027-10-28**；第十次程序 2026 年启动，续期截止 2026-08-24。**使用前必须核实当前状态。** 车辆运行数据豁免明确延伸到"代表所有者行事"的人，这对独立研究者与维修商有实际意义。欧盟方面维修权指令与网络韧性法案增加了厂商的安全信息披露义务。
