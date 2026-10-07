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

| Tool | Note |
|---|---|
| **dnSpy / dnSpyEx** | Debugger + decompiler + editor in one. dnSpyEx is the maintained fork. |
| **ILSpy** | Read-only decompiler, high quality, actively developed |
| **dotPeek** | JetBrains, good for navigation |
| **de4dot** | **The** obfuscator deobfuscator. Run it first on anything obfuscated. |
| **dnlib** | Library for programmatic IL manipulation |

Obfuscators: ConfuserEx, .NET Reactor, Eazfuscator, SmartAssembly, Dotfuscator.

**The important 2025 development: NativeAOT.** A .NET app published with NativeAOT
compiles to native machine code with no IL and no CLR metadata. `dnSpy` and `ILSpy` see
nothing useful. This is a genuine break in the traditional workflow — treat NativeAOT
binaries as native targets (§3), with the caveat that .NET runtime strings and
`System.` symbols still provide strong anchors.

### Python

Three distinct cases, requiring three different approaches:

| Packaging | What it is | Tool |
|---|---|---|
| **PyInstaller** | Bundled CPython + zipped `.pyc` | `pyinstxtractor` → then decompile the `.pyc` |
| **py2exe / cx_Freeze** | Similar, different container layout | `pyinstxtractor` variants, or manual library.zip extraction |
| **Nuitka** | **Compiled to C, then to native** | No bytecode to recover. Treat as native binary. |

`.pyc` decompilation is **version-gated** and this is the practical pain point:

- **uncompyle6** — Python ≤ 3.8, essentially unmaintained
- **decompyle3** — Python 3.7–3.8
- **pycdc (Decompyle++)** — broader range, C++, partial success on newer versions
- **pycdas** — disassembler fallback when decompilation fails

For Python 3.9+ there is frequently **no reliable decompiler**. The fallback is
`dis`-level bytecode reading, which is slow but workable, or runtime instrumentation
(hook the function, log arguments and returns) which is usually faster than reading
bytecode.

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
is no asar and no Node runtime. The IPC boundary between the webview and Rust is the
interesting surface; the Rust side is a normal native RE target.

### Go and Rust binaries

Both produce large static binaries with distinctive fingerprints.

**Go**:

- Symbol tables are usually present unless stripped. `go tool nm`, or `redress` /
  `GoReSym` / `gore` for stripped binaries.
- Build info is embedded: `go version -m ./binary` reports the Go version and every
  module dependency with versions. This is often enough to identify a known CVE.
- Goroutine scheduling and the runtime make the disassembly look unusual; expect
  `runtime.` prefixes everywhere.
- Function signatures follow Go's register-based ABI (Go 1.17+), which Ghidra needs a
  plugin or manual type work to handle well.

**Rust**:

- Symbols are mangled (`_ZN...17h<hash>E`). `rustfilt` demangles.
- Panic strings and `core::panicking` markers survive stripping and identify the binary
  as Rust.
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
| `.vmp0`, `.vmp1`, `.vmp2` | VMProtect |
| `.themida`, `.taggant` | Themida / WinLicense |
| `.aspack`, `.adata` | ASPack |
| `.mpress1`, `.mpress2` | MPRESS |
| `.enigma1`, `.enigma2` | Enigma Protector |

### Unpacking by category

**Compression-only (UPX and friends).** The format is public and reversible. `upx -d`
just works. No execution, no OEP hunting.

**Stub-based (ASPack, older Themida/VMProtect modes).** The stub decrypts the real code
into memory then jumps to it. Approach: run under a debugger, set a memory breakpoint on
the stack or on `VirtualAlloc`/`VirtualProtect` results, catch the jump to the OEP, dump,
then rebuild imports.

- **Unipacker** automates this by emulating the stub (PE32 mainly).
- **Scylla** (with ScyllaHide) rebuilds the import table after dumping. This is the
  standard pairing: dump with x64dbg, fix imports with Scylla.
- **ScyllaHide** is the anti-anti-debug plugin that makes the debugging possible at all.

