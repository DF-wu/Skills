# Protocol Reverse Engineering, Advanced (protobuf / gRPC / custom binary / MQTT / TLS decryption)

When the target does not use HTTP+JSON, protocol-layer capability is required. This document covers the complete toolchain for modern protocol reverse engineering.

## 1. protobuf

**The wire format is TLV**: `(field_number << 3) | wire_type` serves as the key, and four wire types determine the value encoding (varint / length-delimited / 32bit / 64bit).

**The key difficulty**: **type information is not in the message** (both sides agree through a `.proto`). Without a `.proto` you must perform **heuristic inference**: split fields by key → probe for nested messages using length fields → emit a readable tree → manually correct the typedef.

| Tool | Repository | Mechanism |
|---|---|---|
| protobuf-inspector | https://github.com/mildsunrise/protobuf-inspector | Pure Python; probes field by field according to the wire format and emits an indented tree; supports external callback scripts to supply type hints. **No GitHub Release** |
| **pbtk** | https://github.com/marin-m/pbtk | A trio of tools: heuristic deserialization without a `.proto`, **recovering `.proto` definitions from traffic captures (zhua-bao) / binaries**, plus a companion GUI |
| **blackboxprotobuf** | https://github.com/nccgroup/blackboxprotobuf | `decode_message` returns `(dict, typedef)`, and the typedef can be fed back into `encode_message` to **rewrite packets without a .proto**; ships a `mitmproxy/` plugin (`bbpb.py`) and a `burp/` extension |

**blackboxprotobuf's packet-rewriting capability is the core value** — being able to both decode and re-encode means you can modify protobuf requests in real time inside the proxy.

## 2. gRPC

| Tool | Repository | Mechanism |
|---|---|---|
| **grpcurl** | https://github.com/fullstorydev/grpcurl | Uses **server reflection** by default, so `list`/`describe`/`call` work without a `.proto`; `-protoset` can also use an offline descriptor set; supports TLS/mTLS and plaintext |
| grpcui | https://github.com/fullstorydev/grpcui | Renders gRPC methods as browser forms; also relies on reflection |
| mitmproxy-grpc | https://github.com/aarnaut/mitmproxy-grpc | Adds gRPC support to mitmproxy |
| Nope-Proxy | https://github.com/summitt/Nope-Proxy | Burp extension for TCP/UDP non-HTTP proxying, covering WebSocket and custom binary protocols |

### Server Reflection semantics

- Service name `grpc.reflection.v1.ServerReflection` (the older `grpc.reflection.v1alpha` is still widely supported)
- Only one bidirectional-streaming RPC, `ServerReflectionInfo`
- Requests/responses are matched by oneof: `file_by_filename` / `file_containing_symbol` / `file_containing_extension` / `list_services` / `all_extension_numbers_of_type`

**Practical value**: if the target has reflection enabled, **the entire API surface is exposed directly**, with no reverse engineering needed at all.

```bash
grpcurl -plaintext host:port list
grpcurl -plaintext host:port describe svc.Service
grpcurl -plaintext -d '{"id": 1}' host:port svc.Service/Method
```

### gRPC-Web frame format

Source: https://raw.githubusercontent.com/grpc/grpc/master/doc/PROTOCOL-WEB.md

| Item | Rule |
|---|---|
| Frame structure | 1-byte flag + 4-byte **big-endian** length + payload |
| trailer frame | marked by the **highest bit of the flag, `0x80`**; its body is an HTTP/1-style header block (**not carried over an HTTP trailer**) |
| base64 mode | `application/grpc-web-text` uses base64, and **base64 padding does not align with frame boundaries, so streaming decode is mandatory** |
| End of stream | terminates with EOF, not HTTP/2's END_STREAM |

Implementation repository: https://github.com/grpc/grpc-web

### mitmproxy's HTTP/2 capability boundaries

Built on hyper-h2:

- Ignores PRIORITY frames
- Does not support push promise
- **Does not support h2c plaintext**

**Corollary**: gRPC traffic capture = HTTP/2 traffic capture + the protobuf content view; plaintext gRPC requires TLS/ALPN to negotiate h2.

**The truth about protobuf support**: mitmproxy's protobuf support is a **built-in content view, not a standalone addon**. On the Python side it only registers the `protobuf_definitions` option in `mitmproxy/contentviews/_api.py`; **the actual parsing implementation lives in the Rust repository** https://github.com/mitmproxy/mitmproxy_rs . Since mitmproxy 12 an interactive Protobuf / gRPC content view is provided.

