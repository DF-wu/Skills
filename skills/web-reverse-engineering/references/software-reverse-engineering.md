# Software Reverse Engineering (Non-Web)

Web RE ends at the network boundary. Everything behind a desktop app, an installer, a
native binary, a game, or a document format is a different discipline with different
tooling. This document is the map.

Scope note: the techniques below are the same ones used by malware analysts, incident
responders, interoperability engineers, and security researchers. Authorization
determines whether a given application is legitimate — see
[`compliance-and-scope.md`](compliance-and-scope.md).

---

## 1. Triage first: identify before you open a disassembler

The most common wasted hour is loading a binary into Ghidra that was never compiled code
in the first place.

```text
Unknown file
  |
  +-- Detect It Easy (DIE) / `file` / TrID
  |     -> language, compiler, packer, architecture, entropy per section
  |
  +-- Entropy high everywhere?  -> packed or encrypted. Unpack first (§4).
  |
  +-- Is it an archive in disguise?
  |     -> binwalk -e, 7z l, unblob
  |
  +-- Managed runtime?
  |     -> .NET (CLR header), JVM (CAFEBABE), Python (frozen), Electron (asar)
  |     -> go straight to §2, do NOT open in Ghidra
  |
  +-- Native?
        -> §3
```

Two tools carry most of the weight here:

- **Detect It Easy (DIE)** — packer/compiler/language identification. The single most
  useful first command on any unknown binary.
- **binwalk / unblob** — recursive carving of embedded filesystems and archives.

`strings` with a good minimum length, plus `readelf`/`objdump`/`dumpbin`, covers the rest
of triage cheaply. Do this before anything expensive.

---

## 2. Managed runtimes (decompile, do not disassemble)

### Java / Kotlin (JVM)

Bytecode, not machine code. Decompilers recover near-original source.

| Tool | Note |
|---|---|
| **CFR** | Excellent modern Java support, single JAR, actively developed |
| **Vineflower** | Active fork of Procyon; strong on newer Java language features |
| **Procyon** | Still useful; superseded in some cases by Vineflower |
| **JADX** | Best for Android APK/DEX; also handles JAR |
| **Recaf** | Interactive bytecode editor — patch and re-emit, not just read |
| **Bytecode Viewer** | Multi-decompiler frontend |

Obfuscators to expect, and what to do:

| Obfuscator | Signature | Counter |
|---|---|---|
| **ProGuard / R8** | Short class/method names, removed debug info | Often still readable; use mappings if leaked |
| **Allatori** | String encryption, control-flow flattening | String decryptor, then re-decompile |
| **Zelix KlassMaster** | Aggressive string + flow obfuscation | Targeted deobfuscation scripts |
| **Stringer** | Encrypted string constants | Locate the decryptor, dump at runtime |
| **Custom class loaders** | Classes not in the JAR | Hook `ClassLoader.defineClass`, dump from memory |

The general Java approach: **decompile → find the string decryptor → run it → patch the
output → re-decompile.** Trying to read flow-obfuscated bytecode without first removing
string encryption is wasted effort.

### .NET

| Tool | Status | Note |
|---|---|---|
| **dnSpyEx** | Active | Debugger + decompiler + editor in one. The maintained fork; original `0xd4d/dnSpy` stopped. |
| **ILSpy** | Active | Read-only decompiler, high quality. `ILSpyCmd` for cross-platform CLI use. |
| **dotPeek** | Active | JetBrains, good for navigation |
| **de4dot** | **Archived (2020-08-29)** | The original obfuscator deobfuscator. **`de4dot-cex` is the de-facto maintained line.** |
| **dnlib** | Active | Library for programmatic IL manipulation |

Obfuscators: ConfuserEx, .NET Reactor, Eazfuscator, SmartAssembly, Dotfuscator.

**NativeAOT is a genuine break in the workflow.** From .NET 7, a NativeAOT-published app
compiles to native machine code with **no IL and no regular CLR metadata tables**.
`dnSpy` and `ILSpy` see nothing useful. **Any .NET desktop workflow must do AOT detection
first** — check for a CLR header before planning a decompilation.

What actually works in 2025:

| Tool | What it recovers |
|---|---|
| **`ghidra-nativeaot`** (Washi1337) | Locates the ReadyToRun directory (`RTR\0` magic), reconstructs the `DEHYDRATED_DATA` section (tag `0xCF`), rebuilds MethodTable and the type hierarchy, and annotates frozen strings. Targets .NET 8+ without symbols. |
| **`ida-nativeaot`** (Dump-GUY) | IDAPython port; IDA 9.2+, .NET 7–10, x86-64 LE |
| **`ida-nativeaot`** (advancedmonitoring) | IDA 7.x–9.x, with x64 FLIRT signature caches for .NET 7–10 |

**State the limit plainly**: these restore **metadata and types**, not C# method bodies.
You get readable native pseudocode with correct names and structures — you do not get
the original C# back. Treat NativeAOT binaries as native targets (§3). Claims that a
generic decompiler can recover NativeAOT to source are unsupported by the tools'
own documentation.

### Python

Three distinct cases, requiring three different approaches:

| Packaging | What it is | Tool |
|---|---|---|
| **PyInstaller** | Bundled CPython + zipped `.pyc` | `pyinstxtractor` (active, GPL-3.0) → then decompile the `.pyc` |
| **py2exe / cx_Freeze** | Similar, different container layout | `pyinstxtractor` variants, or manual `library.zip` extraction |
| **Nuitka** | **Compiled to C, then to native** | **No bytecode to recover.** Treat as a native binary. |

`.pyc` decompilation is **version-gated**, and the honest summary is that **Python 3.9+
usually has no reliable decompiler**:

| Tool | Coverage | Reality check |
|---|---|---|
| **uncompyle6** | **≤ Python 3.8** | README states the limit explicitly. Runs on a 3.11+ host but will not decompile its bytecode. |
| **decompyle3** | **Python 3.7–3.8** | Hard-codes `PYTHON_VERSIONS={(3,7),(3,8)}` |
| **pycdc (Decompyle++)** | Attempts 3.12/3.13 | The **only** open-source option reaching that far, but partial: `MAKE_FUNCTION`, `CALL_KW`, `TO_BOOL`, `LOAD_FAST_AND_CLEAR` and others are unsupported; output carries `# WARNING: Decompyle incomplete`, loops get mis-degraded to `if`, and the recovered code often will not run. 3.14 reports "Bad MAGIC". |
| **pycdas** | Any version | Disassembler, not a decompiler — **and far more reliable than `pycdc`'s source recovery** |

**Practical guidance**: for Python 3.9+ use **runtime instrumentation** — hook the
function, log arguments and returns — rather than fighting a static decompiler. It is
usually faster than reading bytecode, and it is always more reliable. Fall back to
`pycdas` when you need to read control flow.

### Electron

Electron apps are a web app plus a Node.js runtime. Layout:

```text
app/
  resources/
    app.asar          <- the entire application source (often plain JS)
    app.asar.unpacked/ <- native modules (.node) that cannot live in an archive
```

```bash
# Extract. Note: the modern package is @electron/asar; the old `asar` is deprecated.
npx @electron/asar extract app.asar out/

# Or with 7-Zip if the header is intact (asar is a simple container)
7z x app.asar
```

Then:

- **Fuses** — Electron's `@electron/fuses` allow the app to disable `RunAsNode`, disable
  `EnableNodeCliInspectArguments`, and require ASAR integrity. If `RunAsNode` is enabled,
  you can execute arbitrary JS in the app's context trivially. Check the fuses with
  `npx @electron/fuses read --app app/`.
