/**
 * signature_probe.js - Locate where a request parameter is generated.
 *
 * Purpose: when an API has an opaque signed parameter (sign / token / w / blackbox),
 * you need to find the generation point before you can replicate it. This script
 * instruments every likely call site and prints a labelled trace, so you can see
 * which one actually produces the value.
 *
 * Usage:
 *   1. Open the target page in a real browser
 *   2. Open DevTools console
 *   3. Paste this whole file
 *   4. Trigger the request you care about
 *   5. Read the numbered trace
 *
 * Then narrow down: take the trace index that fired right before the request and
 * set a breakpoint at that call site to walk up the stack.
 */

(() => {
  const TRACE = [];
  let seq = 0;

  const record = (tag, detail) => {
    seq += 1;
    const entry = { n: seq, tag, detail, stack: new Error().stack };
    TRACE.push(entry);
    console.groupCollapsed(`#${seq} [${tag}]`);
    console.log(detail);
    console.trace("call site");
    console.groupEnd();
  };

  // Expose for later inspection without scrolling
  window.__SIG_TRACE = TRACE;
  window.__sigDump = (n) => {
    const e = TRACE.find((x) => x.n === n);
    if (e) console.log(`#${e.n} [${e.tag}]`, e.detail, "\n", e.stack);
    return e;
  };

  // Each section installs independently. A failure in one (a missing API, a frozen
  // prototype, a page that already wrapped it) must not prevent the others from
  // installing -- otherwise a single unavailable global silently disables the probe.
  const failed = [];
  const section = (name, fn) => {
    try {
      fn();
    } catch (e) {
      failed.push(`${name}: ${e.message}`);
    }
  };

  // ---- 1. XHR: capture final request body + headers ----
  section("xhr", () => {
    const XHR_open = XMLHttpRequest.prototype.open;
    const XHR_send = XMLHttpRequest.prototype.send;
    const XHR_setHeader = XMLHttpRequest.prototype.setRequestHeader;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__probe = { method, url, headers: {} };
      return XHR_open.apply(this, arguments);
    };

    XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
      if (this.__probe) this.__probe.headers[k] = v;
      return XHR_setHeader.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function (body) {
      record("xhr.send", {
        url: this.__probe && this.__probe.url,
        method: this.__probe && this.__probe.method,
        headers: this.__probe && this.__probe.headers,
        body: typeof body === "string" ? body.slice(0, 2000) : body,
      });
      return XHR_send.apply(this, arguments);
    };
  });

  // ---- 2. fetch ----
  section("fetch", () => {
    const origFetch = window.fetch;
    if (typeof origFetch !== "function") return;
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input && input.url;
      record("fetch", {
        url,
        method: (init && init.method) || "GET",
        headers: init && init.headers,
        body: init && typeof init.body === "string" ? init.body.slice(0, 2000) : init && init.body,
      });
      return origFetch.apply(this, arguments);
    };
  });

  // ---- 3. Cookie writes: the classic signature delivery channel ----
  section("cookie", () => {
    const docProto =
      (typeof Document !== "undefined" && Document.prototype) ||
      (typeof HTMLDocument !== "undefined" && HTMLDocument.prototype);
    const cookieDesc = docProto && Object.getOwnPropertyDescriptor(docProto, "cookie");
    if (!cookieDesc || !cookieDesc.set) return;
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get() {
        return cookieDesc.get.call(this);
      },
      set(v) {
        record("cookie.set", { value: String(v).slice(0, 500) });
        return cookieDesc.set.call(this, v);
      },
    });
  });

  // ---- 4. Crypto primitives: catch the actual encryption call ----
  section("crypto.subtle", () => {
    const cryptoTags = [
      ["crypto.subtle.digest", "digest"],
      ["crypto.subtle.encrypt", "encrypt"],
      ["crypto.subtle.sign", "sign"],
    ];
    if (!window.crypto || !window.crypto.subtle) return;

    cryptoTags.forEach(([tag, name]) => {
      try {
        const obj = window.crypto.subtle;
        const orig = obj[name];
        if (!orig) return;
        obj[name] = function (algo, ...rest) {
          record(tag, { algo: algo && (algo.name || algo) });
          return orig.apply(this, [algo, ...rest]);
        };
      } catch (e) {
        /* subtle may be unavailable on insecure origins */
      }
    });
  });

  // ---- 5. Common library entry points ----
  section("libraries", () => {
    const libraryHooks = [
      "JSEncrypt.setPublicKey",
      "CryptoJS.AES.encrypt",
      "CryptoJS.MD5",
      "sm2.doEncrypt",
      "sm4.encrypt",
    ];

    libraryHooks.forEach((tag) => {
      try {
        const parts = tag.split(".");
        const fnName = parts.pop();
        let obj = window;
        for (const p of parts) obj = obj && obj[p];
        if (!obj || typeof obj[fnName] !== "function") return;
        const orig = obj[fnName];
        obj[fnName] = function (...args) {
          record(tag, {
            args: args.map((a) => {
              if (typeof a === "string") return a.slice(0, 200);
              if (a && typeof a === "object") {
                try { return JSON.stringify(a).slice(0, 200); } catch { return "[object]"; }
              }
              return a;
            }),
          });
          return orig.apply(this, args);
        };
      } catch (e) {
        /* library not present */
      }
    });
  });

  // ---- 6. Long-string interceptor: catch custom encryption output ----
  // Obfuscated sites often build the signature inline rather than via a known library.
  // Watching for suspiciously long hex/base64 strings catches those.
  section("fromCharCode", () => {
    const SUSPICIOUS = /^[A-Za-z0-9+/=]{32,}$|^[0-9a-fA-F]{32,}$/;
    const seenStrings = new Set();

    const origStringFromCharCode = String.fromCharCode;
    String.fromCharCode = function (...codes) {
      const out = origStringFromCharCode.apply(this, codes);
      if (out.length >= 32 && SUSPICIOUS.test(out) && !seenStrings.has(out)) {
        seenStrings.add(out);
        record("string.fromCharCode.long", { length: out.length, sample: out.slice(0, 120) });
      }
      return out;
    };
  });

  console.log(
    "%c[signature_probe] installed",
    "color:#0a0;font-weight:bold",
    "\n  Trace: window.__SIG_TRACE" +
    "\n  Inspect one entry: window.__sigDump(3)" +
    "\n  Next step: find the trace entry immediately preceding your target request," +
    "\n             then set a breakpoint at that call site and walk up the stack."
  );

  if (failed.length) {
    console.warn(
      "[signature_probe] these hooks did NOT install (the rest still work):\n  " +
      failed.join("\n  ")
    );
  }
})();
