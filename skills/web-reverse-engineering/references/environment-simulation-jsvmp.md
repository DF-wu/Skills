# Environment Simulation and JSVMP Analysis

Chinese-ecosystem risk control has two core obstacles: **environment simulation** (bu-huanjing — code that depends on a browser environment) and **JSVMP** (code compiled into custom bytecode). This document covers each in turn.

## Part 1: Environment Simulation (bu-huanjing)

### Concept

Risk-control JavaScript needs browser objects before it can run. Environment simulation = building enough of a browser environment inside Node so the site's own code runs directly and produces the parameters. Compared with extracting code line by line, **the maintenance cost is far lower** — after a site update, usually no code changes are needed.

### Execution hosts

| Option | Source | Key points |
|---|---|---|
| Node `vm` | https://nodejs.org/api/vm.html | `vm.createContext()` emulates the `window` global; `vm.Script` / `runInContext` / `runInNewContext`. **The docs state explicitly: `node:vm` is not a security mechanism and must not be used to run untrusted code** |
| jsdom | https://github.com/jsdom/jsdom | `getInternalVMContext()` turns the jsdom window into a real context usable by `vm` |
| happy-dom | https://github.com/capricorn86/happy-dom | Faster DOM implementation, TypeScript |
| isolated-vm | https://github.com/laverdet/isolated-vm | True isolated V8 isolate; REstringer / webcrack use it to run unsafe modules |
| node-canvas | https://github.com/Automattic/node-canvas | Required for Canvas fingerprint simulation |

> The maintenance status of `vm2` is **unverified** (long-standing community reports of escape vulnerabilities). Prefer `isolated-vm` as the replacement.

### Checklist of objects that need to be simulated

```
window / self / global
document (including documentElement.getAttribute)
navigator (including userAgent, plugins, mimeTypes, property descriptors)
location
localStorage / sessionStorage
screen
history
crypto
XMLHttpRequest / fetch
canvas / WebGL
external
performance
chrome
iframe.contentWindow
```

### Countering environment detection (the important part)

#### `Function.prototype.toString` native code detection

This is the most widespread detection technique. The standard counter-implementation:

```js
const $toString = Function.toString;
const myFunction_toString_symbol = Symbol('('.concat('', ')'));
const myToString = function myToString() {
  return (typeof this === 'function' && this[myFunction_toString_symbol]) || $toString.call(this);
};
const set_native = function (func, key, value) {
  Object.defineProperty(func, key, { enumerable: false, configurable: true, writable: true, value });
};
delete Function.prototype['toString'];
set_native(Function.prototype, 'toString', myToString);
set_native(Function.prototype.toString, myFunction_toString_symbol, 'function toString() { [native code] }');
```

**Critical detail (very easily overlooked)**: after redefining a native function, **its `prototype` must remain `undefined`**.

Community measurements show that `qxVm` handles this correctly (native function `prototype === undefined`), while hand-written frameworks often wrongly expose a function prototype. **Detectors rely on exactly this to catch a simulated environment.**

#### Other detection points and counters

| Detection point | Counter |
|---|---|
| `Symbol.toStringTag` / `Symbol.toPrimitive` | `Object.defineProperty(obj, Symbol.toStringTag, {value: 'External'})` |
| `Object.getOwnPropertyNames` / `Object.keys` prototype-chain enumeration | Precisely control the own-property set (e.g. one site requires returning only `['length','name']`) |
| Property descriptor detection | Set `enumerable` / `configurable` / `writable` explicitly with `Object.defineProperty` |
| `Object.freeze()` detection | After simulation is finished, call `Object.freeze()` on `window` / `navigator` (in browsers they are immutable to begin with) |
| Exception stack signature | Node signature string `/modules/cjs/loader`; counter: rewrite `String.prototype.indexOf` so it returns -1 |
| `process` global detection | Delete `global.process` (and `delete __dirname` / `__filename`) |
| Canvas / WebGL fingerprint | Requires real drawing through `node-canvas`; mind .jpg/.png, quality and property differences, and repeated drawing under identical conditions must be consistent |
| iframe `contentWindow` detection | The iframe context must be simulated |
| Automation traces | Some sites have 20+ automation-property detection points |