**Burp side**: the official BApp "Protobuf Decoder" https://portswigger.net/bappstore/bd8c70d3f1b74679b2a9fed03d36e81a , source https://github.com/PortSwigger/protobuf-decoder , **last updated 2021-08-04 and dependent on Jython 2.7 — no longer an actively maintained artifact**. The blackboxprotobuf mitmproxy plugin should be the primary choice.

## 3. Custom binary protocols

Two routes:

1. **Descriptive parsing**: describe field structure with a declarative DSL and compile it into parsers for multiple languages, iterating and correcting against real messages
2. **Automatic inference**: message alignment from a pcap → field splitting → type inference → state-machine reconstruction

| Tool | Source | Mechanism |
|---|---|---|
| **Kaitai Struct** | https://github.com/kaitai-io/kaitai_struct | `.ksy` declarative description, compiled to C++/C#/Go/Java/JS/Lua/Nim/Perl/PHP/Python/Ruby/Rust |
| **Kaitai Web IDE** | https://ide.kaitai.io/ | Hex view linked to the parsed object tree; right-click a `.ksy` to generate a parser; files stay only in browser local storage; supports `-webide-representation`, `-webide-parse-mode: eager` |
| 010 Editor Binary Templates | https://www.sweetscape.com/010editor/repository/templates/ | C-like syntax templates driving parsing; well suited to length-prefixed and variable-length arrays |
| **Wireshark Lua dissector** | https://www.wireshark.org/docs/wsdg_html_chunked/wsluarm.html | `Proto`/`ProtoField` declare fields, `dissector(buffer, pinfo, tree)` is the callback; must hit a `DissectorTable` or the user's "Decode As"; TCP stream reassembly requires registering `tcp.port` and enabling desegment |
| Netzob | https://github.com/netzob/netzob | pcap → message alignment → field splitting → type inference → **FSM inference**, and can generate a fuzzer in reverse. **Releases stopped at 2.0.0 (2023-01)** |

### Kaitai quick example

```yaml
meta:
  id: my_protocol
  endian: le
seq:
  - id: magic
    contents: [0xAA, 0xBB]
  - id: length
    type: u4
  - id: payload
    size: length
  - id: crc
    type: u2
```

Generate a parser: `ksc -t python my_protocol.ksy`.

### Academic provenance of automatic protocol reverse engineering

| Tool | Provenance |
|---|---|
| Discoverer | 2007 USENIX Security; dynamic binary analysis + shadow execution to infer message formats |
| FieldHunter | 2015/2016; field extraction + type inference. **Third-party partial reimplementation** https://github.com/vs-uulm/fieldhunter (**not the original authors' implementation**) |
| NEMESYS | USENIX WOOT 2018; infers field boundaries from the intrinsic structure of a single message and proposes the Format Match Score |
| NETPLIER | NDSS 2021; models keyword identification as probabilistic inference |
| Survey | Kleber/Maile/Kargl, IEEE COMST 2019, DOI 10.1109/COMST.2018.2867544 |

> **Note**: **no official open-source implementation was found for either Discoverer or FieldHunter**; `vs-uulm/fieldhunter` is only a third-party partial reimplementation and is not equivalent to the paper's implementation.

## 4. MQTT / CoAP / WebSocket

### Built-in dissectors (least effort)

| Protocol | Wireshark field name | Versions covered | Default ports |
|---|---|---|---|
| MQTT | `mqtt` | 1.12.0–4.6.9 | 1883 / 8883 |
| CoAP | `coap` | 1.6.0–4.6.9 | 5683 / 5684 |

- Use **Decode As** for non-standard ports
- CoAP supports Block1/Block2 reassembly and the OSCORE option
- MQTT parses v5 properties
- **`https://wiki.wireshark.org/MQTT` and `/CoAP` both now 404**; the Display Filter Reference should be the authoritative entry point: https://www.wireshark.org/docs/dfref/m/mqtt.html , https://www.wireshark.org/docs/dfref/c/coap.html

### Client tools

| Tool | Repository | Status |
|---|---|---|
| **MQTTX** | https://github.com/emqx/MQTTX | Active. Three forms: desktop/Web/CLI; **the CLI can script pub/sub, which is good for generating traffic** |
| MQTT Explorer | https://github.com/thomasnordquist/MQTT-Explorer | Repository still receives updates, but **releases stopped at v0.3.5 (2019-07)** |
| websocat | https://github.com/vi/websocat | Active. Command-line WebSocket client/server/proxy; **bidirectional stdin/stdout piping makes manual frame replay easy** |

### mitmproxy's WebSocket capability

Built on wsproto:

- **Does not support replaying client/server messages**
- PING/PONG are not written into the flow
- The `flow.websocket` model exists since v6
- Plugins use the `websocket_message` hook plus the `WebSocketMessage` object
- The console has a "WebSocket Messages" tab

**Chrome DevTools**: in the Network panel select a WS connection → Messages tab, which lists Data/Length/Time; binary frames show the opcode name and number.

## 5. TLS decryption

**Core fact**: modern TLS uses PFS (ephemeral key exchange), so **the server private key cannot decrypt already-captured traffic**. Only two viable paths exist:

1. Export session keys (keylog) from the client TLS library and hand them to Wireshark
2. Use a man-in-the-middle proxy (mitmproxy/Charles/Burp) to actively renegotiate

### The SSLKEYLOGFILE mechanism

When a process starts it reads this environment variable and appends the (Pre)-Master Secret plus the TLS 1.3 traffic secrets to the specified file in **NSS Key Log Format**.

| Item | Value |
|---|---|
| Supporting parties | Firefox, Chrome/Chromium (built in since 2014 via BoringSSL; there is also a `--ssl-key-log-file=<path>` argument) |
| **Non-supporting parties** | **Safari and Windows SChannel do not honor this variable** |
| Condition for effect | The browser must be **fully exited and restarted** |
| Original specification | https://nss-crypto.org/reference/security/nss/legacy/key_log_format/index.html |
| **Now standardized as RFC 9850** | https://www.rfc-editor.org/rfc/rfc9850.html (Informational, 2026-07) |
| OpenSSL | ≥ 3.4 reads `SSLKEYLOGFILE` natively; before that the application had to register a keylog callback itself |

**Labels**: `CLIENT_RANDOM`, `CLIENT_HANDSHAKE_TRAFFIC_SECRET`, `SERVER_HANDSHAKE_TRAFFIC_SECRET`, `CLIENT_TRAFFIC_SECRET_0`, `SERVER_TRAFFIC_SECRET_0`, `EXPORTER_SECRET`, `ECH_SECRET`, `ECH_CONFIG`.

**Wireshark usage**:

```
Preferences → Protocols → TLS → (Pre)-Master-Secret log filename   # internal option tls.keylog_file
editcap --inject-secrets tls,keys.txt in.pcap out.pcapng            # freeze into a pcapng Decryption Secrets Block
```

**mitmproxy integration**:

```bash
SSLKEYLOGFILE="$PWD/.mitmproxy/sslkeylogfile.txt" mitmproxy
# If you do not want to pollute browsers in the same shell, use MITMPROXY_SSLKEYLOGFILE instead
```

Official page: https://docs.mitmproxy.org/stable/howto/wireshark-tls/

### Frida hooking `SSL_write` / `SSL_read`

**Principle**: the buffer passed into `SSL_write` is plaintext before encryption, and the buffer written out of `SSL_read` is plaintext after decryption, so hooking them yields plaintext directly; if you want keys instead, hook `SSL_CTX_set_keylog_callback` / BoringSSL `ssl_log_secret`.

| Project | Repository |
|---|---|
| ssl_logger | https://github.com/google/ssl_logger |
| **friTap** | https://github.com/fkie-cad/friTap — active. Covers OpenSSL/BoringSSL/SChannel, outputs cleartext traffic captures or NSS keylogs; includes experimental memory scanning, RC4, Telegram/MTProto parsing, and an **Android arm64 no-symbols fallback** (locating `ssl_log_secret` via keylog label strings) |
| frida-sslkeylog | https://github.com/saleemrashid/frida-sslkeylog |
| Android SSL_read/write Hook | https://github.com/fanxs-t/Android-SSL_read-write-Hook |
| iOS TLS Keylogger | https://github.com/jankais3r/Frida-iOS-15-TLS-Keylogger |

**Key limitation**: **statically linked BoringSSL (Flutter, Chromium, most hardened apps) has no exported symbols**, so `Module.findExportByName` fails and you must scan by byte signature or offset.

## 6. mitmproxy, advanced

### The addon model

The extension point is the **addon** — a Python object implementing specific method names; registering it into the module-level `addons` list is enough to have it loaded.

**HTTP hooks by invocation timing**:

```
requestheaders   → request headers fully read, body still empty
request          → complete request has been read
responseheaders
response
error / http_connect
```

Each hook receives a `mitmproxy.http.HTTPFlow` that can be modified in place (e.g. `flow.response.text = ...` / `flow.response.content = b'...'`).

### Live reload (important)

A script loaded via `-s path/to/script.py` is monitored for file modification time; after a change, within roughly **1 second** the old module is automatically unloaded, then re-imported and re-registered, **with no need to restart the proxy and no loss of other addons or in-flight flow state**.