- **DevTools** — `--remote-debugging-port=9222` works unless explicitly disabled. If it
  is disabled, check whether the fuse `EnableNodeCliInspectArguments` is off.
- **Native modules** — `.node` files are shared libraries. `strings`, then Ghidra if
  needed. Node's N-API is stable, so exported symbol names survive.
- **V8 bytecode** — some apps ship compiled bytecode rather than JS. `bytenode` is the
  common tool; the bytecode is V8-version-specific, so you need the matching V8 to
  disassemble or run it.

**Tauri** is the important alternative and behaves differently: the frontend is still
web (HTML/JS in a webview), but the backend is **Rust, compiled to a native binary**. There
is no asar and no Node runtime.

How the frontend is stored: `tauri-codegen` walks `frontendDist`, **Brotli-compresses** it,
and embeds it with `include_bytes!` into a static map — path strings plus a pointer/length
table land in read-only data (`.rdata` on PE). Files declared in `bundle.resources` are
**external** ordinary files, not embedded.

| Tool | Platform | Status |
|---|---|---|
| **`Mas0nShi/tauri-dumper`** | PE / Mach-O / ELF (incl. Android `.so`) | Active — scans for the asset table, Brotli-decompresses, exports |
| **`Retiu/TauriExtractor`** | Windows PE | Locates 32-byte records in `.rdata` |

**State the limit**: these recover only the built frontend. The Rust command handlers, the
IPC layer, capabilities, and all native logic are not recovered. And Brotli compression is
**not encryption** — the frontend was never a confidentiality boundary. If you need the
backend logic, that is a normal Rust binary RE task (§3).

### Go and Rust binaries

Both produce large static binaries with distinctive fingerprints.

**Go**:

Even with `-ldflags="-s -w"` (stripping), the runtime requires certain metadata to survive:

- **`pclntab`** (`.gopclntab` / `__gopclntab`) — maps PC to function name, start/end
  address, source path, and line number. The magic value changes per version
  (`0xFFFFFFFB` old, `0xFFFFFFFA` ≈1.16, `0xFFFFFFF0` 1.18–1.19, `0xFFFFFFF1` 1.20+). In
  PE files there is often no dedicated section, so you must scan for the magic.
- **`moduledata`** — points at `pclntab` / `typelinks` / `itablinks`; used for type and
  interface recovery. Its layout changes frequently between versions.
- **`buildinfo`** (Go 1.18+) — 14-byte magic `\xff Go buildinf:`. **`go version -m ./binary`
  reads out the toolchain version and every dependency module with its version.** This is
  often enough to identify a known CVE without any disassembly.

| Tool | Status | Note |
|---|---|---|
| **`mandiant/GoReSym`** | Active, MIT | Improved 1.20–1.26 layout support; `-t/-d/-p/-strings/-v`; JSON output plus an IDA importer |
| **`goretk/gore`** | Active | Includes Go 1.27 interface-table enumeration |
| **`goretk/redress`** | Low churn (2024-10) | Usable inside radare2 via r2pipe |
| **`riven-labs/unstrip`** | Active | Rust CLI, Go 1.18–1.25, includes method signature recovery and Ghidra/IDA/BN exporters |

**Obfuscation (`garble`)**: overwrites the `pclntab` magic and randomizes function names,
but **cannot remove `pclntab` or `moduledata`** — the runtime needs them. GoReSym's
`moduledata` and signature fallbacks still locate the tables; the names are simply
garbage. For that case, **`GoResolver`** (Volexity, 2025-04) uses control-flow-graph
similarity against a reference build to restore original package and function names
automatically.

**Rust**:

- Symbols are mangled (`_ZN...17h<hash>E`). `rustfilt` / `rust-demangle` demangles.
- Panic strings and `core::panicking` markers survive stripping and identify the binary
  as Rust — a reliable fingerprint.
- The `rustc` version can often be fingerprinted from panic message formats and stdlib
  internals — useful for matching against known behaviour.
- Trait objects and generics produce heavy monomorphization; expect many similar-looking
  functions.

### C / C++

The classic case. Tooling:

| Tool | Strength |
|---|---|
| **IDA Pro + Hex-Rays** | Best decompiler output on x86-64/ARM64 in most cases |
| **Ghidra** | Free, excellent for many architectures, strong scripting (Java/Python) |
| **Binary Ninja** | Best API and intermediate language (BNIL) for automation |
| **radare2 / rizin** | CLI-first, scriptable, tight static+dynamic integration, exotic architectures |
| **Hopper** | macOS-focused |

What actually accelerates C++ RE:

- **FLIRT signatures** (IDA) or Ghidra's FID — identify statically-linked library
  functions, collapsing thousands of functions into named library code.
- **RTTI / vtable recovery** — in binaries compiled with RTTI, class names and
  inheritance survive. `class-dump`-style tooling recovers the object model.
- **Struct recovery** — Ghidra's decompiler infers field accesses; manually defining the
  struct propagates types through every function that uses it. This is the single
  highest-leverage action in most C++ RE.
- **Compiler fingerprinting** — MSVC vs GCC vs Clang vs ICC produce distinguishable
  prologue/epilogue patterns, which tells you which decompiler heuristics to expect.

**Compressed debugging aid**: many binaries leak their build path, compiler version, and
library versions in string constants. `strings | grep -E '(GCC|clang|Visual Studio|/build/|/home/)'`
is a five-second step that often saves an hour.

### Qt / GTK / wxWidgets

Cross-platform native toolkits hide their resources in the binary. The approach differs
per toolkit, and Qt is the one worth knowing in detail.

**Qt resources (`.qrc` / `.rcc`)**

`.qrc` is an XML manifest that `rcc` compiles into either a C++ array or a binary `.rcc`.
The data is registered at runtime by `qRegisterResourceData(version, tree, names, data)`.
The format has versions 1–3, and the payload is zlib-compressed (Qt 6 also supports
`compression-algorithm="zstd"`).

| Tool | Note |
|---|---|
| `axstin/qtextract` | Scans for `qRegisterResourceData` call sites |
| `pgaskin/qrc` (Go) | Formats 1–3, zlib and zstd |
| `StephanvanSchaik/qtrc-extract` | — |
| `zedxxx/rccextended` | `rcc --reverse` reconstructs a recompilable `.qrc` |
| `mb1986/qrex`, `tatokis/qresExtract` | Alternatives |

(Individual maintenance status of these small extractors was not verified item by item —
check before depending on one.)

**Qt metaobject recovery** — this is the high-value part. `moc` generates, for every
`Q_OBJECT` class, a static `QMetaObject` containing a superclass pointer, a string table,
and integer metadata, plus `qt_metacall` / `qt_static_metacall`. The metadata table holds
the class name, method signatures, parameter names, signal/slot flags, properties, and
enums. **When symbols are stripped, this is the primary source of names in a Qt binary.**

- **`OSUSecLab/QtRE`** (USENIX Security 2023) — a Ghidra plugin that recovers
  `QObject::connect` signal→slot callbacks and class metadata. Reported symbol recovery
  rates of 98.9%–100% on KDE and Tesla Model S firmware. Low churn (last commit 2024-10),
  but it does what it claims.
- **`diommsantos/QtREAnalyzer`** — annotates `staticMetaObject`, `qt_meta_stringdata`,
  `qt_meta_data`, `qt_static_metacall`. Mainly x86/x64 MSVC with RTTI.

Note: there is **no public tool called "QtMocRebuilder"** — that name circulates but does
not correspond to a real project.

**GTK / wxWidgets**: no equivalent to Qt's metaobject system. GTK resources are GResource
bundles (a custom container that can be compiled in or shipped separately); wxWidgets uses
XRC XML for layouts. Both are less structured than Qt's metadata, so you fall back to
strings and cross-references.