#### Proxy-based environment emission

Attach a `Proxy` to `document` / `navigator` / `location` to log the access trace and fill in the environment step by step (`self` / `window` usually need no proxy).

```js
function proxyEnv(obj, name) {
  return new Proxy(obj, {
    get(target, prop) {
      console.log(`[env] ${name}.${String(prop)}`);
      return target[prop];
    },
    set(target, prop, value) {
      console.log(`[env] set ${name}.${String(prop)} =`, value);
      target[prop] = value;
      return true;
    },
  });
}
```

### Environment simulation frameworks

| Framework | Repository | Notes |
|---|---|---|
| **sdenv** | https://github.com/pysunday/sdenv | "Perfectly passes Ruishu VMP, theoretically a universal bypass"; community verdict "the most comfortable, fast and stable"; based on a modified jsdom |
| v_jstools | https://github.com/cilame/v_jstools | Chrome-extension-style environment simulation / debugging, with AST processing and WASM support |
| Fchrome | https://github.com/jiyulany/Fchrome | Custom Chromium, emits the environment on its own |
| qxVm | https://github.com/ylw00/qxVm | Pure-JS environment simulation framework, built on `node16` + `vm2`; **DOM support is incomplete** |
| boda_jsEnv | https://github.com/xuxiaobo-bobo/boda_jsEnv | — |
| Aggregator repo | https://github.com/hybjpjx/all_vm2_vm_node_sandbox | Collects CatVm2, HaHaVM, NodeSandbox, ZGYD, boda_jsEnv, qxVm, sdenv and others |
| rs-reverse | https://github.com/pysunday/rs-reverse | The inspiration for sdenv; Ruishu pure algorithm |

**Community verdict**: `catvm` / `CatVm2` are missing many environment pieces and are not updated; the author of `node-sandbox` (a modified Node build) has abandoned the project.

> **Important limitation**: some "environment simulation frameworks" are in fact **simulated-environment frameworks** — they patch the spots in jsdom that are easy to detect, so site JS can run directly and produce results, but they **cannot "emit the environment"** (only some objects and functions can be instrumented to print logs, such as cookie and eval). If you need a complete access-trace export, you still have to attach your own `Proxy`.

### Environment simulation field checklist

- [ ] `navigator.userAgent` matches the request UA
- [ ] The `screen` and `devicePixelRatio` combination is plausible
- [ ] `prototype === undefined` after redefining a native function
- [ ] The `Object.getOwnPropertyNames` return value matches a browser
- [ ] `Object.freeze()` has been applied to `window` / `navigator`
- [ ] No Node signature string in the exception stack
- [ ] `global.process` has been deleted
- [ ] Canvas drawing is consistent across repeated runs under identical conditions
- [ ] Property descriptors (`enumerable` / `configurable` / `writable`) are set explicitly

## Part 2: JSVMP

### Mechanism

Custom bytecode plus an interpreter loop. Typical structure:

```
VMContext    registers / stack / bytecode pointer
VMInit       initialization
VMExit       exit
Dispatcher   main loop while + switch(opcode)
Handler      handler function per opcode
```

Execution model: `opcode = bytecode[PC++]`, operands are taken from the bytecode stream or a constant pool, and the result is pushed onto the stack / written to a register.