**Virtualization-based (VMProtect, Themida in VM mode).** This is a different problem.
The original x86 instructions are translated into a custom virtual instruction set,
interpreted at runtime. There is **no single clean OEP to dump** — the code never exists
in its original form in memory.

Options:

1. **Behavioural triage.** For malware, this is often sufficient — observe what it does
   rather than what it is.
2. **Devirtualization research tooling.** VMDragonSlayer (presented at DEF CON 2025)
   combines dynamic taint tracking, symbolic execution, pattern classification, and ML
   prioritization to automate VM-based protector analysis. It targets VMProtect 2.x/3.x
   and Themida. Plugin status for Ghidra/IDA/Binary Ninja was still in progress as of
   late 2025 — the direct API is the stable path.
3. **Manual VM reversal.** Trace the dispatch loop, identify the handler table, lift
   handlers to semantics. Weeks to months of work for a single binary. Justified only
   for high-value targets.

Honest assessment: **full devirtualization is a research problem, not a workflow.** If
you need it, you are in a small group and you know it.

### Anti-debugging and anti-VM

| Technique | Counter |
|---|---|
| `IsDebuggerPresent`, `CheckRemoteDebuggerPresent`, PEB `BeingDebugged` | ScyllaHide, TitanHide |
| `NtQueryInformationProcess` (ProcessDebugPort etc.) | ScyllaHide hooks |
| `rdtsc` timing checks | Hypervisor-based hiding, or patch the comparison |
| Hardware breakpoint detection (`DR0-DR7`) | Use software breakpoints, or hide DRs |
| `int 3` / exception-based flow | Careful stepping, exception logging |
| VM detection (CPUID hypervisor bit, MAC prefix, registry keys, driver names) | Patch the checks or run on bare metal |
| Debugger window enumeration | ScyllaHide covers most |
| Self-modifying / self-checksumming code | Patch the checksum comparison, or dump after decode |

**Hypervisor-based hiding** (TitanHide, or a custom hypervisor) is the strongest
counter because it operates below the OS where the checks run. It is also the most work
to set up.

### Linux and macOS

- **ELF**: same concepts, different tooling. UPX supports ELF. `patchelf` for
  manipulation, `readelf`/`objdump` for inspection.
- **macOS**: code signing and the hardened runtime are the interesting surface. A signed
  binary with the hardened runtime resists injection; `codesign -d --entitlements` shows
  what it is allowed to do. SIP restricts what you can do to system binaries. Ad-hoc
  re-signing (`codesign --force --deep --sign -`) is the common step after patching.

---

## 5. Installers and self-extracting archives

A large fraction of "the binary" is actually an installer wrapping the real payload.

| Format | Tool |
|---|---|
| **MSI / WiX** | `msiexec /a pkg.msi /qb TARGETDIR=out` (administrative install), `lessmsi`, Orca, WiX `dark.exe` for the bundled payload |
| **NSIS** | 7-Zip extracts directly; `nsisunz` for stubborn cases |
| **Inno Setup** | `innoextract` |
| **InstallShield** | `unshield` |
| **Squirrel (Windows)** | The app is in a versioned `app-x.y.z` folder; the real code is often a plain `.nupkg` (a zip) |
| **Velopack** | Squirrel's successor; similar layout |
| **MSIX / APPX** | It is a zip. `makeappx unpack`, or just rename to `.zip` |
| **macOS DMG** | `hdiutil attach`, or `7z x` |
| **macOS PKG** | `pkgutil --expand-full pkg out/`, then `xar` for the payload |
| **Windows Store (MSIX)** | Zip; the payload may be an encrypted EAppX, which needs the key from the Store licence |

The MSI administrative install is the step people miss: it extracts the real files
without running the installer's custom actions.

---

## 6. Document and data formats

### Office and PDF

- **OOXML (.docx/.xlsx/.pptx)** — a zip of XML. Rename to `.zip` and read. Macros live in
  `vbaProject.bin`, which is an OLE compound file containing compressed VBA source.
  `oletools` (`olevba`, `oleid`) extracts and analyses it.
