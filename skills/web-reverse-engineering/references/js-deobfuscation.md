# JavaScript Deobfuscation and Dynamic Analysis

When target sites load obfuscated JavaScript challenge scripts, you need to reverse them to understand signature generation, token mechanisms, or API call sequences.

## Step 0: Identify the Obfuscator Before Doing Anything

**Do not start hand-deobfuscating.** Identify the tool first — the transformation set determines the approach.

```bash
# AST-based classifier (HumanSecurity)
npx obfuscation-detector path/to/file.js
```

| Detected | Then use |
|---|---|
| `javascript-obfuscator` / obfuscator.io | `obfuscator-io-deobfuscator` (handles control-flow flattening) |
| jsjiami v6 / sojson v5 | Babel AST scripts, `decode-js` |
| webpack bundle | `webcrack` unpack |
| JSVMP | See `environment-simulation-jsvmp.md` — **no automation exists** |
| Unknown / custom | `webcrack` then `REstringer` |

## Obfuscation Types

| Type | Signature | Approach |
|---|---|---|
| Minification | Single-letter variables, no whitespace | Prettier/Beautify restores readability |
| String encryption | Hex/octal/Unicode escapes | Decrypt at runtime, capture output |
| String array | Central array + decode fn + rotation/shuffle IIFE | Constant propagation after resolving rotation |
| Control flow flattening | `while(true) + switch` state machine | AST-based control flow restoration |
| Dead code injection | Unreachable branches | AST pruning |
| Self-defending | Anti-tampering regex self-checks | Patch checks or remove them |
| Virtual machine | Custom bytecode interpreter | Trace VM execution, extract opcodes |
| Domain-locked | `location.host` checks | Override `window.location` before script runs |
| Time-limited | Date-based expiration | Freeze `Date.now()` or override `new Date()` |
| Debug protection | `debugger` traps + `setInterval` | Remove traps; `debugProtectionInterval` semantics changed in v4.0.0 |

## Tool Chain

### Level 1: Surface Cleaning

```bash
npx prettier --write obfuscated.js
npx js-beautify -f obfuscated.js -o clean.js
```

### Level 2: Automated Deobfuscators

| Tool | Command | Best for |
|---|---|---|
| **webcrack** | `npx webcrack obfuscated.js -o out/` | All-round: deobfuscate + unminify + **webpack/browserify unpack**. Node 22 or 24; uses `isolated-vm` |
| **obfuscator-io-deobfuscator** | `npx obfuscator-io-deobfuscator input.js` | obfuscator.io specific. Restores strings, removes proxy functions, simplifies objects/arithmetic/string concat, removes dead code, **reverses control-flow flattening**, auto-detects config, **does not execute untrusted code** |
| **javascript-deobfuscator** | https://deobfuscate.io | General purpose |
| **synchrony** | `synchrony deobfuscate ./obfuscated.js` | Zero-config automatic string decoding. npm package name is `deobfuscator`. **May fail on older obfuscator output** |
| **REstringer** | `restringer <input> [-c] [-m M] [-o out]` | 40+ modules, safe/unsafe split; unsafe runs in `isolated-vm`. Node v20+ |
| **js-deobfuscator** | — | Explicitly includes self-defending + anti-debug removal |

> **Archived — do not rely on**: `de4js` (archived, v1.12.0, no new features since 2021).

### Level 3: AST-Based Custom Transforms

```javascript
const parser = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const generate = require("@babel/generator").default;
const t = require("@babel/types");

const ast = parser.parse(code, { sourceType: "script" });

traverse(ast, {
  BinaryExpression(path) {
    if (t.isStringLiteral(path.node.left) && t.isStringLiteral(path.node.right)) {
      path.replaceWith(t.stringLiteral(path.node.left.value + path.node.right.value));
    }
  }
});
```

Common Babel transforms:
- **Constant folding**: evaluate `1 + 2` → `3`
- **String decryption**: find decrypt function, call it at build time
- **Dead code elimination**: remove unreachable branches
- **Control flow simplification**: unflatten state machines