**Provenance**: the concept originates from Kuang Kaiyuan (Master's student, class of 2015, Northwest University), the 2018 degree thesis "Research and Implementation of a WebAssembly-Based JavaScript Code Virtualization Protection Method", and the national patent "A JavaScript Virtualization Protection Method Based on Front-end Bytecode Technology".

**Official position (obfuscator.io wording)**:

> "No automated deobfuscator online services currently exist for VM-obfuscated code — each obfuscation compiles code into custom bytecode with a unique virtual machine, making universal tooling impossible."

In other words, **there is no general automated recovery solution for JSVMP; it must be handled sample by sample.** This is the single most important practical constraint in this field.

### Representative implementations

| Project | Repository | Description |
|---|---|---|
| cy_jsvmp | https://github.com/2833844911/cy_jsvmp | Babel AST + custom stack-based VM; **each obfuscation run dynamically generates its own opcode mapping**; ES5-leaning |
| facelessJsvmp | https://github.com/Alanhays/facelessJsvmp | A JSVMP protection implementation |
| jsvmp | https://github.com/baishuijianjia/jsvmp | Stack-based JS VM, Babel AST + bytecode compilation + sandboxed execution |
| obfuscator.io VM | https://obfuscator.io | Commercial Pro; see the `vm*` options in `js-deobfuscation.md` |

**Real-world samples**: Ruishu VMP (v4/v5/v6), Douyin X-Bogus / abogus, Tencent `tdc.js` (`__TENCENT_CHAOS_VM`).

### De-virtualization methods

1. **Instrument opcodes + PC tracing**: print `(PC, opcode, stack/register snapshot)` before the Dispatcher's `switch` and reconstruct the execution trace
2. **Recover the `switch-case` via AST**: restore the handler into readable branches keyed by opcode number, then do per-opcode AST rewriting
3. **Source-level instrumentation**: rewrite the response at the HTTP layer and inject instrumentation code, avoiding changes to a manually unpacked artifact
4. **The PC-increment trap (a very common pitfall)**: `opFunc.apply(undefined, args)` and `opFunc(...args)` have different semantics under `PC += ++PC`-style expressions — the former yields 3, the latter (with `var v = ++PC; PC += v` first) yields 4. This is a key clue for pinning down implementation details
5. **The `undefined` ambiguity of the `ret` opcode**: when the return value is `undefined`, a normal return cannot be distinguished from a VM exit
6. **The `opcode[++PC]` loader abstraction**: wrap instruction fetch in a standalone function so it can be uniformly swapped for a logging version
7. **Scale reality**: a community case records needing to execute **880,000 instructions** before exiting the VM — pure single-step tracing is not viable; you must do **converging sampling + critical-path backtracking**

### Instrumentation / tracing tools

| Tool | Repository | Capability |
|---|---|---|
| v_jstools | https://github.com/cilame/v_jstools | Chrome extension: JS debugging, hooking, AST processing, WASM support |
| hello_js_reverse_skill | https://github.com/WhiteNightShadow/hello_js_reverse_skill | AI-driven reverse-engineering Skill; includes `hook_jsvmp_interpreter` (proxy / transparent dual mode), `instrumentation(action='install'\|'log'\|'stop'\|'reload')`, `inject_hook_preset` (xhr/fetch/crypto/websocket/debugger_bypass/cookie/runtime_probe), `network_capture`, `get_request_initiator`, `intercept_request` |

> Dedicated de-virtualization tools (the `dexvm` / `vmp` family) are **unverified** — no verifiable repository was found.

### Relationship to environment simulation

JSVMP often appears together with environment simulation: after the VM code runs it still needs a browser environment. The practical order is:

1. First use environment simulation to get the VM code running through (producing a result counts as success)
2. If you need to understand the algorithm, then do opcode-level instrumentation tracing
3. If you only need the result, **stop at step 1** — do not do profitless opcode recovery just for the sake of "understanding"

## Sources

- Environment simulation principles and detection points: https://github.com/AlienwareHe/awesome-reverse/blob/main/js/browser-env-fix.md
- Xie-mou testab environment-simulation field report: https://cloud.tencent.com/developer/article/2446185
- A native function's prototype must be undefined: http://program.robinjia.cc/page/5
- Environment simulation framework comparison: https://www.cnblogs.com/kanadeblisst/p/18177803
- Testing several open-source environment simulation frameworks: https://juejin.cn/post/7366082235243741221
- sdenv: https://github.com/pysunday/sdenv
- Node vm documentation (the not-a-security-mechanism statement): https://nodejs.org/api/vm.html
- No universal tooling for JSVMP (obfuscator.io official position): https://obfuscator.io
- cy_jsvmp: https://github.com/2833844911/cy_jsvmp
- JSVMP instrumentation as an aid to environment simulation: https://cloud.tencent.com/developer/article/2446185
- Tencent `__TENCENT_CHAOS_VM`: https://bbs.kanxue.com/thread-290429.htm