---

## 3. Native binaries: static + dynamic

The workflow that actually works:

```text
1. Triage (§1)                 -> language, compiler, packer, arch
2. Static survey               -> strings, imports, exports, sections, entropy
3. Symbol recovery             -> FLIRT/FID, Go/Rust symbol recovery, RTTI
4. Locate the interesting code -> xrefs from API calls, string refs, crypto constants
5. Decompile / rename          -> build a mental model, not a full decompile
6. Dynamic verification        -> debugger or instrumentation confirms or refutes
7. Reimplement or patch        -> the goal depends on the task
```

**Step 4 is where most time is saved or lost.** Do not read the binary front to back.
Anchor on:

- Imported APIs that match the behaviour you care about (crypto, network, file, registry)
- String references — error messages, URLs, format strings, magic numbers
- Cryptographic constants (AES S-box, SHA-256 K, SM4 constants) — see
  `scripts/wasm_triage.py` for the same technique applied to WASM
- Cross-references into these from the entry points

**Static analysis gives you a map. Dynamic analysis tells you whether the map is lying.**
Both are needed. Decompiler output is a guess — a useful guess, but a guess.

Dynamic tooling:

| Platform | Debuggers |
|---|---|
| Windows | x64dbg, WinDbg, x64dbg with ScyllaHide |
| Linux | GDB (+ pwndbg / GEF / peda), rr for record-replay |
| macOS | LLDB |
| Cross-platform instrumentation | Frida, DynamoRIO, Intel PIN, Triton (symbolic) |
| Emulation | Qiling, unicorn, Speakeasy, angr |

**Frida is the highest-leverage dynamic tool** for most tasks: hook a function, log
arguments and returns, change a return value, no rebuild. For a licensing check, hooking
the validation function and flipping the return is usually minutes of work rather than
hours of static analysis.

---

## 4. Packers, protectors, and anti-analysis

### Identify the packer

```bash
# Entropy per section. Near-8.0 across .text is the tell.
python -c "
import math,sys
d=open(sys.argv[1],'rb').read()
for i in range(0,len(d),4096):
    c=d[i:i+4096]
    if not c: break
    e=-sum((c.count(b)/len(c))*math.log2(c.count(b)/len(c)) for b in set(c) if c.count(b))
    if e>7.0: print(hex(i), round(e,2))
" sample.bin
```

DIE or PEiD names most packers directly. Known section names are a giveaway:

| Section | Packer |
|---|---|
| `UPX0`, `UPX1` | UPX |
| `.vmp0`, `.vmp1`, `.vmp2` (also `.vmp3`) | VMProtect |
| `.themida`, `.taggant`, `.winlice`, `.loadcon` | Themida / WinLicense |
| `.aspack`, `.adata` | ASPack |
| `.mpress1`, `.mpress2` | MPRESS |
| `.enigma1`, `.enigma2` | Enigma Protector |

Two supporting signals: **per-section entropy** (`.text` near 8.0) and a **minimal import
table** containing only loader APIs.

### Unpacking by category

**Compression-only (UPX and friends).** The format is public and reversible. `upx -d`
just works. No execution, no OEP hunting.

**Stub-based (ASPack, older Themida/VMProtect modes).** The stub decrypts the real code
into memory then jumps to it. Approach: run under a debugger, set a memory breakpoint on
the stack or on `VirtualAlloc`/`VirtualProtect` results, catch the jump to the OEP, dump,
then rebuild imports.

- **Unipacker** automates this by emulating the stub (PE32 mainly).
- **Scylla** rebuilds the import table after dumping — the standard pairing is dump with
  x64dbg, fix imports with Scylla. Note: **Scylla itself has not been updated since
  2019**; it is stable and low-churn, and x64dbg has Scylla built in.
- **ScyllaHide** (last commit 2023-07) is the **user-mode** anti-anti-debug plugin that
  makes the debugging possible at all. It hooks the PEB,
  `NtQueryInformationProcess`, and `NtSetInformationThread`, with profiles for
  Themida/VMProtect.
- Themida's wrapped-import scheme usually needs more than a raw dump plus Scylla.

**Virtualization-based (VMProtect, Themida in VM mode).** This is a different problem.
The original x86 instructions are translated into a custom virtual instruction set,
interpreted at runtime. There is **no single clean OEP to dump** — the code never exists
in its original form in memory.

Options, with honest assessments:

1. **Behavioural triage.** For malware, this is often sufficient — observe what it does
   rather than what it is.
2. **Manual VM reversal.** Trace the dispatch loop, identify the handler table, lift
   handlers to semantics. Weeks to months of work for a single binary. Justified only for
   high-value targets.
3. **Devirtualization research tooling.** Two distinct lines of work exist, and they are
   **routinely conflated — do not do that**:
   - **VMDragonSlayer** (DEF CON 33, 2025-08, "De-Virtualizing the Dragon") — a
     multi-engine pipeline: VM discovery (dispatch loop / handler table / nested
     heuristics) + Intel Pin dynamic taint tracking + symbolic execution + pattern and ML
     classification + Ghidra/IDA/BN plugins of varying maturity. Targets VMProtect 2.x/3.x
     and Themida. **Its "weeks to hours" claim is not independently verified.** Public
     technical review found the released code does not implement usable real VMProtect
     devirtualization: the taint tracking is described as hardcoded rather than a real
     shadow-memory implementation, the output as dispatcher/opcode classification rather
     than clean deobfuscated code, and the README itself calls the ML model a PoC. **Do
     not treat it as a working tool.**
   - **Independent, separate work**: Jonathan Salwan's `VMProtect-devirtualization`
     (symbolic execution + LLVM, pure functions only), and Fare9's dragons-vs-VMs series
     (handler lifting to IR, Z3 semantic naming, recompilation toward LLVM IR).

**Honest assessment: full devirtualization is a research problem, not a workflow.** If you
need it, you are in a small group and you know it.

### Anti-debugging and anti-VM

| Technique | Counter |
|---|---|
| `IsDebuggerPresent`, `CheckRemoteDebuggerPresent`, PEB `BeingDebugged` | ScyllaHide (user-mode), TitanHide (kernel) |
| `NtQueryInformationProcess` (ProcessDebugPort etc.) | ScyllaHide hooks |
| Kernel-level hiding needed | **TitanHide** — a kernel driver that hooks the `Nt*` debug queries. **Warning from the project: improper installation triggers PatchGuard (`CRITICAL_STRUCTURE_CORRUPTION`), and VMProtect 3.9.4+ detects its default service name.** |
| `rdtsc` timing checks | Hypervisor-based hiding, or patch the comparison |
| Hardware breakpoint detection (`DR0-DR7`) | Use software breakpoints, or hide the DRs |
| `int 3` / exception-based flow | Careful stepping, exception logging |
| VM detection (CPUID hypervisor bit, MAC prefix, registry keys, driver names, Windows build number) | Patch the checks or run on bare metal |
| Debugger window enumeration | ScyllaHide covers most |
| Self-modifying / self-checksumming code | Patch the checksum comparison, or dump after decode |

**Hypervisor-based hiding** (TitanHide, HyperHide, or a custom hypervisor) is the strongest
counter because it operates below the OS where the checks run. It is also the most work to
set up. Note that newer VMProtect builds have also been observed checking the Windows
build number, which invalidates off-the-shelf ScyllaHide profiles.

### Linux and macOS

- **ELF**: same concepts, different tooling. UPX supports ELF. `patchelf` for
  manipulation, `readelf`/`objdump` for inspection.