For `sojson` / `jsjiami` family, the standard pipeline handles: stringArray (with rotation and nested calls), dead code, control-flow flattening (switch), local transforms (Object expressions, string splitting), and custom protections (self-defending, console/debugger blocking).

### Level 4: Dynamic Extraction

When static analysis fails, run the script in a controlled environment and intercept outputs.

```javascript
const originalLog = console.log;
console.log = function(...args) {
  fs.appendFileSync("intercepted.txt", args.join(" ") + "\n");
  return originalLog.apply(this, args);
};

const origToString = Function.prototype.toString;
Function.prototype.toString = function() {
  fs.appendFileSync("functions.txt", origToString.call(this) + "\n---\n");
  return origToString.call(this);
};
```

### Level 5: VM/Bytecode Analysis

For custom VM obfuscators, see `environment-simulation-jsvmp.md`. Short version:

1. Identify the dispatch loop (`while(true)` + `switch`)
2. Extract the bytecode array
3. **Instrument (PC, opcode, stack snapshot)** before the switch
4. Trace to build an opcode-to-behavior map
5. Write a decoder

**Reality check**: obfuscator.io's own documentation states no automated deobfuscator exists for VM-obfuscated code, because each obfuscation compiles to custom bytecode with a unique VM. Community reports describe single samples requiring ~880,000 instructions to exit the VM. Do not expect automation.

## javascript-obfuscator: Option → Reversal Map

If the target used obfuscator.io, this table tells you exactly what to undo.

| Option | Reversal approach | Tool support |
|---|---|---|
| `stringArray` | Locate array var + decode fn → constant propagation | webcrack, obfuscator-io-deobfuscator, synchrony, REstringer |
| `stringArrayEncoding` (base64/rc4) | Identify `atob`/custom RC4 decode fn and execute | obfuscator-io-deobfuscator, REstringer |
| `stringArrayRotate` / `Shuffle` | Resolve the IIFE rotation, compute final order, reorder | synchrony, webcrack |
| `stringArrayWrappers*` | Inline proxy functions, flatten call chains | obfuscator-io-deobfuscator |
| `stringArrayCallsTransform` | Split-call recombination | webcrack |
| `stringArrayIndexShift` / `IndexesType` | Index expression evaluation + constant folding | obfuscator-io-deobfuscator |
| `splitStrings` | String concat constant folding | webcrack, REstringer |
| `controlFlowFlattening` | Restore execution order from state machine | **obfuscator-io-deobfuscator** |
| `deadCodeInjection` | Constant condition eval + unreachable branch removal | javascript-deobfuscator |
| `numbersToExpressions` | Arithmetic constant folding | javascript-deobfuscator |
| `simplify` | Boolean/expression simplification | all mainstream tools |
| `transformObjectKeys` | Object key stringification reversal | webcrack |
| `unicodeEscapeSequence` | Escape decoding | all mainstream tools |
| `selfDefending` | Remove regex self-check + formatting breakage | js-deobfuscator, webcrack |
| `debugProtection` | Remove `debugger` traps + `setInterval` | js-deobfuscator. Manual: replace base64 `debugger` with `console.log(0)` |
| `domainLock` | Remove domain check branch | manual / static rewrite |
| `renameGlobals` / `renameProperties` | **Names cannot be auto-recovered.** Only solution: generation-time `identifierNamesCache` reverse mapping | manual |
| `disableConsoleOutput` | Restore `console.*` | manual |

**Version traps**:

- v4.0.0 **breaking change**: `debugProtectionInterval` changed from boolean to milliseconds
- v3.0.0 **breaking change**: `ignoreRequireImports` → `ignoreImports`, `rotateStringArray` → `stringArrayRotate`, `shuffleStringArray` → `stringArrayShuffle`
- v2.0.0: `stringArrayEncoding` became an array
- v2.9.0: default index type changed from `hexadecimal-numeric-string` to `hexadecimal-number`
- v4.1.0: added `target: 'service-worker'` (not listed in the current README's `target` table — doc lag)

## Common Target Patterns

| What you need | Where to look |
|---|---|
| API signing algorithm | XHR/fetch interceptors, before-send hooks |
| Session token refresh | Cookie setters, `document.cookie` assignments |
| Fingerprint generation | Canvas/WebGL context calls, `navigator` property reads |
| Bot challenge solver | `eval`, `Function`, `setTimeout` with string arguments |
| Anti-debug triggers | `debugger` statements, `console` clear calls |

## Browser-Based Dynamic Analysis

```javascript
// Override key globals before challenge script loads
Object.defineProperty(window, "_0x1234", {
  get() { return this.__secret; },
  set(v) {
    console.log("Secret set:", v);
    this.__secret = v;
  }
});

// Freeze Date to bypass time checks
const frozen = new Date("2024-01-01");
Date.now = () => frozen.getTime();
```

## Webpack / Vite Bundle Analysis

**Webpack**: Hook the chunk-loading global to capture every module's source at registration time.

```js
const orig = Array.prototype.push;
window.webpackChunk_myapp.push = function (chunk) {
  const [ids, modules, runtime] = chunk;
  Object.entries(modules).forEach(([id, fn]) => console.log(id, fn.toString()));
  return orig.apply(this, arguments);
};
```

The global name is `output.chunkLoadingGlobal` (default `'webpackChunk'`) combined with `output.uniqueName`. `webcrack` automates this.

**Vite**: Products are native ESM. The most reliable reconstruction entry is the build manifest — set `build.manifest = true` to emit `.vite/manifest.json` with `file`, `src`, `imports`, `dynamicImports`, `isEntry`, `isDynamicEntry`, `css`, `assets`. Without it, hook `__vitePreload` or parse `import "./chunk-xxx.js"` literals.

## Source Map Recovery

**Highest-value target**: the `sourcesContent` field embeds original source directly — zero-cost recovery.

```text
1. Search the bundle for //# sourceMappingURL=
2. If inline (data:application/json;base64,...), base64-decode it directly
3. Read sourcesContent — if present, you are done
4. Otherwise use SourceMapConsumer.originalPositionFor() to reverse positions
5. If the map is absent on a webpack build, fall back to the bundle-hook method above
```

| Tool | Status |
|---|---|
| `mozilla/source-map` | Active. `SourceMapConsumer.initialize({"lib/mappings.wasm": ...})` for the wasm VLQ decoder |
| `rarecoil/unwebpack-sourcemap` | **Archived** — use a fork (`An-GG/unwebpack-sourcemap`, `1qr4h/unwebpack-sourcemap`) or reimplement (the logic is just: parse map → rebuild tree from `sources`) |

## When to Stop

- You have extracted the algorithm you need
- Further deobfuscation yields no new actionable signals
- Time cost exceeds value of understanding (use managed API instead)

Deobfuscation is time-expensive. Use it for recurring high-value targets, not one-off scrapes.

## Sources

- javascript-obfuscator: https://github.com/javascript-obfuscator/javascript-obfuscator
- obfuscator.io: https://obfuscator.io
- webcrack: https://github.com/j4k0xb/webcrack
- obfuscator-io-deobfuscator: https://github.com/ben-sb/obfuscator-io-deobfuscator
- javascript-deobfuscator: https://github.com/ben-sb/javascript-deobfuscator
- synchrony: https://github.com/relative/synchrony
- REstringer: https://github.com/HumanSecurity/restringer
- obfuscation-detector: https://github.com/HumanSecurity/obfuscation-detector
- js-deobfuscator: https://github.com/kuizuo/js-deobfuscator
- isolated-vm: https://github.com/laverdet/isolated-vm
- debugProtection manual patch: https://github.com/javascript-obfuscator/javascript-obfuscator/issues/95
- jsjiami: https://www.jsjiami.com/sojson.v5.html
- Vite build options: https://cn.vite.dev/config/build-options
- mozilla/source-map: https://github.com/mozilla/source-map
