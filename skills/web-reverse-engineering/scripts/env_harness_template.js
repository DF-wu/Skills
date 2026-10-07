/**
 * env_harness_template.js - Environment simulation (bu-huanjing) skeleton for running
 * vendor risk-control JS in Node.
 *
 * Purpose: instead of hand-porting a vendor's signing algorithm, run THEIR code in a
 * controlled browser-like environment and capture the parameters it produces. This is
 * the highest-leverage technique against Chinese risk-control vendors (RiverSecurity, Shumei, Yidun).
 *
 * This is a SKELETON with the detection points that actually matter already handled.
 * Fill in the target-specific parts (marked TODO) for your site.
 *
 * Usage:
 *   npm i jsdom canvas
 *   node env_harness_template.js ./vendor_challenge.js
 *
 * Then call the exported entry point from your own code and read the captured output.
 *
 * IMPORTANT: this uses node:vm, which the Node docs explicitly state is NOT a security
 * boundary. Do not run untrusted code from the open internet without a real sandbox
 * (isolated-vm). Vendor challenge scripts are usually fine, but know the limitation.
 *
 * ---------------------------------------------------------------------------
 * THREE NON-OBVIOUS FACTS ABOUT node:vm THAT THIS FILE HANDLES FOR YOU
 * ---------------------------------------------------------------------------
 * All three were verified empirically on Node 24. Most self-written harnesses get
 * at least one of them wrong.
 *
 * 1. A vm context has its OWN intrinsics. Patching the outer realm's
 *    Function.prototype.toString or String.prototype.indexOf has NO effect on code
 *    running inside the context -- they are different objects. Every spoof must be
 *    installed a second time from inside, via runInContext.
 *
 * 2. Symbol.for() uses a GLOBAL symbol registry that IS shared across vm contexts.
 *    This is what lets you mark a function in one realm and have the spoof in the
 *    other realm recognize the mark.
 *
 * 3. Patching only one realm leaves a bypass. `fn.toString()` resolves the method via
 *    fn's OWN prototype, while `Function.prototype.toString.call(fn)` resolves via the
 *    CALLER's realm. You need both patched, or one of those two forms leaks the real
 *    source code of your stubbed functions.
 */

const fs = require('fs');
const vm = require('vm');
const path = require('path');

// Shared across realms -- this is the whole point of Symbol.for over Symbol().
const NATIVE = Symbol.for('__lcs_native__');

// ---------------------------------------------------------------------------
// 1. Native function spoofing (dual-realm)
// ---------------------------------------------------------------------------

function setNative(obj, key, value) {
  Object.defineProperty(obj, key, {
    enumerable: false,
    configurable: true,
    writable: true,
    value,
  });
}

/**
 * Mark a function so that any patched toString reports it as native.
 * Works across realms because NATIVE lives in the global symbol registry.
 *
 * Note on `prototype`: real native functions that are not constructors have no
 * `prototype`. If your stub is a plain function, it DOES have one, and a careful
 * detector will notice. Call stripPrototype() for non-constructor stubs.
 */
function markNative(fn, name) {
  setNative(fn, NATIVE, `function ${name || fn.name}() { [native code] }`);
  return fn;
}

/** Remove the `prototype` property so the function looks like a non-constructor native. */
function stripPrototype(fn) {
  try {
    delete fn.prototype;
  } catch (e) { /* non-configurable */ }
  return fn;
}

/** Build a patched toString that consults the NATIVE mark. */
function makePatchedToString(originalToString) {
  const patched = function toString() {
    if (typeof this === 'function' && this[NATIVE] !== undefined) {
      return this[NATIVE];
    }
    return originalToString.call(this);
  };
  // The patched function must itself look native, or the check "is toString native?"
  // reveals the patch immediately.
  setNative(patched, NATIVE, 'function toString() { [native code] }');
  return patched;
}

/** Install the toString spoof on the OUTER realm (covers `outerFn.toString()`). */
function installOuterSpoof() {
  const original = Function.prototype.toString;
  setNative(Function.prototype, 'toString', makePatchedToString(original));
}

/**
 * Install the toString spoof INSIDE a context (covers
 * `Function.prototype.toString.call(fn)` and `Reflect.apply`).
 * Fact 1 makes this necessary; fact 3 makes it insufficient on its own.
 */