- **macOS**: code signing and the hardened runtime are the interesting surface.
  - A signed binary with the hardened runtime resists injection. `codesign -d
    --entitlements` shows what it is allowed to do; the relevant exceptions are
    `com.apple.security.cs.*` (e.g. `allow-jit`, `disable-library-validation`).
  - **Only the executable needs to opt in to the hardened runtime** — dylibs and
    frameworks do not.
  - SIP restricts what you can do to system binaries.
  - Ad-hoc re-signing (`codesign --force --deep --sign -`) is the common step after
    patching.
  - **Notarization requirements**: Developer ID signature (not ad-hoc), a secure
    timestamp, hardened runtime enabled, no `com.apple.security.get-task-allow`
    entitlement, and linking against the macOS 10.9 SDK or newer. `notarytool` replaced
    `altool`; `altool` uploads stopped being accepted on 2023-11-01.
  - **macOS Sequoia removed the Control-click → Open override** for unsigned apps; the
    path is now System Settings → Privacy & Security → Open Anyway.
  - **Notarization is an automated scan of what you submit, not a guarantee about code
    fetched later.** In 2025-12 there were public reports of a signed-and-notarized
    MacSync Stealer variant that Gatekeeper did not block. Treat notarization as a
    provenance signal, not a safety verdict.

---

## 5. Installers and self-extracting archives

A large fraction of "the binary" is actually an installer wrapping the real payload.

| Format | Method | Status / gotcha |
|---|---|---|
| **MSI / WiX** | `msiexec /a pkg.msi /qb TARGETDIR=C:\out` (**administrative install — extracts the real file tree without running custom actions**); `lessmsi x pkg.msi C:\out\` (**the trailing backslash is required**); Orca to inspect tables | Active |
| **WiX Burn bundle** | WiX v3: `dark.exe -x out setup.exe` — **the wix3 repo was archived 2025-02-14**. WiX v4/v5+: `wix burn extract setup.exe -o out -oba outba` — **pass both `-out` and `-outba` or you get `a0`/`a1` instead of the real payload names** | Active. **.NET 10+ hosting bundles are built with WiX 5 and cannot be correctly extracted by v3 `dark.exe`.** |
| **NSIS** | 7-Zip extracts the payload directly | **Official 7-Zip removed NSIS script decompilation after 15.05** — you no longer get `[NSIS].nsi`. Community builds (e.g. `myfreeer/7z-build-nsis`) restore script extraction. Fall back to Universal Extractor 2. |
| **Inno Setup** | `innoextract` | Upstream **1.9 covers up to Inno Setup ≈6.3.3**. **6.4–7.x support exists only in forks/PRs, not upstream** — do not present fork capability as upstream capability. |
| **InstallShield** | Try `setup.exe /a`, then `setup.exe /s /x /b"C:\Extract" /v"/qn"`; then `cabextract` the embedded `.cab`; `unshield` handles the cabinet format (v5+) **without running the installer** | `unshield` active |
| **MSIX / APPX** | It is a ZIP plus a signature block. `MakeAppx unpack /p p.msix /d C:\out`; bundles use `MakeAppx unbundle` | Active. **EAppX (encrypted) needs the key from the Store licence.** |
| **Squirrel (Windows)** | The app is in a versioned `app-x.y.z` folder; the real code is often a plain `.nupkg` (a zip) | Stalled (last commit 2024-01) |
| **Velopack** | Squirrel's successor; similar layout | Active |
| **macOS PKG** | `file` reports **xar**. `pkgutil --expand pkg dir` yields the `Distribution` XML, component packages, `PackageInfo`, `Bom`, `Payload`, `Scripts`; `--expand-full` also expands the payload (this flag exists but is **not listed in `pkgutil`'s help**). `xar -xf` is the lower-level route. Read-only inspection: `pkgutil --check-signature`, `--payload-files`, `--bom` + `lsbom`, `spctl -a -vv -t install` | **Bundle-style pkg was retired in macOS Sequoia 15.** Installer packages are signed with a **Developer ID Installer** certificate — a different identity from Developer ID Application. |
| **macOS DMG** | UDIF. `hdiutil verify` → `imageinfo` → `attach -nobrowse` → `detach` | Apple **never published a formal UDIF specification**; the `koly` trailer and block map descriptions come from reverse engineering. Compression codes `UDZO`/`UDBZ` map to `hdiutil convert -format`. |

**Suggested order for an unknown EXE**: 7-Zip → probe `/?` for a silent-extract switch →
format-specific tool → Universal Extractor 2 → only then run the installer and harvest from
`%TEMP%`. That last step **executes installer code**, so reserve it for packages you trust.

The MSI administrative install is the step people miss: it extracts the real files without
running the installer's custom actions.

---

## 6. Document and data formats

### Office and PDF

- **OOXML (.docx/.xlsx/.pptx)** — a zip of XML. Rename to `.zip` and read. Macros live in
  `vbaProject.bin`, which is an OLE compound file containing compressed VBA source.
  `oletools` (`olevba`, `oleid`) extracts and analyses it.
- **ODF** — also a zip of XML (`content.xml`, `styles.xml`).
- **PDF** — a graph of objects, with content streams that are frequently compressed
  (FlateDecode) and sometimes encrypted. Tools: `qpdf` (structure, decryption,
  linearization — actively maintained), `pikepdf` (Python binding to qpdf), `mutool`,
  `pdf-parser.py` (Didier Stevens). JavaScript in PDFs (`/JS`, `/JavaScript`) is a common
  attack vector and worth extracting explicitly.
- **XPS** — an OPC-based zip container (`FixedDocumentSequence.fdseq` plus `.fpage` XAML).
  Handle it exactly like OOXML: rename to `.zip`. There is no well-maintained
  XPS-specific RE toolchain to recommend.

### Unknown binary formats

The disciplined approach:

```text
1. Hex dump. Look at the first 64 bytes for a magic number.
2. Search for the magic in a corpus — file signatures DB, or grep a folder of samples.
3. Entropy by region. Low-entropy regions are usually headers or tables.
4. Look for length-prefixed structures and repeated stride patterns.
5. Find two samples that differ in one known field. Diff them. The changed bytes are
   your field.
