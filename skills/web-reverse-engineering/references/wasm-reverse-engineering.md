# WebAssembly Deep Reverse Engineering (WASM Deep RE)

WASM is becoming the sink target for risk-control algorithms: some versions of Geetest, parts of Alibaba's stack, and various license checks and crypto logic are all moving to WASM. This document provides the complete toolchain and workflow.

## Why WASM needs dedicated methods

Key differences between WASM and native binaries:

1. **A stack machine, not a register machine** — instructions operate on the implicit top of stack, so decompiled code is visibly redundant (a single native instruction is often split into several steps)
2. **No symbol table** (unless DWARF or a `name` section is present)
3. **Branch targets are blocks, not fixed addresses**, and they pop the stack implicitly
4. **LEB128 variable-length operands** (e.g. `br_table`)
5. **The dual-stack problem**: the C stack pointer and the wasm value stack coexist, and decompilers must distinguish them

**Positive factors**: the format has a formal specification, is structurally regular, and can be executed deterministically — in some respects it is easier to analyze than native code.

## Toolchain

### WABT (WebAssembly Binary Toolkit)

https://github.com/WebAssembly/wabt (C++, Apache-2.0)

| Tool | Purpose |
|---|---|
| `wat2wasm` | WAT text → binary |
| `wasm2wat` | binary → WAT |
| `wasm-objdump` | print wasm binary information (objdump-like) |
| `wasm-interp` | stack-based interpreter that executes wasm |
| `wat-desugar` | normalize into flattened WAT |
| `wasm2c` | wasm → C source + header |
| `wasm-strip` | remove sections |
| `wasm-validate` | validate |
| `wast2json` | spec test format → JSON + wasm |
| `wasm-stats` | module statistics |
| `spectest-interp` | spec test interpreter |

Install: `brew install wabt` / `sudo apt install wabt`.

