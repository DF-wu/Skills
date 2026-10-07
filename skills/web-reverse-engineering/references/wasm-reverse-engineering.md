# WebAssembly 深度逆向（WASM Deep RE）

WASM 正成为风控算法的下沉目标：极验部分版本、阿里部分体系、各类许可校验与加密逻辑都在往 WASM 走。本文给出完整工具链与工作流。

## 为什么 WASM 需要专门方法

WASM 与原生二进制的关键差异：

1. **栈式机而非寄存器机**——指令操作隐式栈顶，反编译后代码冗余明显（单个原生指令常被拆成多步）
2. **无符号表**（除非带 DWARF 或 `name` 段）
3. **分支目标是块而非固定地址**，且隐式弹栈
4. **LEB128 变长操作数**（如 `br_table`）
5. **双栈问题**：C 栈指针与 wasm 值栈并存，反编译器需区分

**正面因素**：格式有正式规范、结构规整、可确定性执行——某些方面比原生代码更易分析。

## 工具链

### WABT（WebAssembly Binary Toolkit）

https://github.com/WebAssembly/wabt （C++，Apache-2.0）

| 工具 | 作用 |
|---|---|
| `wat2wasm` | WAT 文本 → 二进制 |
| `wasm2wat` | 二进制 → WAT |
| `wasm-objdump` | 打印 wasm 二进制信息（类 objdump） |
| `wasm-interp` | 栈式解释器执行 wasm |
| `wat-desugar` | 规范化为扁平 WAT |
| `wasm2c` | wasm → C 源码 + 头文件 |
| `wasm-strip` | 删除段 |
| `wasm-validate` | 校验 |
| `wast2json` | spec 测试格式 → JSON + wasm |
| `wasm-stats` | 模块统计 |
| `spectest-interp` | spec 测试解释器 |

安装：`brew install wabt` / `sudo apt install wabt`。

> **重要变更**：`wasm-decompile` **已于 2026-06-22 从 WABT 移除**（PR #2769，理由原文 "This tools was unmaintained and acting mostly active as source of fuzzer bugs"，随 wabt **1.0.42** 生效）。需要 `wasm-decompile` 必须固定使用 **1.0.41 或更早**。
>
> 另注：`wasm-decompile` 属 **WABT**，**不属于 Binaryen**——这是一个常见归属错误。

### Binaryen

https://github.com/WebAssembly/binaryen

工具：`wasm-opt`、`wasm-as`、`wasm-dis`、`wasm2js`、`wasm-reduce`、`wasm-shell`、`wasm-emscripten-finalize`、`wasm-ctor-eval`、`wasm-merge`、`wasm-metadce`、`binaryen.js`。

**`wasm2js` 是反混淆利器**：把 wasm 编译成 JS（Emscripten 用它生成 JS 作为 WebAssembly 的替代，`-sWASM=0`），输出为 ES6 模块格式。**把 wasm 逻辑摊成可读 JS 往往比反编译更快出结果。**

调试信息：`-ism` / `-osm` 支持 source map；`;;@ src.cpp:100:33` 注解；`BINARYEN_PRINT_FULL=1`；DWARF 支持。

### wasm-tools（Bytecode Alliance）

https://github.com/bytecodealliance/wasm-tools

Rust 实现，对较新提案（Component Model、GC）支持更好。子命令：`print`（二进制→文本）、`objdump`、`dump`、`validate`、`strip`、`demangle`（Rust/C++ 符号）、`component wit`；测试向：`mutate`、`shrink`。

**更适合模块结构检查与现代特性解析，不是高层反编译。**

### Ghidra WASM 插件

**Ghidra 无原生 WASM 支持。** 官方 Issue https://github.com/NationalSecurityAgency/ghidra/issues/2937 "WebAssembly Support"（作者 nneonneo，2021-04-15 创建，标签 `Type: Enhancement` + `Feature: Processor`，**state: open，最后更新 2022-03-27**）。

社区插件：**https://github.com/nneonneo/ghidra-wasm-plugin**（Java，GPL-3.0，**fork: true**）
上游：https://github.com/garrettgu10/ghidra-wasm-plugin（**已 3 年未推送，实际维护在 fork 上**）

能力：
- 加载 `.wasm`、反汇编与 Ghidra 反编译
- 函数调用/分支交叉引用、表与含函数指针的 global 引用
- 常见编译器（如 Emscripten）把 C 栈指针放在 global 时的栈恢复
- WASM 1.0 操作码、SIMD、一定程度的 P-Code 模拟