6. Write a Kaitai Struct or ImHex pattern to formalize what you found.
7. Validate against many samples.
```

Tools:

| Tool | Use | Status |
|---|---|---|
| **Kaitai Struct** | Declarative format spec, compiles to a parser in many languages. The best choice for a format you need to parse repeatedly. | Active (stable compiler 0.11) |
| **ImHex** | Hex editor with a pattern language, plus a large pattern repository | Active |
| **010 Editor** | Binary templates; commercial, huge template library | Commercial |
| **Hex Fiend** (macOS), **HxD** (Windows) | Editing and diffing | — |
| **binwalk v3** | Carving embedded structures (Rust rewrite; ~111 signatures as of the 2025-07 refresh) | Active |
| **unblob** | Modern container extraction | Active |
| **Synalyze It!** | Grammar-based format RE | Commercial |

**The differential technique (step 5) is the one that actually cracks formats.** Change
one thing in the producing application, diff the output, read the field. Repeat. This is
far faster than staring at hex.

**Extraction fails silently more often than it fails loudly.** When carving a container,
verify completeness — file count, total size, presence of expected binaries — rather than
assuming success.

### Serialization formats

When you find binary data that is not obviously a file format, check these before
reverse-engineering anything:

| Format | Identification | Decode without schema |
|---|---|---|
| **protobuf** | Field-number varint tags; often starts with `0x08`, `0x0a`, `0x12` | `protoc --decode_raw`, or `blackboxprotobuf` / `bbpb` (Python) |
| **MessagePack** | First byte often `0x80`-`0x9f` (fixmap) or `0xdc`/`0xdd` (array) | `msgpack` CLI, `msgpack-tools` |
| **CBOR** | Self-describing tags; `0xa0`+ for maps (RFC 8949) | `cbor2`, `cbor-diag` |
| **BSON** | Length-prefixed; `\x05\x00\x00\x00` style header | `bsondump` |
| **Avro** | `Obj\x01` magic, then a JSON schema in the header | **Schema is embedded — no RE needed** |
| **Thrift** | No magic; version/type byte in the header | `thrift --decode`, or Thriftpy2 |
| **FlatBuffers** | No magic; vtable offsets | Needs the schema. Recover from client code. |
| **Cap'n Proto** | Segment table in the header | Needs the schema |

protobuf without a `.proto` is by far the most common case, and
[`protocol-reverse-engineering-advanced.md`](protocol-reverse-engineering-advanced.md)
covers it in depth. **Know the hard limit before you start**: schema-less decoding
recovers field numbers and wire types only. It cannot recover names, and it cannot
reliably distinguish `string` from `bytes` from a nested message from a packed repeated
field — nor `int32` from `sint64` from `enum` from `bool`.

Two notes on tooling that matter in practice:

- **`blackboxprotobuf` (`bbpb`) can re-encode.** That is its real value: you can edit a
  decoded message and put it back on the wire, which is what you need when working through
  a proxy. The `protoc --decode_raw` route is read-only.
- **ImHex's `protobuf.hexpat` is for visual inspection, not reliable parsing.** Sub-message
  detection is trial-and-error, the pattern's own comments note that signed LEB128 "does
  not seem to work correctly", and there is a reported field-number correctness issue.
  010 Editor has no officially maintained protobuf template.
- **binwalk is not a protobuf decoder.** Its signature library contains no protobuf
  signature; it is only useful for carving a blob out of a larger container.

---

## 7. Games

Game RE is its own subfield because the anti-tamper and anti-cheat layers are unusually
aggressive, and because the goals (asset extraction, modding, save editing, research)
differ from typical application RE.

### Unity

The critical fork: **Mono or IL2CPP**. Check for `Assembly-CSharp.dll` (Mono) versus
`GameAssembly.dll` / `libil2cpp.so` plus `global-metadata.dat` (IL2CPP).

| Backend | Approach |
|---|---|
| **Mono** | `Assembly-CSharp.dll` is plain .NET IL. Open in dnSpy. Easy case. |
| **IL2CPP** | C# is transpiled to C++ then compiled. Metadata lives in `global-metadata.dat`; the logic is native. |

IL2CPP tooling — **and this is a section where the ecosystem has moved a lot, so check
status before choosing**:

| Tool | Status | Coverage |
|---|---|---|
| **Il2CppDumper** (Perfare) | Not archived but **lagging** (last commit 2024-08) | README still says Unity 5.3–2022.2; practical coverage to metadata v31. Unity 6's v35–v39 and 104+ have open, unmerged PRs. |
| **Cpp2IL** (SamboyCoding) | **Active**, `development` branch being rewritten; now under AssetRipper | Pre-release adds metadata 35/38/39/104/105/106 |
| **Il2CppInspectorRedux** (LukeFZ) | **Active** | Metadata 29/29.1/31/35/38/39/104/105/106/106.1/107/108/110. A 2026-06 report notes a new magic `0xC1C21EF0` still being rejected. |
| **Il2CppInspector** (djkaty) | **Development stopped 2021-11** | Author points users to Cpp2IL |
| **Auto-Il2cppDumper** | **Archived 2025-12-10** | Discontinued because protection methods diversified |
| **AssetStudio** (Perfare) | **Archived 2022-12-08** | Use AssetRipper |
| **AssetRipper** | Active, GPL-3.0 | Asset extraction and reconstruction |
| **UnityPy** (K0lb3) | Active | Python; handles bundles with LZ4/LZMA compression |

**Unity 6 caveat**: metadata versions jumped (31 → 35/38/39 → 104+ on 6000.5+), and some
builds no longer use `0xFAB11BAF` as the header validation constant. **Encrypted or
obfuscated metadata is beyond what any static parser can do** — you need a runtime memory
dump first.

Assets:

- **AssetRipper** (active) replaces AssetStudio (archived) — extract and reconstruct
  assets from `resources.assets` and bundles
- **Addressables** — modern Unity ships assets in Addressables bundles; same tooling,
  different container
- Asset bundles use a custom container with optional LZ4/LZMA compression; `UnityPy`
  handles it from Python

### Unreal Engine

UE5 uses **IoStore** (`.utoc` / `.ucas`).

| Tool | Capability | Status |
|---|---|---|
| **FModel** | GUI browse / preview / export, supports IoStore | Active. World export (USD) added 2026-08. |
| **CUE4Parse** | The library behind FModel; handles unversioned properties | Active |
| **repak** (Rust) | Fast CLI/library for `.pak` read/write (Oodle, AES) | Active — but **explicitly does not support IoStore** |
| **retoc** (Rust) | IoStore pack/unpack plus Zen ↔ legacy (`.uasset`/`.uexp`) conversion | Active. README states UE **5.3+** converts well; pre-5.3 may lack dependency data. |

**`.usmap` mappings are not optional.** UE5 cooked assets serialize properties by **index,
not name**. Without a `.usmap` matching the exact build, FModel/CUE4Parse can only show
raw blobs. Mappings are typically generated at runtime by UE4SS's "Dump mappings" or by
Dumper-7, and are shared per game/build. Recent dumps use newer format versions (e.g. v4,
which includes explicit enum values).

**Blueprints**: if a game ships Blueprint bytecode it can be decompiled back to graph form;
FModel's Kismet analysis covers much of this.

### Godot

- **`gdsdecomp`** (GDRETools) is active and covers Godot 2.x/3.x/4.x — loading from `.pck`,
  embedded EXE, or APK; decompiling GDScript bytecode; rebuilding `project.godot`.
- **Bytecode support tracks engine revisions**, so very new Godot versions lag.
- `.pck` layout is public: magic `GDPC`, engine version, a file table (path / offset /
  size / MD5), then data blocks. **AES-256 encryption requires a custom export template,
  and the key is not in the package.** `GodotPCKExplorer` added Godot 4.5+ PackV3 support
  in 1.5/1.6.

### Other engines

| Engine | Container | Tool | Status |
|---|---|---|---|
| **GameMaker** | `.win` / `data.win` / `game.unx` / `game.ios` / `game.droid` | **UndertaleModTool** — includes a GML decompiler *and* compiler, asset editors, scripting | Active. **YYC (native) builds do not support equivalent code editing/decompilation.** |
| **GameMaker** (parsing only) | same | **LibGM** (Rust) — parses Studio 1 through 2024–2026 builds, faster than UndertaleModLib | Active, but **no GML decompiler yet** |
| **RPG Maker** | `.rgss` archives, or plain files | `RPGMakerDecrypter` | — |
| **Ren'Py** | `.rpa` archives, `.rpyc` bytecode | `unrpa`, `unrpyc` | — |
| **Cocos2d-x** | `.jsc` (compiled JS) | V8/SpiderMonkey bytecode tooling | — |

**Save formats**: there is no general answer. Godot saves are whatever the game writes
under `user://` — ConfigFile, JSON, `var2str`, or custom `FileAccess` binary. GameMaker
likewise (often INI or custom binary). **Both must be analysed per game**; neither engine
imposes a save format.

### DRM, anti-tamper, and anti-cheat

**Read this section for scope awareness, not as a how-to.** The legal boundary here is
narrower than anywhere else in this document, and it is worth stating precisely.