- **ODF** — also a zip of XML (`content.xml`, `styles.xml`).
- **PDF** — a graph of objects, with content streams that are frequently compressed
  (FlateDecode) and sometimes encrypted. Tools: `qpdf` (structure, decryption, linearization),
  `pikepdf` (Python binding to qpdf), `mutool`, `pdf-parser.py` (Didier Stevens).
  JavaScript in PDFs (`/JS`, `/JavaScript`) is a common attack vector and worth extracting
  explicitly.

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

| Tool | Use |
|---|---|
| **Kaitai Struct** | Declarative format spec, compiles to a parser in many languages. The best choice for a format you need to parse repeatedly. |
| **ImHex** | Hex editor with a pattern language, plus a large pattern repository |
| **010 Editor** | Binary templates; commercial, huge template library |
| **Hex Fiend** (macOS), **HxD** (Windows) | Editing and diffing |
| **binwalk / unblob** | Carving embedded structures |
| **Synalyze It!** | Grammar-based format RE |

**The differential technique (step 5) is the one that actually cracks formats.** Change
one thing in the producing application, diff the output, read the field. Repeat. This is
far faster than staring at hex.

### Serialization formats

When you find binary data that is not obviously a file format, check these before
reverse-engineering anything:

| Format | Identification | Decode without schema |
|---|---|---|
| **protobuf** | Field-number varint tags; often starts with `0x08`, `0x0a`, `0x12` | `protoc --decode_raw`, or `blackboxprotobuf` (Python) |
| **MessagePack** | First byte often `0x80`-`0x9f` (fixmap) or `0xdc`/`0xdd` (array) | `msgpack` CLI, `msgpack-tools` |
| **CBOR** | Self-describing tags; `0xa0`+ for maps | `cbor2`, `cbor-diag` |
| **BSON** | Length-prefixed; `\x05\x00\x00\x00` style header | `bsondump` |
| **Avro** | `Obj\x01` magic, then a JSON schema in the header | Schema is embedded — no RE needed |
| **Thrift** | No magic; version/type byte in the header | `thrift --decode`, or Thriftpy2 |
| **FlatBuffers** | No magic; vtable offsets | Needs the schema. Recover from client code. |
| **Cap'n Proto** | Segment table in the header | Needs the schema |

protobuf without a `.proto` is by far the most common case, and
[`protocol-reverse-engineering-advanced.md`](protocol-reverse-engineering-advanced.md)
covers it in depth. The short version: `protoc --decode_raw` gives you the field numbers
and wire types; you reconstruct names by correlating with the client code and the
semantics of the values.

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

IL2CPP tooling:

- **Il2CppDumper** — parses `global-metadata.dat` + the binary, emits dummy DLLs that
  restore class/field/method names in a disassembler. The standard first step.
- **Il2CppInspector** — alternative, with more analysis features.
- **Il2CppAssemblyUnhollower / Cpp2IL** — generate real managed assemblies for
  decompilation.

Assets:

- **AssetStudio** (archived) / **AssetRipper** (active) — extract and reconstruct assets
  from `resources.assets` and bundles
- **Addressables** — modern Unity ships assets in Addressables bundles; same tooling,
  different container
- Asset bundles use a custom container with optional LZ4/LZMA compression; `UnityPy`
  handles it from Python

### Unreal Engine

- **`.pak` files** — the container. `UnrealPak` (from the SDK) or **repak** (Rust,
  actively maintained) extracts them. Newer versions may use AES encryption, with the key
  often recoverable from the shipping executable.