安装：下载对应版本扩展 zip → Ghidra → File → Install Extensions。**Ghidra 小版本升级后常需同步插件。**

### JEB Pro

JEB 可分析并反编译 WASM，产出类 C 代码。三个模块：wasm 二进制解析器、反汇编扩展、反编译扩展。原理是把操作数栈槽位转换为常规 IR 变量。

### 动态分析与内存 Hook

| 工具 | 仓库 | 能力 |
|---|---|---|
| **Wasabi** | https://github.com/danleh/wasabi | **字节码级动态插桩框架**，分析用 JavaScript 编写（MIT）；论文 ASPLOS 2019 |
| **Cetus** | https://github.com/Qwokka/Cetus | **浏览器扩展，WASM 版 Cheat Engine**：在二进制执行前拦截并插桩，加读写 watchpoint（Apache-2.0）。源自 Jack Baker 在 DEF CON 27 的演讲《Hacking WebAssembly Games with Binary Instrumentation》 |
| wasm-mem | https://github.com/qaiik/wasm-mem | 读取/修改运行中 WASM 内存的库（类 Cetus） |
| CetusRemastered | https://github.com/RobbyV2/CetusRemastered | Cetus 重制版 |
| Chrome DevTools | https://developer.chrome.com/docs/devtools/memory-inspector | **Memory Inspector** 面板可检视 `WebAssembly.Memory`；需 Chrome 107+ |

**其他动态分析框架（论文级）**：Wizard（引擎级非侵入插桩，arXiv 2403.07973）、Wasm-R3（record & replay）、Wemby（内存破坏检测）。

## 标准工作流

```bash
# 1. 结构侦察：看 imports/exports/类型/段
wasm-objdump -x target.wasm
wasm-tools objdump target.wasm

# 2. 快速情报：字符串与端点
strings -n 8 target.wasm | grep -iE "(api|key|token|secret|https|/v[0-9])"

# 3. 判定工具链（见下节）
wasm-objdump -x target.wasm | grep -A20 Import

# 4. 文本化
wasm2wat target.wasm -o target.wat

# 5. 要读逻辑：转 C 再优化编译进原生反编译器
wasm2c target.wasm -o target.c
gcc -g -O3 -I ./wasm-c-api/include -I . \
    -I /usr/share/wabt/wasm2c /usr/share/wabt/wasm2c/wasm-rt-impl.c target.c -o target.o
# 再把 target.o 丢进 IDA/Ghidra —— 得到干净得多的控制流

# 6. 或直接摊平成 JS（对反混淆最省力）
wasm2js target.wasm -o target.js
```

**`wasm2c` + 编译器优化为何有效**：`wasm2c` 输出偏底层、栈机器风格明显，但经 `-O3` 优化后，原本被拆散的指令会被重新合并，控制流恢复自然。

**替代方案**：`rewasm`（https://github.com/benediktwerner/rewasm，Rust 反编译器，支持 WASM MVP v1，类型恢复仍不完善，需 libz3）；学术项目 **NotDec**（跨过程类型恢复，ICSE '26，https://arxiv.org/html/2608.03286v1）在类型恢复上更好。

## 工具链指纹识别

**判定「这个 wasm 用什么编译的」直接决定分析策略**：

### Emscripten

- 导入：`wasi_snapshot_preview1.*`（如 `fd_write`、`environ_sizes_get`）
- 导出/内部：`__wasm_call_ctors`
- JS 侧：`Module.instantiateWasm`、`-sWASM=0` 生成 `.wasm.js` 回退
- 官方文档明示可用 `wasm-objdump` 或 `wasm-dis` 查看真实符号名

### wasm-bindgen（Rust）

- `__wbindgen_malloc`、`__wbindgen_free`、`__wbindgen_object_drop_ref`、`__wbindgen_exn_store`、`__wbindgen_externrefs`
- 导入 shim：`__wbg_<name>_<hash>`
- JS 侧助手：`passStringToWasm`、`getStringFromWasm`、`WASM_VECTOR_LEN`、`addHeapObject`、`getObject`

### AssemblyScript

- 符号：`~lib/rt/...`
- `--exportRuntime` / `exportRuntime: true`、`@assemblyscript/loader`、`__getString(ptr)`、`ID_OFFSET`、`--runtime stub`