| Layer | Examples | Nature |
|---|---|---|
| **DRM / anti-tamper** | Denuvo, VMProtect (used as anti-tamper), Steam DRM (SteamStub), Epic Online Services | Protects the executable from modification. Denuvo layers VM-based virtualization, dynamic code encryption, randomization, anti-debugging, and integrity checks. **It stacks with the Steam licence layer** — removing Denuvo still leaves you needing a Steam entitlement. Public bypasses exist but are version-specific. |
| **Anti-cheat** | Easy Anti-Cheat (EAC), BattlEye, Riot Vanguard, Ricochet | Kernel-level on Windows. Vanguard loads at boot. **A separate discipline** — kernel drivers, hypervisor detection, hypervisor-level hiding. |

**The legal position, stated accurately:**

1. **US DMCA §1201** prohibits circumventing access-control TPMs and **separately prohibits
   distributing circumvention tools**. *MDY Industries v. Blizzard* (9th Cir. 2010) held
   within that circuit that anti-cheat can constitute an access control — so selling a bot
   that circumvents it can create §1201(a)(2) liability **even with no finding of copyright
   infringement**.
2. **The permanent interoperability exemption §1201(f) is very narrow**: lawfully obtained
   copy, the **sole** purpose is identifying what is needed for interoperability, and the
   act itself does not infringe or violate other law. Building or distributing a
   cheat/spoofer/detection bypass does **not** fit that purpose.
3. **The temporary security-research exemption** (renewed by the 2024-10-28 rule,
   codified at **37 C.F.R. §201.40(b)(18)**) is limited to devices/systems you own or are
   authorized to use, where the **sole** purpose is good-faith testing, investigating, or
   correcting a security flaw, the environment is designed to avoid harm, the results are
   used mainly to improve the security of that class of software, and **it is not used in a
   way that facilitates infringement**. The regulation states explicitly that qualifying
   conduct **may still** create liability under other law (including CFAA) and that the
   exemption **does not authorize creating or distributing circumvention tools**.
4. **DOJ's 2022-05 CFAA charging policy** says it will not pursue good-faith security
   research. That is **prosecutorial discretion, not a statutory defence** — it does not
   affect civil CFAA, state computer-crime statutes, or contract claims.
5. **Game and anti-cheat EULAs** routinely prohibit reverse engineering, decompilation, and
   disabling security mechanisms, and US courts have long enforced such terms.
   **A DMCA research exemption does not cancel a contract you accepted.**
6. **The practical line the research community actually observes**: publishers sue people
   who **sell or distribute** cheats/spoofers. 2024–2025 published work stayed inside the
   line by narrowing what it released — Dorner & Klausner (ARES 2024) compared
   BattlEye/EAC/FACEIT/Vanguard architectures at the architectural level; Viescinski et al.
   (IEEE ISCC 2025) assessed privacy impact from observable system behaviour; Sabt's
   *Battling The Eye* (CheckMATE/CCS 2025) reverse-engineered BattlEye and disclosed to the
   vendor, releasing kernel-module code for reproducibility but **withholding the cheat
   client/DLL for legal reasons**. That withholding is the boundary the community treats as
   substantive.
7. **Outside the US**: China and South Korea criminalize game cheating more directly; in
   the EU, kernel-level anti-cheat raises GDPR and device-access questions.

Legitimate game RE is asset extraction, save-file format work, modding on titles whose
licence permits it, performance research, and security research on the game's network
protocol. Those are real and common. Piracy is not, and this document does not cover it.
See [`compliance-and-scope.md`](compliance-and-scope.md) for the general framework.

---

## 8. Decision path

```text
Unknown software artifact
  |
  1. Triage with DIE / file / binwalk
  |
  2. Managed runtime?
  |    .NET      -> dnSpyEx; de4dot first if obfuscated; NativeAOT -> treat as native
  |    JVM       -> CFR/Vineflower; deobfuscate strings first
  |    Python    -> pyinstxtractor then decompile (version-gated)
  |    Electron  -> @electron/asar extract; check fuses; check --remote-debugging-port
  |    Tauri     -> webview frontend, Rust native backend
  |
  3. Go/Rust?   -> symbol recovery (GoReSym/redress, rustfilt); buildinfo for versions
  |
  4. Native?
  |    Packed?   -> identify packer -> unpack (§4)
  |                 compression-only -> upx -d
  |                 stub-based       -> debugger + dump + Scylla
  |                 VM-based         -> behavioural triage, or devirtualization research
  |    Not packed-> FLIRT/FID, RTTI recovery, struct recovery
  |                 anchor on imports, strings, crypto constants
  |                 verify dynamically with Frida/debugger
  |
  5. Installer? -> msiexec /a, innoextract, unshield, 7z, pkgutil
  |
  6. Game?      -> engine ID -> Mono/IL2CPP fork -> Il2CppDumper -> AssetRipper/FModel
  |
  7. Format?    -> differential analysis -> Kaitai Struct / ImHex pattern
```

---

## 9. Tool inventory and maintenance status

Verify status before depending on any of these; the RE tool ecosystem churns. The
maintenance columns below reflect observed repository activity, not reputation.

| Tool | Domain | Status note |
|---|---|---|
| Ghidra | Native RE | Active (NSA), Apache-2.0 |
| IDA Pro / Hex-Rays | Native RE | Commercial, active |
| Binary Ninja | Native RE | Commercial, active |
| radare2 / rizin / Cutter | Native RE | Both r2 and rizin active; Cutter is the GUI |
| x64dbg | Windows debugging | Active |
| WinDbg | Windows debugging | Active (Microsoft) |
| **ScyllaHide** | Anti-anti-debug | **Low churn (2023-07)** — user-mode only |
| **TitanHide** | Kernel anti-anti-debug | Active; PatchGuard risk, VMProtect 3.9.4+ detects default service name |
| **Scylla** | Import reconstruction | **Stable since 2019**; built into x64dbg |
| Frida | Instrumentation | Active |
| **dnSpyEx** | .NET | Active fork of the discontinued dnSpy |
| ILSpy | .NET | Active; `ILSpyCmd` for CLI |
| **de4dot** | .NET deobfuscation | **Archived 2020-08**; use **de4dot-cex** |
| **ghidra-nativeaot** | .NET NativeAOT | Active — recovers metadata/types, **not** C# bodies |
| **ida-nativeaot** | .NET NativeAOT | Two active ports (Dump-GUY; advancedmonitoring) |
| CFR / Vineflower | JVM | Active (Vineflower has Kotlin plugin + Java 25 support) |
| **Procyon** | JVM | **Stalled 2022-02**; superseded by Vineflower |
| JADX | Android/JVM | Active |
| Recaf | JVM bytecode editing | Active |
| Detect It Easy | Triage | Active — the first command on any unknown binary |
| binwalk | Firmware/container carving | **v3 (Rust) is the current line**; the v2 fork is EOL at 2025-12-12 |
| unblob | Container extraction | Active, security-hardened pipeline |
| Kaitai Struct | Format RE | Active (stable compiler 0.11) |
| ImHex | Hex + patterns | Active |
| Unipacker | Automated unpacking | Maintained; PE32 focus |
| Qiling | Emulation | Active |
| unicorn | CPU emulation | Active |
| angr | Symbolic execution | Active |
| **VMDragonSlayer** | VM protector devirtualization | **Research only — the automated-devirtualization claim is not independently verified and public review disputes it. Do not treat as a working tool.** |
| **Il2CppDumper** | Unity IL2CPP | **Lagging (2024-08)**; Unity 6 metadata versions have unmerged PRs |
| **Cpp2IL** | Unity IL2CPP | Active; metadata 35/38/39/104+ |
| **Il2CppInspectorRedux** | Unity IL2CPP | Active; widest metadata coverage |
| **Il2CppInspector** (djkaty) | Unity IL2CPP | **Development stopped 2021-11** |
| **Auto-Il2cppDumper** | Unity IL2CPP | **Archived 2025-12-10** |
| **AssetStudio** | Unity assets | **Archived 2022-12** — use AssetRipper |
| AssetRipper | Unity assets | Active, GPL-3.0 |
| UnityPy | Unity bundles (Python) | Active |
| FModel / CUE4Parse | Unreal | Active |
| repak | Unreal `.pak` | Active — **no IoStore support** |
| retoc | Unreal IoStore | Active; UE 5.3+ recommended |
| gdsdecomp | Godot | Active; Godot 2.x/3.x/4.x |
| UndertaleModTool | GameMaker | Active; **YYC native builds not supported equivalently** |
| **vercel/pkg** | Node packaging | **Archived 2024-01** |
| **Squirrel.Windows** | Windows packaging | **Stalled 2024-01**; Velopack is the successor |
| **innoextract** | Inno Setup | Upstream covers **≈6.3.3**; 6.4–7.x only in forks |
| **wixtoolset/wix3** | WiX v3 | **Archived 2025-02-14**; .NET 10+ bundles need WiX 5 |
| unshield | InstallShield | Active |
| lessmsi | MSI | Active |
| **undetected-chromedriver** | (web) | **Dead** — last PyPI release 3.5.5, 2024-02-17 |
| **rebrowser-playwright** | (web) | **Effectively unmaintained** — last real commit 2024-09 |
| **hermes** (facebook) | React Native bytecode | Active; bytecode format is version-bound |
| **hermes-dec** (P1sec) | Hermes bytecode decompiler | Low churn; version-limited. (`P1sec/hbctool` is widely cited but its repo path currently 404s — verify before relying on it.) |
| **blutter** (worawit) | Flutter `libapp.so` | Active; recovers Dart snapshot and class/function structure |

