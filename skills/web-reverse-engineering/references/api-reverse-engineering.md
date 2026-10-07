# API Reverse Engineering

Direct API extraction is usually more stable than HTML parsing.

## Workflow

1. reproduce user flow in browser
2. capture XHR/fetch requests in DevTools
3. identify auth, pagination, filters, and anti-replay params
4. replay request outside browser
5. parameterize and productionize

## Tooling

| Tool | Use case | Install |
|---|---|---|
| Browser DevTools | request discovery, payload inspection | built-in |
| mitmproxy | intercept/modify traffic, mobile app traffic | `pip install mitmproxy` |
| **mitmproxy2swagger** | auto-derive OpenAPI/Swagger from captured traffic | https://github.com/alufers/mitmproxy2swagger |
| Charles Proxy | GUI-based interception/replay | commercial |
| **Reqable** (原 HttpCanary) | mobile-first GUI proxy | https://reqable.com |
| Frida | runtime hooking, SSL pinning bypass | project-specific |
| **grpcurl** | gRPC with server reflection | https://github.com/fullstorydev/grpcurl |
| **pbtk / blackboxprotobuf** | protobuf without `.proto` | see `protocol-reverse-engineering-advanced.md` |

## DevTools Checklist

For each useful request, capture:
- URL and method
- query/body params
- auth headers/cookies
- **header order** (it is itself a fingerprint)
- required ordering of prior calls
- response schema and pagination tokens

## Replay Pattern

```python
from curl_cffi import requests

url = "https://target.example/api/search"
headers = {
    "Authorization": "Bearer <token>",
    "Accept": "application/json",
}
params = {"q": "keyword", "page": 1}

resp = requests.get(url, headers=headers, params=params, impersonate="chrome", timeout=20)
print(resp.status_code)
print(resp.json())
```

Use `curl_cffi` rather than plain `requests` — the TLS fingerprint matters even for API endpoints on protected targets.

## Finding Hidden Endpoints

The SPA page route is usually **not** the API route. Methods to recover the real paths:

| Method | How |
|---|---|
| Grep the bundles | `grep -oE '"/(api\|v[0-9])/[a-zA-Z0-9_/?=&-]+"' app.js \| sort -u` |
| Hook fetch/XHR | Log every URL the app actually calls |
| Source map recovery | `sourcesContent` gives you original filenames and route definitions |
| Hook the router | Most SPA routers expose a route table object |
| mitmproxy2swagger | Derive the full surface from real traffic |

```js
// Enumerate every endpoint the app calls, including ones you never triggered manually
const origFetch = window.fetch;
window.fetch = function (...args) {
  console.log('[fetch]', args[0]);
  return origFetch.apply(this, args);
};
const origOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (m, u) {
  console.log('[xhr]', m, u);
  return origOpen.apply(this, arguments);
};
```

## Token and Signature Handling

Common blockers:
- short-lived access tokens
- one-time nonce values
- HMAC signatures tied to timestamps/body
- **vendor-signed parameters** (极验 `w`, 数美 `data`, 同盾 `blackbox`)

Mitigation:
- emulate exact call sequence
- implement token refresh lifecycle
- preserve server-expected canonicalization rules for signing

**When a signed parameter blocks you**, do not hand-port the algorithm first. Ask: what is the request volume?

| Volume | Route |
|---|---|
| < 1k/day | RPC to a real browser — call the vendor's own JS |
| 1k–10k/day | environment simulation (run vendor JS in Node) |
| > 10k/day | pure-algorithm reversal |

Full methodology in `signature-parameter-re.md`.

## GraphQL-Specific Notes

| Issue | Approach |
|---|---|
| Introspection disabled | Recover the schema from the client bundle (queries are usually string literals) |
| Persisted queries (APQ) | Either replay the hash, or send the full query with `extensions.persistedQuery` omitted |
| Query depth/complexity limits | Split one large query into several |
| Batching | Most servers accept an array of operations — useful for rate-limit efficiency |

## WebSocket / SSE APIs

If the app uses a persistent channel, the HTTP layer is only the handshake.

- **WebSocket**: mitmproxy has a "WebSocket Messages" tab; `flow.websocket` since v6. Note mitmproxy **does not support message replay**, and PING/PONG are not written to the flow.
- **SSE**: it is plain HTTP with `Content-Type: text/event-stream` — read it as a stream, do not wait for the response to end.
- Custom binary frames: see `protocol-reverse-engineering-advanced.md`.

## Mobile App Angle

Many mobile APIs are simpler than web frontends — but the transport is harder.

Typical steps:
1. set device proxy to mitmproxy/Charles/Reqable
2. install interception cert — **on Android 14+, you must use an APEX-aware module** (see `mobile-app-reverse-engineering.md`)
3. capture app traffic
4. map endpoint families and auth lifecycle

If SSL pinning blocks capture, escalation order: `objection` → `frida-multiple-unpinning` → `ecapture`/`r0capture` (no CA needed) → static patch.

## Production Guardrails

- schema validation for response drift
- endpoint-level rate limiting
- replay tests from stored fixtures
- fallback parser path if API contracts change suddenly
- **version-pin your client fingerprint** — a `curl_cffi` upgrade can change your TLS profile and silently break everything

## Behind a login + Cloudflare?

If the API is gated by both auth and Cloudflare, don't re-implement the login to map it. Inject a
manually-exported session and drive the site's own same-origin `fetch` to enumerate endpoints
read-only. The SPA page route is usually NOT the API route — grep the JS bundles for the real
`/api/...` paths. See `authenticated-session-mapping.md`.

## Failure Signature Table

| Symptom | Likely cause | Fix |
|---|---|---|
| 200 but empty/HTML body | Wrong endpoint (SPA fallback route) | Find the real API path |
| 401 after minutes of working | Token expired | Implement refresh lifecycle |
| 403 with valid token | Missing signed param | See `signature-parameter-re.md` |
| Signature accepted once then rejected | Nonce replay protection | Generate fresh nonce per request |
| Works with one param set, fails with another | Canonicalization order differs | Compare two near-identical requests |

API-first extraction reduces fragility and maintenance cost when done correctly.