- Errors raised in `configure` / `running` / at import time → recorded in the event log and the old version is kept unregistered
- Errors raised inside an event handler → logged only; the addon is not unloaded
- **Adding a new script file still requires a restart**

### Verified options and commands

| Item | Source location | Notes |
|---|---|---|
| `connection_strategy` | `mitmproxy/addons/proxyserver.py` | Defaults to `eager`; `lazy` is also available |
| `map_local` | `mitmproxy/addons/maplocal.py` | Maps requests to local files/directories |
| `map_remote` | `mitmproxy/addons/mapremote.py` | Maps requests to a remote host |
| HAR export | `mitmproxy/addons/savehar.py`; the `save.har` command + `hardump` option | Reading HAR is supported via `mitmproxy -r example.har` |
| `tls_passthrough` | `examples/contrib/tls_passthrough.py` | **This is a contrib example script, not a built-in CLI option**; it must be loaded with `-s` |

> **Common misconception**: `tls_passthrough` is widely misreported as a built-in option; it is actually a contrib example. Copying older tutorials and writing `--set tls_passthrough=true` directly will report an unknown option.

### Proxy modes

| Mode | Purpose |
|---|---|
| Regular | Explicit HTTP(S) proxy (default recommendation) |
| Local Capture | `--mode local[:process-name\|:PID]`, capturing local processes |
| **WireGuard** | `--mode wireguard[@addr:port]`, starts a VPN server, capturing external devices or a single Android app |
| Reverse | `reverse:SPEC`, placed in front of a server |
| Transparent | Network-layer redirection, with the client using the proxy machine as its default gateway |
| Upstream | `upstream:SPEC`, chained proxying |
| SOCKS | SOCKS5 server |
| DNS | Scriptable DNS server |

### API reverse-engineering helper

**mitmproxy2swagger** (https://github.com/alufers/mitmproxy2swagger ) can automatically recover OpenAPI/Swagger definitions from traffic.

## Sources

- pbtk: https://github.com/marin-m/pbtk
- blackboxprotobuf: https://github.com/nccgroup/blackboxprotobuf
- protobuf-inspector: https://github.com/mildsunrise/protobuf-inspector
- grpcurl: https://github.com/fullstorydev/grpcurl
- grpcui: https://github.com/fullstorydev/grpcui
- gRPC reflection docs: https://grpc.github.io/grpc/core/md_doc_server-reflection.html
- gRPC reflection guide: https://grpc.io/docs/guides/reflection/
- gRPC-Web spec: https://raw.githubusercontent.com/grpc/grpc/master/doc/PROTOCOL-WEB.md
- grpc-web: https://github.com/grpc/grpc-web
- Kaitai Struct: https://github.com/kaitai-io/kaitai_struct
- Kaitai Web IDE: https://ide.kaitai.io/
- 010 Editor template repository: https://www.sweetscape.com/010editor/repository/templates/
- Wireshark Lua dissector: https://www.wireshark.org/docs/wsdg_html_chunked/wsluarm.html
- Wireshark MQTT field reference: https://www.wireshark.org/docs/dfref/m/mqtt.html
- Wireshark CoAP field reference: https://www.wireshark.org/docs/dfref/c/coap.html
- Netzob: https://github.com/netzob/netzob
- NETPLIER: https://www.ndss-symposium.org/wp-content/uploads/ndss2021_4A-5_24531_paper.pdf
- NEMESYS: https://www.usenix.org/conference/woot18/presentation/kleber
- Discoverer: https://www.usenix.org/conference/16th-usenix-security-symposium/discoverer-automatic-protocol-reverse-engineering-network
- MQTTX: https://github.com/emqx/MQTTX
- websocat: https://github.com/vi/websocat
- NSS Key Log Format: https://nss-crypto.org/reference/security/nss/legacy/key_log_format/index.html
- RFC 9850: https://www.rfc-editor.org/rfc/rfc9850.html
- Wireshark TLS: https://wiki.wireshark.org/TLS
- mitmproxy + Wireshark: https://docs.mitmproxy.org/stable/howto/wireshark-tls/
- friTap: https://github.com/fkie-cad/friTap
- mitmproxy addons: https://docs.mitmproxy.org/stable/addons/overview
- mitmproxy events: https://docs.mitmproxy.org/stable/api/events.html
- mitmproxy modes: https://docs.mitmproxy.org/stable/concepts/modes
- mitmproxy2swagger: https://github.com/alufers/mitmproxy2swagger
- PortSwigger protobuf-decoder: https://github.com/PortSwigger/protobuf-decoder