- **`.usmap` mappings** — UE4/UE5 strip property names from shipped builds. Mappings
  files (from FModel's community or dumped from a build with symbols) restore them.
- **FModel / CUE4Parse** — the standard viewer; `CUE4Parse` is the underlying library if
  you need to script extraction.
- **Blueprints** — if a game ships Blueprint bytecode, it can be decompiled back to
  graph form. `Kismet` analysis in FModel covers much of this.
- **IoStore (`.utoc`/`.ucas`)** — UE5's newer container format. `retoc`, `ZenTools`,
  or FModel.

### Godot

- `.pck` archive. `gdsdecomp` (GDRE Tools) extracts and can decompile GDScript back to
  source. If the game was exported with encryption enabled, the key is in the executable.

### Other engines

| Engine | Container | Tool |
|---|---|---|
| GameMaker | `.win` / `data.win` | `UndertaleModTool` (also decompiles GML) |
| RPG Maker | `.rgss` archives, or plain files | `RPGMakerDecrypter` |
| Ren'Py | `.rpa` archives, `.rpyc` bytecode | `unrpa`, `unrpyc` |
| Cocos2d-x | `.jsc` (compiled JS) | V8/spidermonkey bytecode tooling |

### DRM, anti-tamper, and anti-cheat

**Read this section for scope awareness, not as a how-to.**

| Layer | Examples | Nature |
|---|---|---|
| **DRM / anti-tamper** | Denuvo, VMProtect (used as anti-tamper), Steam DRM (SteamStub), Epic Online Services | Protects the executable from modification. Analysis is a research problem; public bypasses exist but are version-specific and legally fraught. |
| **Anti-cheat** | Easy Anti-Cheat (EAC), BattlEye, Riot Vanguard, Ricochet | Operates at kernel level on Windows. Vanguard loads at boot. |

Two things to be clear about:

1. **Circumventing DRM is a distinct legal risk** — anti-circumvention law, separate from
   access control law. In the US, DMCA §1201 applies. The triennial exemptions cover
   security research and repair, not piracy. See
   [`compliance-and-scope.md`](compliance-and-scope.md) §5.
2. **Kernel-level anti-cheat research is a different discipline.** It involves kernel
   drivers, hypervisor detection, and hypervisor-based hiding. It is well outside the
   scope of this document and it carries its own legal and safety considerations. If that
   is your task, you already know where the material is.

Legitimate game RE is asset extraction, save-file format work, modding on titles whose
licence permits it, performance research, and security research on the game's network
protocol. Those are real and common. Piracy is not, and this document does not cover it.

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

Verify status before depending on any of these; the RE tool ecosystem churns.

| Tool | Domain | Status note |
|---|---|---|
| Ghidra | Native RE | Active (NSA) |
| IDA Pro / Hex-Rays | Native RE | Commercial, active |
| Binary Ninja | Native RE | Commercial, active |
| radare2 / rizin / Cutter | Native RE | rizin is the active fork of radare2's core; Cutter is the GUI |
| x64dbg | Windows debugging | Active |
| WinDbg | Windows debugging | Active (Microsoft) |
| ScyllaHide | Anti-anti-debug | Active |
| Scylla | Import reconstruction | Stable, low churn |
| Frida | Instrumentation | Active |
| dnSpyEx | .NET | Active fork of the discontinued dnSpy |
| ILSpy | .NET | Active |
| de4dot | .NET deobfuscation | Mature; de4dot-cex is the maintained fork |
| CFR / Vineflower | JVM | Active |
| JADX | Android/JVM | Active |
| Detect It Easy | Triage | Active |
| binwalk | Firmware/container carving | v3 is a Rust rewrite — verify which major version you have, the CLI differs |
| unblob | Container extraction | Active, strong on modern formats |
| Kaitai Struct | Format RE | Active |
| ImHex | Hex + patterns | Active |
| Unipacker | Automated unpacking | Maintained; PE32 focus |
| Qiling | Emulation | Active |
| unicorn | CPU emulation | Active |
| angr | Symbolic execution | Active |
| Il2CppDumper | Unity IL2CPP | Active |
| AssetRipper | Unity assets | Active (AssetStudio is archived) |
| FModel / CUE4Parse | Unreal | Active |
| repak | Unreal .pak | Active |
| UndertaleModTool | GameMaker | Active |
| VMDragonSlayer | VM protector devirtualization | Research; DEF CON 2025 |
| **undetected-chromedriver** | (web) | **Dead** — last PyPI release 3.5.5, 2024-02-17 |

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
- **Java/Kotlin**：CFR / Vineflower / JADX。混淆器（ProGuard、Allatori、Zelix、Stringer）的通用打法：**先解字符串加密 → 再重新反编译**，跳过这步去读控制流混淆的字节码是白费功夫。
- **.NET**：dnSpyEx（活跃分支）、ILSpy、**de4dot 先跑**。**2025 年的关键变化是 NativeAOT**——编译成原生机器码，无 IL 无元数据，dnSpy/ILSpy 看不到东西，必须当原生目标处理。
- **Python**：PyInstaller → `pyinstxtractor` 再反编译 `.pyc`；**Nuitka 编译成原生，无字节码可恢复**。`.pyc` 反编译受版本限制：uncompyle6（≤3.8，基本停止维护）、decompyle3（3.7–3.8）、pycdc（范围较广但部分失败）。**Python 3.9+ 常常没有可靠反编译器**，改用运行时插桩通常比读字节码快。
- **Electron**：`@electron/asar extract`（旧 `asar` 包已弃用）；检查 **fuses**（`RunAsNode` 若开启可直接执行任意 JS）；`--remote-debugging-port=9222` 常可用。**Tauri 不同**：前端仍是 web，后端是 Rust 原生二进制，没有 asar。
- **Go/Rust**：Go 用 `go version -m` 直接读出依赖模块版本（常足以定位已知 CVE），`GoReSym`/`redress` 处理 stripped；Rust 用 `rustfilt` 解符号，panic 字符串可指纹化 rustc 版本。

**原生二进制**：先 FLIRT/FID 识别静态链接库、RTTI 恢复类模型、**结构体恢复**（C++ 逆向中单点收益最高的动作）。**不要从头读到尾**——锚定导入 API、字符串引用、密码学常量，然后动态验证（Frida 挂钩通常比静态分析快一个数量级）。

**壳与保护**：压缩型（UPX，`upx -d` 直接解决）→ 桩型（调试器 + dump + **Scylla** 重建导入表 + **ScyllaHide** 反反调试）→ **虚拟化型（VMProtect / Themida）**。虚拟化型**没有干净的 OEP 可 dump**，原始指令在内存中从不以原形存在。选项：行为分诊、**VMDragonSlayer**（DEF CON 2025，动态污点 + 符号执行 + ML 排序）、或手工逆向分派循环（数周到数月）。**诚实的结论：完整反虚拟化是研究课题，不是工作流。**

**安装包**：MSI 用 `msiexec /a` 管理安装（**这一步最常被漏掉**，能不执行自定义动作直接抽出真实文件）、Inno 用 `innoextract`、InstallShield 用 `unshield`、NSIS 用 7-Zip、MSIX/APPX 就是 zip、macOS PKG 用 `pkgutil --expand-full`。

**格式逆向**：**差分法是真正能破格式的方法**——在生产端改一个字段，diff 输出，读出该字段，重复。比盯着 hex 快得多。用 Kaitai Struct / ImHex pattern 形式化。序列化格式先排除 protobuf（`protoc --decode_raw`、`blackboxprotobuf`）、MessagePack、CBOR、BSON、Avro（schema 内嵌，无需逆向）、Thrift、FlatBuffers/Cap'n Proto（需要 schema）。

**游戏**：Unity 的关键分叉是 **Mono（`Assembly-CSharp.dll`，dnSpy 直接看）还是 IL2CPP（`global-metadata.dat` + 原生，用 Il2CppDumper）**。Unreal 用 repak/FModel/CUE4Parse，UE5 是 IoStore（`.utoc`/`.ucas`）。Godot 用 gdsdecomp。**DRM 与内核级反作弊（Denuvo、EAC、BattlEye、Vanguard）明确标注范围**：绕过 DRM 是独立的 anti-circumvention 法律风险（美国 DMCA §1201），三年期豁免覆盖安全研究与维修，不覆盖盗版；内核级反作弊研究属于另一个学科，本文不覆盖。合法的游戏逆向是资源提取、存档格式、授权允许的 mod、网络协议安全研究。