## 运行时 Hook（最实用的入口）

在 `WebAssembly.instantiate` / `instantiateStreaming` 之前替换 imports 对象，即可拦截所有进出 WASM 的数据。

```js
let wasmMemory;

const hookedImports = {
  env: {
    // 拦截 WASM → JS 的出站数据
    js_send_data: (ptr, len) => {
      const mem = new Uint8Array(wasmMemory.buffer, ptr, len);
      console.log('[INTERCEPTED OUTBOUND]', new TextDecoder().decode(mem));
    },
    // 记录内存对象以便后续读取
    memory: new WebAssembly.Memory({ initial: 256 }),
  },
};
wasmMemory = hookedImports.env.memory;

WebAssembly.instantiateStreaming(fetch('app.wasm'), hookedImports)
  .then(r => console.log(r.instance.exports));
```

**读取线性内存的标准方式**：`new Uint8Array(wasmMemory.buffer, ptr, len)` + `TextDecoder`。必要时对 memory 读写挂 JS `Proxy`。

**这个手法的价值**：多数场景下你**不需要**真正理解 WASM 内部逻辑——只要知道它接收什么、返回什么，就能在 JS 层复现整个流程。

## 实操决策树

```text
拿到 .wasm
  │
  ├─ 只需复现行为？
  │    → Hook imports + 读线性内存（最省力，优先做）
  │
  ├─ 只需知道用了什么算法？
  │    → strings + wasm-objdump -x + 搜常量（AES S-box、SHA 初始值、RSA 公钥）
  │
  ├─ 需要理解逻辑？
  │    → wasm2c + -O3 + IDA/Ghidra，或 wasm2js 摊平成 JS
  │
  ├─ 需要动态追踪？
  │    → Wasabi（字节码级插桩）或 Cetus（内存 watchpoint）
  │
  └─ 需要类型恢复？
       → Ghidra + nneonneo/ghidra-wasm-plugin（注意版本匹配）
```

## 常见陷阱

| 陷阱 | 说明 |
|---|---|
| 用 `wasm-decompile` | 已在 wabt 1.0.42 移除；要么固定 ≤1.0.41，要么改用 `wasm2c` |
| 直接反编译 `wasm2c` 输出 | 不优化就直接看，可读性差；**必须加 `-O3` 再编译** |
| 期望 Ghidra 原生支持 | 不存在，必须装社区插件 |
| 忽略 `name` 段 | 有些模块保留函数名段，先检查 `wasm-objdump -x` 的 name section |
| 忽略 DWARF | C/C++ 编译的 wasm 可能带 DWARF，直接给 Ghidra 用可大幅改善 |
| 把 `wasm-decompile` 归给 Binaryen | 归属错误，它属 WABT |

## 来源

- WABT：https://github.com/WebAssembly/wabt
- `wasm-decompile` 移除 PR：https://github.com/WebAssembly/wabt/pull/2769
- Binaryen：https://github.com/WebAssembly/binaryen
- wasm-tools：https://github.com/bytecodealliance/wasm-tools
- Ghidra WASM 支持 Issue：https://github.com/NationalSecurityAgency/ghidra/issues/2937
- nneonneo 插件：https://github.com/nneonneo/ghidra-wasm-plugin
- garrettgu10 上游：https://github.com/garrettgu10/ghidra-wasm-plugin
- `wasm2c` + `-O3` 实战：https://nolangilardi.github.io/blog/decompiling-wasm/
- WASM 逆向 2026 概览：https://1337skills.com/blog/2026-07-18-webassembly-reverse-engineering-2026-wasm-analysis/
- 密钥提取与线性内存：https://blogs.jsmon.sh/webassembly-binary-reverse-engineering-decompiling-wasm-extracting-secrets-and-exploiting-linear-memory/
- Wasabi：https://github.com/danleh/wasabi
- Cetus：https://github.com/Qwokka/Cetus
- NotDec（类型恢复）：https://arxiv.org/html/2608.03286v1
- JEB WASM 支持：https://www.pnfsoftware.com/jeb/manual/webassembly
- Emscripten：https://github.com/emscripten-core/emscripten
- wasm-bindgen：https://github.com/rustwasm/wasm-bindgen
- AssemblyScript：https://github.com/AssemblyScript/assemblyscript