function installInnerSpoof(context) {
  vm.runInContext(`
(function () {
  var NATIVE = Symbol.for('__lcs_native__');
  var original = Function.prototype.toString;
  var patched = function toString() {
    if (typeof this === 'function' && this[NATIVE] !== undefined) {
      return this[NATIVE];
    }
    return original.call(this);
  };
  Object.defineProperty(Function.prototype, 'toString', {
    enumerable: false, configurable: true, writable: true, value: patched,
  });
  Object.defineProperty(patched, NATIVE, {
    enumerable: false, configurable: true, writable: true,
    value: 'function toString() { [native code] }',
  });
})();
`, context, { filename: 'spoof.js' });
}

// Install on the outer realm at module load, before anything else creates functions.
installOuterSpoof();

// ---------------------------------------------------------------------------
// 1b. Optional dependency resolution
// ---------------------------------------------------------------------------

/**
 * Resolve an optional native dependency from either the skill's own node_modules
 * or the caller's project, so a user-installed package is actually found.
 *
 * Without this, require('canvas') resolves relative to THIS file's directory and
 * silently misses a canvas the user installed in their own project -- producing a
 * confusing "not installed" warning immediately after a successful npm install.
 */
function resolveOptionalDependency(name) {
  const candidates = [
    name,                                            // normal resolution
    path.join(process.cwd(), 'node_modules', name),  // caller's project
    path.join(__dirname, 'node_modules', name),      // skill's own deps
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (e) {
      if (e.code !== 'MODULE_NOT_FOUND') {
        // A real load failure (e.g. missing native binding) is worth surfacing.
        console.warn(`[env] ${name} found at ${candidate} but failed to load: ${e.message}`);
        return null;
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// 2. Build the window object
// ---------------------------------------------------------------------------

function buildWindow() {
  const win = {};

  // --- navigator ---
  // TODO: capture these from a REAL browser session on the target site.
  // Hardcoding plausible-looking values is how people get caught: the risk engine
  // cross-checks relationships (screen vs devicePixelRatio vs hardwareConcurrency).
  const navigator = {
    userAgent: process.env.PROBE_UA ||
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    platform: 'Win32',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh', 'en'],
    hardwareConcurrency: 8,
    deviceMemory: 8,
    maxTouchPoints: 0,
    webdriver: false,
    cookieEnabled: true,
    doNotTrack: null,
    onLine: true,
    plugins: [],
    mimeTypes: [],
    vendor: 'Google Inc.',
    product: 'Gecko',
    appVersion: '5.0 (Windows)',
    appName: 'Netscape',
    appCodeName: 'Mozilla',
  };

  // navigator.plugins must look like a PluginArray, not a plain array.
  const pluginData = [
    { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
  ];
  const pluginArray = pluginData.map((p) => {
    const plugin = Object.create(null);
    Object.assign(plugin, p);
    Object.defineProperty(plugin, Symbol.toStringTag, { value: 'Plugin' });
    return plugin;
  });
  Object.defineProperty(pluginArray, Symbol.toStringTag, { value: 'PluginArray' });
  Object.defineProperty(pluginArray, 'length', { value: pluginData.length, enumerable: false });
  navigator.plugins = pluginArray;

  // --- screen ---
  // TODO: keep these consistent with devicePixelRatio and with the real device.
  const screen = {
    width: 1920,
    height: 1080,
    availWidth: 1920,
    availHeight: 1040,
    colorDepth: 24,
    pixelDepth: 24,
    availLeft: 0,
    availTop: 0,
  };

  // --- location ---
  const location = {
    href: 'https://target.example/',
    protocol: 'https:',
    host: 'target.example',
    hostname: 'target.example',
    port: '',
    pathname: '/',
    search: '',
    hash: '',
    origin: 'https://target.example',
    toString() { return this.href; },
  };

  // --- document ---
  const document = {
    cookie: '',
    referrer: '',
    title: '',
    readyState: 'complete',
    characterSet: 'UTF-8',
    charset: 'UTF-8',
    inputEncoding: 'UTF-8',
    compatMode: 'CSS1Compat',
    hidden: false,
    visibilityState: 'visible',
    documentElement: {
      getAttribute(name) {
        // Some risk engines probe this specifically.
        if (name === 'lang') return 'zh-CN';
        return null;
      },
      clientWidth: 1920,
      clientHeight: 1080,
      style: {},
    },
    body: {
      clientWidth: 1920,
      clientHeight: 1080,
      appendChild() {},
      removeChild() {},
      style: {},
    },
    head: { appendChild() {}, removeChild() {} },
    createElement(tag) {
      return makeElement(tag);
    },
    createTextNode() { return { nodeValue: '' }; },
    getElementsByTagName() { return []; },
    getElementsByClassName() { return []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getElementById() { return null; },
    addEventListener() {},
    removeEventListener() {},
    hasFocus() { return true; },
  };

  // --- Canvas: risk engines hash the rendered output ---
  // Requires node-canvas. Real drawing is mandatory: a stubbed toDataURL is trivially
  // detected because the output must vary with input in a consistent way.
  //
  // Resolution note: this file lives in the skill's scripts/ directory, so a plain
  // require('canvas') resolves against THAT directory and misses a canvas the user
  // installed in their own project. Try both locations.
  const CanvasImpl = resolveOptionalDependency('canvas');
  if (!CanvasImpl) {
    console.warn('[env] node-canvas not installed -- Canvas fingerprinting will fail.');
    console.warn('[env] install it in YOUR PROJECT directory (not the skill dir):');
    console.warn('[env]   npm i canvas');
    console.warn(`[env] cwd is ${process.cwd()}`);
  }

  function makeElement(tag) {
    const el = {
      tagName: String(tag).toUpperCase(),
      style: {},
      attributes: {},
      children: [],
      setAttribute(k, v) { this.attributes[k] = v; },
      getAttribute(k) { return this.attributes[k] ?? null; },
      removeAttribute(k) { delete this.attributes[k]; },
      appendChild(c) { this.children.push(c); return c; },
      removeChild() {},
      addEventListener() {},
      removeEventListener() {},
      getContext(kind) {
        if (!CanvasImpl) return null;
        if (this.__canvas === undefined) {
          this.__canvas = CanvasImpl.createCanvas(this.width || 300, this.height || 150);
        }
        return this.__canvas.getContext(kind);
      },
      toDataURL(...a) {
        if (this.__canvas) return this.__canvas.toDataURL(...a);
        return 'data:image/png;base64,';
      },
      getBoundingClientRect() {
        return { top: 0, left: 0, right: 100, bottom: 100, width: 100, height: 100, x: 0, y: 0 };
      },
      width: 300,
      height: 150,
    };
    Object.defineProperty(el, Symbol.toStringTag, { value: `HTML${el.tagName}Element` });
    return el;
  }

  // --- storage ---
  const makeStorage = () => {
    const store = new Map();
    return {
      getItem(k) { return store.has(String(k)) ? store.get(String(k)) : null; },
      setItem(k, v) { store.set(String(k), String(v)); },
      removeItem(k) { store.delete(String(k)); },
      clear() { store.clear(); },
      key(i) { return Array.from(store.keys())[i] ?? null; },
      get length() { return store.size; },
    };
  };

  // --- crypto ---
  const nodeCrypto = require('crypto');
  const crypto = {
    getRandomValues(arr) {
      const bytes = nodeCrypto.randomBytes(arr.length);
      for (let i = 0; i < arr.length; i++) arr[i] = bytes[i];
      return arr;
    },
    randomUUID() { return nodeCrypto.randomUUID(); },
    subtle: (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.subtle) || undefined,
  };

  // --- Assemble ---
  const startTime = Date.now();
  Object.assign(win, {
    navigator,
    screen,
    location,
    document,
    localStorage: makeStorage(),
    sessionStorage: makeStorage(),
    history: { length: 1, back() {}, forward() {}, go() {}, pushState() {}, replaceState() {} },
    crypto,
    performance: { now: () => Date.now() - startTime, timeOrigin: startTime },
    innerWidth: 1920,
    innerHeight: 1080,
    outerWidth: 1920,
    outerHeight: 1080,
    screenX: 0,
    screenY: 0,
    pageXOffset: 0,
    pageYOffset: 0,
    scrollX: 0,
    scrollY: 0,
    devicePixelRatio: 1,
    name: '',
    closed: false,
    origin: location.origin,
    isSecureContext: true,
    crossOriginIsolated: false,
    __startTime: startTime,
  });

  // --- Events ---
  win.addEventListener = () => {};
  win.removeEventListener = () => {};
  win.dispatchEvent = () => true;
  win.setTimeout = (fn, ms, ...a) => setTimeout(fn, ms, ...a);
  win.setInterval = (fn, ms, ...a) => setInterval(fn, ms, ...a);
  win.clearTimeout = (id) => clearTimeout(id);
  win.clearInterval = (id) => clearInterval(id);
  win.requestAnimationFrame = (fn) => setTimeout(() => fn(Date.now()), 16);
  win.cancelAnimationFrame = (id) => clearTimeout(id);
  win.atob = (s) => Buffer.from(s, 'base64').toString('binary');
  win.btoa = (s) => Buffer.from(s, 'binary').toString('base64');

  // --- XMLHttpRequest / fetch stubs ---
  // TODO: point these at a real proxy if the challenge script needs to talk to the server.
  const XHR = function XMLHttpRequest() {
    this.open = () => {};
    this.send = () => {};
    this.setRequestHeader = () => {};
    this.getAllResponseHeaders = () => '';
    this.getResponseHeader = () => null;
    this.addEventListener = () => {};
    this.readyState = 4;
    this.status = 200;
    this.responseText = '';
  };
  win.XMLHttpRequest = markNative(XHR, 'XMLHttpRequest');

  const fetchFn = async () => ({ ok: true, status: 200, text: async () => '', json: async () => ({}) });
  win.fetch = markNative(fetchFn, 'fetch');

  // --- chrome object (Chromium-family marker) ---
  win.chrome = {
    runtime: {},
    app: { isInstalled: false },
    csi: () => ({ startE: Date.now(), onloadT: Date.now(), pageT: 1000, tran: 15 }),
    loadTimes: () => ({}),
  };

  // --- console: keep it working but quiet by default ---
  win.console = {
    log: () => {},
    warn: () => {},
    error: (...a) => console.error('[vendor]', ...a),
    info: () => {},
    debug: () => {},
    trace: () => {},
    table: () => {},
    clear: () => {},
  };

  // --- self-references ---
  win.window = win;
  win.self = win;
  win.globalThis = win;
  win.top = win;
  win.parent = win;
  win.frames = win;
  win.opener = null;

  return win;
}

// ---------------------------------------------------------------------------
// 3. Leak cleanup
// ---------------------------------------------------------------------------
// Node-specific artifacts that risk engines look for.
//
// Fact 1 again: every scrub must run INSIDE the context. Patching the outer realm's
// String.prototype.indexOf does nothing to code in the context.

const SCRUB_SOURCE = `
(function () {
  // Remove Node frames at the source rather than patching string methods.
  // This is strictly better than an indexOf patch: it also removes the
  // "node:vm" and "evalmachine" frames, and it cannot be defeated by
  // String.prototype.includes, split, match, or a regex.
  Error.prepareStackTrace = function (err, frames) {
    var kept = [];
    for (var i = 0; i < frames.length; i++) {
      var f = frames[i];
      var fileName = String(f.getFileName() || '');
      var fnName = String(f.getFunctionName() || f.getMethodName() || '');

      // Drop anything that reveals the Node host.
      if (fileName.indexOf('node:') === 0) continue;
      if (fileName.indexOf('internal/') !== -1) continue;
      if (fileName.indexOf('evalmachine') !== -1) continue;
      if (fileName.indexOf('node_modules') !== -1) continue;
      if (fnName.indexOf('runInContext') !== -1) continue;
      if (fnName.indexOf('Script.runIn') !== -1) continue;
      if (fnName.indexOf('Module.') !== -1) continue;
      if (fnName.indexOf('executeUserEntryPoint') !== -1) continue;

      kept.push('    at ' + (f.getFunctionName() || '<anonymous>') +
                ' (' + (fileName || 'unknown') + ':' +
                (f.getLineNumber() || 0) + ':' + (f.getColumnNumber() || 0) + ')');
    }
    var head = err.name + ': ' + err.message;
    return kept.length ? head + '\\n' + kept.join('\\n') : head;
  };

  // Hide Node-only globals. Delete the property so that the 'in' operator is
  // false -- a detector checking ("process" in window) must not see it at all.
  var NODE_GLOBALS = ['process', 'require', 'module', '__dirname', '__filename',
                      'Buffer', 'global', 'setImmediate', 'clearImmediate'];
  for (var i = 0; i < NODE_GLOBALS.length; i++) {
    try {
      if (NODE_GLOBALS[i] in globalThis) { delete globalThis[NODE_GLOBALS[i]]; }
    } catch (e) { /* non-configurable; nothing further we can do */ }
  }
})();
`;

function scrubNodeArtifacts(context) {
  // Must execute inside the context; see the note above.
  vm.runInContext(SCRUB_SOURCE, context, { filename: 'scrub.js' });
}

// ---------------------------------------------------------------------------
// 4. Run
// ---------------------------------------------------------------------------

function run(vendorScriptPath, options = {}) {
  const quiet = options.quiet === true;
  const win = buildWindow();

  // Run inside a vm context so `var x = ...` at top level lands on the window object,
  // matching browser semantics (this is why plain `eval` or `require` does not work).
  const context = vm.createContext(win);

  scrubNodeArtifacts(context);
  // Install the in-context toString spoof. Without this, a vendor script calling
  // Function.prototype.toString.call(stub) reads the stub's real source code.
  installInnerSpoof(context);

  // Freeze AFTER setup: real window/navigator are immutable, and some engines check this.
  try {
    Object.freeze(win.navigator);
    Object.freeze(win.screen);
  } catch (e) { /* ignore */ }

  const code = fs.readFileSync(vendorScriptPath, 'utf8');

  if (!quiet) {
    console.log(`[env] executing ${path.basename(vendorScriptPath)} (${code.length} bytes)`);
  }

  try {
    const script = new vm.Script(code, { filename: 'vendor.js' });
    script.runInContext(context, { timeout: options.timeout || 30000 });
  } catch (err) {
    console.error('[env] vendor script threw:', err.message);
    console.error('[env] the stack below usually names the missing property:');
    console.error(err.stack);
    console.error('\n[env] Add the missing property to buildWindow() and re-run.');
    return null;
  }

  if (!quiet) {
    console.log('[env] vendor script completed without throwing');
  }
  return win;
}

/**
 * Report the values a vendor script left behind. Without this the harness is
 * useless: you would have to guess which globals the script populated.
 */
function reportCaptured(win, extraKeys = []) {
  const known = [
    '$_ts',                    // RiverSecurity dynamic config
    '__captured',              // your own capture point
    '__vendorResults',         // test-harness output
    '__NEXT_DATA__',
    '__INITIAL_STATE__',
    '__NUXT__',
  ].concat(extraKeys);

  console.log('\n=== Captured values ===');

  let found = 0;

  // Known globals
  for (const key of known) {
    if (win[key] !== undefined) {
      found++;
      console.log(`  window.${key} =`, preview(win[key]));
    }
  }

  // document.cookie is the most common challenge delivery channel
  if (win.document && win.document.cookie) {
    found++;
    console.log('  document.cookie =', preview(win.document.cookie));
  }

  // localStorage / sessionStorage
  for (const storeName of ['localStorage', 'sessionStorage']) {
    const store = win[storeName];
    if (!store) continue;
    try {
      for (let i = 0; i < store.length; i++) {
        const k = store.key(i);
        found++;
        console.log(`  ${storeName}.${k} =`, preview(store.getItem(k)));
      }
    } catch (e) { /* storage may not be enumerable */ }
  }

  // Any global the vendor added that we did not expect.
  // Harness-internal keys are excluded so they do not show up as false positives.
  const HARNESS_INTERNAL = new Set(['__startTime']);
  const unexpected = Object.keys(win).filter((k) => {
    if (known.includes(k)) return false;
    if (HARNESS_INTERNAL.has(k)) return false;
    return k.startsWith('__');
  });
  for (const k of unexpected) {
    if (known.includes(k)) continue;
    found++;
    console.log(`  window.${k} =`, preview(win[k]));
  }

  if (found === 0) {
    console.log('  (nothing captured)');
    console.log('  The script may write to a global with an obfuscated name.');
    console.log('  Add a capture point: define a setter on window for the name you expect.');
  }

  return found;
}

function preview(value, max = 200) {
  if (typeof value === 'function') return `[Function ${value.name || 'anonymous'}]`;
  if (typeof value === 'string') {
    return value.length > max ? JSON.stringify(value.slice(0, max)) + `... (${value.length} chars)` : JSON.stringify(value);
  }
  try {
    const s = JSON.stringify(value);
    if (s === undefined) return String(value);
    return s.length > max ? s.slice(0, max) + '...' : s;
  } catch (e) {
    return `[${typeof value}]`;
  }
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

if (require.main === module) {
  const target = process.argv[2];
  if (!target) {
    console.error('Usage: node env_harness_template.js <vendor_script.js>');
    process.exit(1);
  }
  if (!fs.existsSync(target)) {
    console.error(`File not found: ${target}`);
    process.exit(1);
  }
  const win = run(target);
  if (win) reportCaptured(win);
}

module.exports = {
  buildWindow,
  run,
  reportCaptured,
  markNative,
  stripPrototype,
  setNative,
  installOuterSpoof,
  installInnerSpoof,
  NATIVE,
};