**Three status traps worth stating explicitly**, because they change the workflow:

1. **`.NET` mainline is broken for AOT builds.** NativeAOT ships no IL and no CLR
   metadata tables. Existing tooling recovers metadata and types, not C# method bodies.
   Detect AOT before planning anything.
2. **Python `.pyc` at 3.9+ is largely unsolved.** Prefer runtime instrumentation over
   static decompilation unless the target is ≤3.8.
3. **VMProtect/Themida virtualization mode has no working automation.** Behavioural
   triage or manual reversal; anything claiming otherwise should be verified before you
   budget on it.

**Adjacent mobile runtimes** (full detail in
[`mobile-app-reverse-engineering.md`](mobile-app-reverse-engineering.md)):

- **React Native / Hermes** — bytecode decompilation via `hermes-dec`; the bytecode format
  changes between Hermes versions, so tools are version-limited.
- **Flutter** — `blutter` recovers the Dart snapshot and class/function structure from
  `libapp.so`.
- **Xamarin / .NET MAUI** — Xamarin-era artifacts are Mono AOT plus managed assemblies, so
  dnSpy/ILSpy work directly. MAUI's iOS/AOT targets converge on the NativeAOT problem
  described in §2, so plan for the native path.

---

## 10. Relationship to other documents

- Native/WASM specifics: [`binary-native-reverse-engineering.md`](binary-native-reverse-engineering.md),
  [`wasm-reverse-engineering.md`](wasm-reverse-engineering.md)
- Firmware, embedded, IoT, hardware: [`firmware-and-hardware-re.md`](firmware-and-hardware-re.md)
- Mobile apps: [`mobile-app-reverse-engineering.md`](mobile-app-reverse-engineering.md)
- Protocol and serialization formats: [`protocol-reverse-engineering-advanced.md`](protocol-reverse-engineering-advanced.md)
- Per-language library ecosystems: [`language-ecosystems.md`](language-ecosystems.md)
- Authorization and legal boundaries: [`compliance-and-scope.md`](compliance-and-scope.md),
  [`legal-ethical.md`](legal-ethical.md)

---

## 中文摘要

**先做分诊**：最常见的浪费是把一个根本不是编译产物的文件丢进 Ghidra。用 **Detect It Easy (DIE)** 看语言/编译器/壳/架构，用 `binwalk -e` / `unblob` 判断是不是伪装的容器。

**托管运行时（反编译而非反汇编）**：
- **Java/Kotlin**：CFR / Vineflower / JADX（Procyon 自 2022 年停滞，由 Vineflower 承接）。混淆器（ProGuard、Allatori、Zelix、Stringer）的通用打法：**先解字符串加密 → 再重新反编译**，跳过这步去读控制流混淆的字节码是白费功夫。
- **.NET**：dnSpyEx（活跃分支）、ILSpy。**de4dot 本体已于 2020-08 归档，事实维护线是 `de4dot-cex`。** **NativeAOT（.NET 7+）是主线断裂**——编译成原生机器码，**无 IL、无常规 CLR 元数据表**，dnSpy/ILSpy 看不到有用内容。**任何 .NET 桌面工作流必须先做 AOT 检测。** 现行可行方案是 `ghidra-nativeaot` / 两个 `ida-nativeaot` 移植版，它们恢复的是 **ReadyToRun 目录（`RTR\0`）、`DEHYDRATED_DATA`（tag `0xCF`）、MethodTable、类型层级与 frozen string**，**不恢复 C# 方法体**。任何声称能把 NativeAOT 反编译回源码的说法在其官方文档中无支撑。
- **Python**：PyInstaller → `pyinstxtractor` 再反编译 `.pyc`；**Nuitka 编译成原生，无字节码可恢复**。**`.pyc` 在 3.9+ 基本无解**：uncompyle6 官方限 **≤3.8**、decompyle3 硬编码 **3.7–3.8**；pycdc 是唯一尝试 3.12/3.13 的开源方案，但 `MAKE_FUNCTION`/`CALL_KW`/`TO_BOOL`/`LOAD_FAST_AND_CLEAR` 等 opcode 未支持，循环被错降级为 `if`，恢复的代码常不能运行（3.14 仍报 "Bad MAGIC"）。**`pycdas` 反汇编比 `pycdc` 源码恢复可靠得多。改用运行时插桩。**
- **Electron**：`@electron/asar extract`（旧 `asar` 包已弃用）；检查 **fuses**（`RunAsNode` 若开启可直接执行任意 JS）；`--remote-debugging-port=9222` 常可用；`.jsc` 与生成它的 V8 版本强绑定。**Tauri 不同**：前端仍是 web 但**用 Brotli 压缩后 `include_bytes!` 嵌入 Rust 二进制的只读数据段**（PE `.rdata`），用 `tauri-dumper` 可还原前端；**但 Rust 命令处理器、IPC、capabilities 与原生逻辑全部拿不到**，且压缩不是加密。
- **Qt / GTK / wxWidgets**：`.qrc` → `rcc` 编译，运行时由 `qRegisterResourceData` 注册，格式 1–3、zlib/zstd。**高价值的是 `moc` 生成的 `QMetaObject`**（父类指针 + 字符串表 + 整型元数据 + `qt_metacall`），含类名、方法签名、参数名、signal/slot 标志、属性、枚举——**符号剥离时这是主要名字来源**；`QtRE`（USENIX Security 2023，Ghidra 插件）可恢复 signal→slot 回调，KDE 与 Tesla 固件实测符号恢复率 98.9%–100%。**不存在名为 QtMocRebuilder 的公开工具。**
- **Go/Rust**：Go 即使 `-s -w` 剥离仍保留 **pclntab**（magic 随版本变：`0xFFFFFFFA`≈1.16、`0xFFFFFFF0` 1.18–1.19、`0xFFFFFFF1` 1.20+，PE 常无独立节需扫 magic）与 **moduledata**；`go version -m` 直接读出工具链与全部依赖模块版本（**常足以定位已知 CVE**）。**garble 会覆写 pclntab magic 并随机化函数名，但无法删除 pclntab/moduledata**——`GoReSym` 的 moduledata/签名回退仍能定位表结构，名字仍是乱码；`GoResolver`（Volexity 2025-04）用 CFG 相似度对参考构建还原原始包/函数名。Rust 用 `rustfilt` 解符号，**panic 字符串与 `core::panicking` 标记在剥离后存活**，是可靠指纹。