> **Important change**: `wasm-decompile` **was removed from WABT on 2026-06-22** (PR #2769; the stated reason reads "This tools was unmaintained and acting mostly active as source of fuzzer bugs", effective with wabt **1.0.42**). If you need `wasm-decompile` you must pin to **1.0.41 or earlier**.
>
> Additional note: `wasm-decompile` belongs to **WABT**, **not to Binaryen** — that is a common attribution error.

### Binaryen

https://github.com/WebAssembly/binaryen

Tools: `wasm-opt`, `wasm-as`, `wasm-dis`, `wasm2js`, `wasm-reduce`, `wasm-shell`, `wasm-emscripten-finalize`, `wasm-ctor-eval`, `wasm-merge`, `wasm-metadce`, `binaryen.js`.

**`wasm2js` is a deobfuscation (fan-hunxiao) powerhouse**: it compiles wasm into JS (Emscripten uses it to generate JS as a replacement for WebAssembly, with `-sWASM=0`), emitting ES6 module format. **Flattening (tanping) wasm logic into readable JS often reaches results faster than decompiling.**

Debug information: `-ism` / `-osm` support source maps; `;;@ src.cpp:100:33` annotations; `BINARYEN_PRINT_FULL=1`; DWARF support.

### wasm-tools (Bytecode Alliance)

https://github.com/bytecodealliance/wasm-tools

A Rust implementation with better support for newer proposals (Component Model, GC). Subcommands: `print` (binary→text), `objdump`, `dump`, `validate`, `strip`, `demangle` (Rust/C++ symbols), `component wit`; testing-oriented: `mutate`, `shrink`.

**Better suited to module structure inspection and parsing modern features; it is not a high-level decompiler.**

### Ghidra WASM plugin

**Ghidra has no native WASM support.** Official issue https://github.com/NationalSecurityAgency/ghidra/issues/2937 "WebAssembly Support" (author nneonneo, created 2021-04-15, labels `Type: Enhancement` + `Feature: Processor`, **state: open, last updated 2022-03-27**).

Community plugin: **https://github.com/nneonneo/ghidra-wasm-plugin** (Java, GPL-3.0, **fork: true**)
Upstream: https://github.com/garrettgu10/ghidra-wasm-plugin (**no pushes for 3 years; actual maintenance happens on the fork**)

Capabilities:
- Loads `.wasm`, disassembles, and uses Ghidra decompilation
- Cross-references for function calls/branches, tables, and global references containing function pointers
- Stack recovery for when common compilers (e.g. Emscripten) place the C stack pointer in a global
- WASM 1.0 opcodes, SIMD, and a degree of P-Code emulation

Install: download the extension zip matching your version → Ghidra → File → Install Extensions. **Ghidra minor-version upgrades often require updating the plugin in step.**

### JEB Pro

JEB can analyze and decompile WASM, producing C-like code. Three modules: a wasm binary parser, a disassembly extension, and a decompilation extension. The principle is to convert operand stack slots into regular IR variables.

### Dynamic analysis and memory hooking

| Tool | Repository | Capability |
|---|---|---|
| **Wasabi** | https://github.com/danleh/wasabi | **Bytecode-level dynamic instrumentation (chazhuang) framework**; analyses are written in JavaScript (MIT); paper ASPLOS 2019 |
| **Cetus** | https://github.com/Qwokka/Cetus | **Browser extension, the WASM Cheat Engine**: intercepts and instruments the binary before execution, adding read/write watchpoints (Apache-2.0). Derived from Jack Baker's DEF CON 27 talk "Hacking WebAssembly Games with Binary Instrumentation" |
| wasm-mem | https://github.com/qaiik/wasm-mem | Library for reading/modifying running WASM memory (Cetus-like) |
| CetusRemastered | https://github.com/RobbyV2/CetusRemastered | Remastered edition of Cetus |
| Chrome DevTools | https://developer.chrome.com/docs/devtools/memory-inspector | The **Memory Inspector** panel can inspect `WebAssembly.Memory`; requires Chrome 107+ |

**Other dynamic analysis frameworks (paper-level)**: Wizard (engine-level non-intrusive instrumentation, arXiv 2403.07973), Wasm-R3 (record & replay), Wemby (memory corruption detection).

## Standard workflow

```bash
# 1. Structural recon: look at imports/exports/types/sections
wasm-objdump -x target.wasm
wasm-tools objdump target.wasm

# 2. Quick intel: strings and endpoints
strings -n 8 target.wasm | grep -iE "(api|key|token|secret|https|/v[0-9])"

# 3. Determine the toolchain (see the next section)
wasm-objdump -x target.wasm | grep -A20 Import

# 4. Textualize
wasm2wat target.wasm -o target.wat

# 5. To read the logic: convert to C, then optimize-compile into a native decompiler
wasm2c target.wasm -o target.c
gcc -g -O3 -I ./wasm-c-api/include -I . \
    -I /usr/share/wabt/wasm2c /usr/share/wabt/wasm2c/wasm-rt-impl.c target.c -o target.o
# Then drop target.o into IDA/Ghidra — you get much cleaner control flow

# 6. Or flatten directly into JS (least effort for deobfuscation)
wasm2js target.wasm -o target.js
```

**Why `wasm2c` + compiler optimization works**: `wasm2c` output is fairly low-level with an obvious stack-machine style, but after `-O3` optimization the instructions that were split apart get merged back together and control flow recovers naturally.

**Alternatives**: `rewasm` (https://github.com/benediktwerner/rewasm, a Rust decompiler, supports WASM MVP v1; type recovery is still incomplete and it requires libz3); the academic project **NotDec** (interprocedural type recovery, ICSE '26, https://arxiv.org/html/2608.03286v1) is better at type recovery.

## Toolchain fingerprinting

**Determining "what this wasm was compiled with" directly decides the analysis strategy**:

### Emscripten

- Imports: `wasi_snapshot_preview1.*` (e.g. `fd_write`, `environ_sizes_get`)
- Exports/internals: `__wasm_call_ctors`
- JS side: `Module.instantiateWasm`, `-sWASM=0` generating a `.wasm.js` fallback
- The official documentation states explicitly that `wasm-objdump` or `wasm-dis` can be used to view real symbol names

### wasm-bindgen (Rust)

- `__wbindgen_malloc`, `__wbindgen_free`, `__wbindgen_object_drop_ref`, `__wbindgen_exn_store`, `__wbindgen_externrefs`
- Import shims: `__wbg_<name>_<hash>`
- JS-side helpers: `passStringToWasm`, `getStringFromWasm`, `WASM_VECTOR_LEN`, `addHeapObject`, `getObject`

### AssemblyScript

- Symbols: `~lib/rt/...`
- `--exportRuntime` / `exportRuntime: true`, `@assemblyscript/loader`, `__getString(ptr)`, `ID_OFFSET`, `--runtime stub`

## Runtime hooking (the most practical entry point)

Replacing the imports object before `WebAssembly.instantiate` / `instantiateStreaming` lets you intercept all data going into and out of WASM.

```js
let wasmMemory;

const hookedImports = {
  env: {
    // Intercept outbound data going WASM → JS
    js_send_data: (ptr, len) => {
      const mem = new Uint8Array(wasmMemory.buffer, ptr, len);
      console.log('[INTERCEPTED OUTBOUND]', new TextDecoder().decode(mem));
    },
    // Keep a record of the memory object for later reads
    memory: new WebAssembly.Memory({ initial: 256 }),
  },
};
wasmMemory = hookedImports.env.memory;

WebAssembly.instantiateStreaming(fetch('app.wasm'), hookedImports)
  .then(r => console.log(r.instance.exports));
```

**The standard way to read linear memory**: `new Uint8Array(wasmMemory.buffer, ptr, len)` + `TextDecoder`. When necessary, wrap JS `Proxy` around memory reads and writes.

**The value of this technique**: in most scenarios you **do not** need to truly understand the WASM's internal logic — as long as you know what it receives and what it returns, you can reproduce the whole flow at the JS layer.

## Practical decision tree

```text
Got a .wasm
  │
  ├─ Only need to reproduce behavior?
  │    → Hook imports + read linear memory (least effort, do this first)
  │
  ├─ Only need to know which algorithm is used?
  │    → strings + wasm-objdump -x + search for constants (AES S-box, SHA IVs, RSA public keys)
  │
  ├─ Need to understand the logic?
  │    → wasm2c + -O3 + IDA/Ghidra, or wasm2js to flatten into JS
  │
  ├─ Need dynamic tracing?
  │    → Wasabi (bytecode-level instrumentation) or Cetus (memory watchpoints)
  │
  └─ Need type recovery?
       → Ghidra + nneonneo/ghidra-wasm-plugin (watch the version match)
```

## Common pitfalls

| Pitfall | Explanation |
|---|---|
| Using `wasm-decompile` | Removed in wabt 1.0.42; either pin ≤1.0.41 or switch to `wasm2c` |
| Decompiling `wasm2c` output directly | Looking at it without optimizing gives poor readability; **you must compile with `-O3`** |
| Expecting native Ghidra support | It does not exist; the community plugin must be installed |
| Ignoring the `name` section | Some modules retain a function-name section; check the name section of `wasm-objdump -x` first |
| Ignoring DWARF | C/C++-compiled wasm may carry DWARF, and handing it straight to Ghidra greatly improves results |
| Attributing `wasm-decompile` to Binaryen | An attribution error; it belongs to WABT |

## Sources

- WABT: https://github.com/WebAssembly/wabt
- `wasm-decompile` removal PR: https://github.com/WebAssembly/wabt/pull/2769
- Binaryen: https://github.com/WebAssembly/binaryen
- wasm-tools: https://github.com/bytecodealliance/wasm-tools
- Ghidra WASM support issue: https://github.com/NationalSecurityAgency/ghidra/issues/2937
- nneonneo plugin: https://github.com/nneonneo/ghidra-wasm-plugin
- garrettgu10 upstream: https://github.com/garrettgu10/ghidra-wasm-plugin
- `wasm2c` + `-O3` in practice: https://nolangilardi.github.io/blog/decompiling-wasm/
- WASM reverse engineering 2026 overview: https://1337skills.com/blog/2026-07-18-webassembly-reverse-engineering-2026-wasm-analysis/
- Key extraction and linear memory: https://blogs.jsmon.sh/webassembly-binary-reverse-engineering-decompiling-wasm-extracting-secrets-and-exploiting-linear-memory/
- Wasabi: https://github.com/danleh/wasabi
- Cetus: https://github.com/Qwokka/Cetus
- NotDec (type recovery): https://arxiv.org/html/2608.03286v1
- JEB WASM support: https://www.pnfsoftware.com/jeb/manual/webassembly
- Emscripten: https://github.com/emscripten-core/emscripten
- wasm-bindgen: https://github.com/rustwasm/wasm-bindgen
- AssemblyScript: https://github.com/AssemblyScript/assemblyscript