**原生二进制**：先 FLIRT/FID 识别静态链接库、RTTI 恢复类模型、**结构体恢复**（C++ 逆向中单点收益最高的动作）。**不要从头读到尾**——锚定导入 API、字符串引用、密码学常量，然后动态验证（Frida 挂钩通常比静态分析快一个数量级）。

**壳与保护**：压缩型（UPX，`upx -d` 直接解决）→ 桩型（调试器 + dump + **Scylla** 重建导入表 + **ScyllaHide** 反反调试，注意 ScyllaHide 只做用户态、Scylla 自 2019 年未更新、Themida 的 wrapped import 常需额外修复）→ **虚拟化型（VMProtect / Themida）**。虚拟化型**没有干净的 OEP 可 dump**，原始指令在内存中从不以原形存在。选项：行为分诊、手工逆向分派循环（数周到数月）、或研究工具。**关于 VMDragonSlayer 必须说清楚**：它（DEF CON 33, 2025-08）宣称自动化反虚拟化，但**该宣称未获独立验证**——公开技术评审指出其污点追踪为硬编码而非真实 shadow memory，输出是分派器/opcode 分类而非干净的反混淆代码，README 自述 ML 模型为 PoC。**不要把它当可用工具，也不要与 Salwan 的 `VMProtect-devirtualization` 或 Fare9 的 dragons-vs-VMs 混为一谈。** 诚实的结论：**完整反虚拟化是研究课题，不是工作流。**

**安装包**：MSI 用 `msiexec /a` 管理安装（**这一步最常被漏掉**，能不执行自定义动作直接抽出真实文件）；`lessmsi x` **尾随反斜杠必需**。WiX Burn：v3 用 `dark.exe -x`（**wix3 仓库已 2025-02-14 归档**），v4/v5+ 用 `wix burn extract -o out -oba outba`（**必须同时给两个参数**否则得到 `a0`/`a1`）；**.NET 10+ 的 hosting bundle 用 WiX 5 构建，v3 的 dark.exe 解不出来**。NSIS 用 7-Zip，但**官方 7-Zip 自 15.05 起不再反编译 NSIS 脚本**。Inno 用 `innoextract`，**上游 1.9 只覆盖到 Inno Setup ≈6.3.3，6.4–7.x 只在 fork 里**（不要把 fork 能力当上游能力）。InstallShield 用 `unshield`。MSIX/APPX 就是 zip + 签名块，`MakeAppx unpack`，**EAppX 需从 Store licence 取密钥**。macOS PKG 用 `pkgutil --expand-full`（该 flag 存在但**未列入 help**），**bundle-style pkg 已在 macOS Sequoia 15 退役**；DMG 是 UDIF，**Apple 从未发布正式规范**。

**格式逆向**：**差分法是真正能破格式的方法**——在生产端改一个字段，diff 输出，读出该字段，重复。比盯着 hex 快得多。用 Kaitai Struct / ImHex pattern 形式化。序列化格式先排除 protobuf（`protoc --decode_raw` 只读；`bbpb` 的独有价值是**能重新编码**，可用于代理中改请求）、MessagePack、CBOR、BSON、Avro（schema 内嵌，无需逆向）、Thrift、FlatBuffers/Cap'n Proto（需要 schema）。**protobuf 无 schema 解码的硬限制**：只能恢复字段号与 wire type，**无法恢复名字，也无法可靠区分 string/bytes/嵌套 message/打包重复，以及 int32/sint64/enum/bool**。ImHex 的 protobuf pattern 只适合目视检查（自述 signed LEB128 有问题）。**binwalk 不是 protobuf 解码器**（签名库里没有 protobuf）。

**游戏**：Unity 的关键分叉是 **Mono（`Assembly-CSharp.dll`，dnSpy 直接看）还是 IL2CPP（`global-metadata.dat` + 原生）**。**IL2CPP 工具链变化很大，选型前必须查状态**：`Il2CppDumper` 未归档但落后（2024-08，实用覆盖到 metadata v31，Unity 6 的 v35–v39/104+ 有未合并 PR）；`Cpp2IL` 活跃（重写中）；`Il2CppInspectorRedux` 活跃且覆盖最广；`Il2CppInspector`（djkaty）**2021-11 即停止开发**；`Auto-Il2cppDumper` **2025-12 归档**。**Unity 6 部分构建的 header 校验常量已不是 `0xFAB11BAF`，且加密/混淆的 metadata 超出任何静态解析器能力，需先做运行时内存 dump。** Unreal：`repak` 只做 `.pak`、**不支持 IoStore**；IoStore 用 `retoc`（UE 5.3+）；**UE5 按索引而非名字序列化属性，没有与构建版本匹配的 `.usmap` 就只能看到原始 blob**。Godot 用 `gdsdecomp`（字节码支持跟随引擎修订，很新的版本会滞后）；**`.pck` 的 AES-256 密钥不在包内**。GameMaker 用 `UndertaleModTool`，**YYC 原生构建不支持同等的代码反编译**。**Godot 与 GameMaker 都没有通用存档格式，必须逐游戏分析。**

**DRM 与内核级反作弊的范围必须精确**：美国 DMCA §1201 既禁止规避访问控制 TPM，**也单独禁止传播规避工具**；*MDY Industries v. Blizzard*（9th Cir. 2010）在该巡回区内认定反作弊可构成 access control，**即使无版权侵权认定**，销售规避它的 bot 仍可依 §1201(a)(2) 担责。常设互操作性例外 §1201(f) 极窄（合法取得 + **唯一目的**是识别互操作所需内容 + 行为本身不侵权），构造或发布 cheat/spoofer **不符合**该目的。临时善意安全研究豁免（2024-10-28 续期三年，编于 **37 C.F.R. §201.40(b)(18)**）限自有或经授权设备、唯一目的为善意测试/调查/修正缺陷、环境设计为避免伤害、结果主要用于改进该类软件安全性，且**不得以促成侵权的方式使用**；法规明示符合条件的**仍可能**依其他法律（含 CFAA）担责，且**不授权制造或传播规避工具**。DOJ 2022-05 的 CFAA 起诉政策是**起诉裁量，不是法定抗辩**（不影响民事 CFAA、州法与合同主张）。**游戏与反作弊 EULA 普遍禁止逆向，且法院长期执行——DMCA 研究豁免不取消你已接受的合同。** 实务分界：出版商起诉的是**销售或分发**者；2024–2025 公开研究通过收窄发布内容守住这条线（Sabt 的 *Battling The Eye*（CheckMATE/CCS 2025）向厂商披露并发布内核模块代码以保证可复现性，**但以法律理由扣留了 cheat 客户端/DLL**）。美国之外：中韩更直接地把游戏作弊入刑，欧盟内核反作弊另涉 GDPR。

合法的游戏逆向是资源提取、存档格式、授权允许的 mod、性能研究、网络协议安全研究。
