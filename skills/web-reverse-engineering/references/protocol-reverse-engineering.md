# Protocol Reverse Engineering

Beyond HTTP/HTTPS, modern applications use WebSocket, gRPC, custom TCP, and UDP protocols. Understanding these unlocks data sources invisible to standard web scraping.

> For advanced coverage (protobuf without `.proto`, gRPC reflection and gRPC-Web framing, Kaitai/Wireshark dissectors, TLS decryption, mitmproxy internals), see `protocol-reverse-engineering-advanced.md`.

## Protocol Identification

```bash
# Quick protocol fingerprint
nmap -sV -p 443 target.com

# TLS inspection
openssl s_client -connect target.com:443 -servername target.com

# ALPN negotiation (HTTP/2, HTTP/3)
openssl s_client -alpn h2 -connect target.com:443

# Certificate inspection
openssl x509 -in cert.pem -text -noout
```

## WebSocket

### Identification

Look for:
- `Upgrade: websocket` headers
- `Sec-WebSocket-Key` / `Sec-WebSocket-Accept`
- `ws://` or `wss://` URLs

### Inspection

```bash
# wscat for manual testing
npm install -g wscat
wscat -c wss://target.com/socket

# websocat for advanced use (curl for WebSockets)
websocat wss://target.com/socket

# mitmproxy supports WebSocket interception
mitmproxy --mode reverse:wss://target.com:443@localhost:8080
```

**mitmproxy WebSocket limits you should know before relying on it**:

- `flow.websocket` exists since v6, but **message replay is not supported**
- **PING/PONG frames are not written to the flow** — if the protocol uses them for liveness, you will not see them
- WebSocket messages are only captured in regular proxy / reverse proxy modes

### Replay Pattern

```python
import websocket
import json

ws = websocket.create_connection("wss://target.com/socket")
ws.send(json.dumps({"type": "subscribe", "channel": "updates"}))

while True:
    msg = ws.recv()
    data = json.loads(msg)
    print(data)
```

### Authentication Patterns

| Method | How to replicate |
|---|---|
| Cookie-based | Send same cookies from web session |
| Token in query | `wss://target.com/socket?token=...` |
| First message auth | Send auth frame immediately after connect |
| JWT in Sec-WebSocket-Protocol | Extract from browser DevTools |

## gRPC and gRPC-Web

### Identification

- Content-Type: `application/grpc`, `application/grpc-web`
- HTTP/2 POST to paths like `/package.Service/Method`
- Binary protobuf payloads

### Tooling

```bash
# Server reflection is the highest-value first move — it can enumerate the whole API
# surface with zero reverse engineering.
grpcurl -plaintext target.com:50051 list
grpcurl -plaintext target.com:50051 describe package.Service

# Call a method
grpcurl -plaintext -d '{"id": 1}' target.com:50051 package.Service/Method
```

If reflection is disabled, recover the `.proto` from:
1. the client bundle (mobile apps often ship `.proto` descriptors)
2. `blackboxprotobuf` inference from captured traffic
3. `grpcui` against a local stub

### Proto Discovery

When `.proto` files are unavailable:

```bash
pip install blackboxprotobuf
```

```python
from blackboxprotobuf import decode_message, encode_message

with open("payload.bin", "rb") as f:
    data = f.read()

message, typedef = decode_message(data)
print(message)

# blackboxprotobuf can also RE-ENCODE with the inferred typedef.
# This is what makes in-proxy request modification possible without a .proto.
modified = encode_message({**message, "3": b"new value"}, typedef)
```

**Note**: `blackboxprotobuf` is available as a Python library and as a Burp extension. The Burp extension is the practical route for interactive work.

### Reverse Engineering Protobuf

Key protobuf patterns:
- Varint fields: `0x08`, `0x10`, `0x18` (field 1, 2, 3 with wire type 0)
- Length-delimited: `0x0a` (field 1, wire type 2) followed by length byte
- Fixed32/64: `0x0d`, `0x09`, `0x11`, `0x19`

Wire type is the low 3 bits of the tag byte; field number is `tag >> 3`. This is what lets you read an unknown message by hand.

### gRPC-Web Frame Format

Browser gRPC is not raw gRPC. The body is a sequence of length-prefixed frames:

```text
[1 byte flags][4 byte big-endian length][payload]
```

- flags bit 0 set (0x80) = trailer frame, not message
- gRPC-Web over HTTP/1 requires base64 encoding when the `Content-Type` ends in `+proto`

## Server-Sent Events (SSE)

```bash
# Direct curl
curl -N -H "Accept: text/event-stream" \
  -H "Authorization: Bearer ..." \
  https://target.com/events
```

SSE is simpler than WebSocket: standard HTTP, server pushes text/events. Read it as a **stream** — do not wait for the response to end, because it does not end.

## Custom TCP/UDP Protocols

### Reconnaissance

```bash
nmap -p- target.com
nmap -sV -sC target.com
nc target.com 1337
sudo tcpdump -i any -w capture.pcap host target.com
```

### Analysis with Wireshark

1. Capture traffic during known operation
2. Filter: `tcp.port == 1337`
3. Follow TCP stream: `Analyze → Follow → TCP Stream`
4. Look for patterns:
   - Fixed-length headers
   - Magic bytes / signatures
   - Length-prefix framing
   - Delimiter-based framing (newline, null byte)

### Common Framing Patterns

| Pattern | Structure | Example |
|---|---|---|
| Length-prefix | `[4 bytes length][payload]` | Protobuf, many game protocols |
| Delimiter | `payload\r\n` | Redis, HTTP/1 |
| Fixed header | `[16 byte header][variable body]` | Binary protocols |
| TLV | `[type][length][value]` | ASN.1, some financial protocols |

### Replay with Custom Client

```python
import socket
import struct

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("target.com", 1337))

# Length-prefix protocol
payload = b'{"action":"query"}'
header = struct.pack(">I", len(payload))  # big-endian 4-byte length
sock.sendall(header + payload)

response = sock.recv(4096)
print(response)
```

## HTTP/3 and QUIC

```bash
curl -I --http3 https://target.com
curl --http2 https://target.com
```

Tooling:
- `aioquic` (Python) for custom QUIC clients
- `ngtcp2` (C) for low-level QUIC
- Chrome's `chrome://net-export/` for browser-side inspection

**Why this matters for RE**: QUIC is a **new detection layer**. The initial packet's transport parameters, ALPN, and GREASE behavior are fingerprintable the same way TLS ClientHello is. If a target serves HTTP/3 and you fall back to HTTP/2 while claiming to be a modern browser, that is a signal.

## MQTT (IoT/Messaging)

```bash
mosquitto_sub -h broker.target.com -t "topic/#"
mosquitto_pub -h broker.target.com -t "topic/test" -m "payload"
```

```bash
pip install paho-mqtt
```

Common in IoT, some real-time dashboards. Wireshark has a built-in MQTT dissector; CoAP has one too.

## GraphQL (over HTTP)

Not a transport protocol, but a query language that requires specific interaction patterns:

```bash
# Introspection query (often disabled in production)
curl -X POST https://target.com/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ __schema { types { name } } }"}'

# Standard query
curl -X POST https://target.com/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "query { user(id: 1) { name email } }"}'
```

GraphQL-specific RE:
- Look for persisted queries (hash-based) — you may be able to replay the hash without the query body
- Batching (array of operations) — useful for rate-limit efficiency
- Fragments and variable definitions
- Error messages leak schema info
- **If introspection is disabled**, recover the schema from the client bundle. The queries are usually plain string literals.

## Message Queues

| System | Protocol | Access pattern |
|---|---|---|
| RabbitMQ | AMQP | `pika` (Python), `amqplib` (Node) |
| Kafka | Binary TCP | `kafka-python`, `confluent-kafka` |
| Redis | RESP | `redis-py` |
| NATS | Text/binary | `nats-py`, `nats.js` |
| ZeroMQ | Custom framing | `pyzmq` |

These are rarely directly scrapable but may be relevant for internal infrastructure RE.

## TLS Decryption

If you control the client or can hook it, decrypting captured traffic is far better than reverse-engineering it from ciphertext.

| Method | How |
|---|---|
| `SSLKEYLOGFILE` | Set the env var, point Wireshark at the keylog file (`Preferences → Protocols → TLS → (Pre)-Master-Secret log filename`) |
| Frida hook | Hook `SSL_write` / `SSL_read` in the target process |
| `ecapture` | eBPF uprobe, **no CA and no client modification needed** |
| Android | Hook `Conscrypt` / `BoringSSL` at the JNI boundary |

**Standard**: TLS key logging was published as **RFC 9850** in 2026-07, though most tooling still cites the older NSS draft. Functionally equivalent.

## Protocol Analysis Workflow

```text
1. Identify transport (TCP/UDP/QUIC/WebSocket)
2. Check for server reflection / introspection FIRST (gRPC, GraphQL)
3. Capture traffic during known operations
4. Look for framing patterns (length, delimiter, fixed)
5. Map message types to operations
6. Find authentication mechanism
7. Write minimal client to reproduce
8. Iterate until full protocol coverage
```

**Step 2 is the highest-leverage step and the most commonly skipped.** For gRPC, `grpcurl list` can hand you the entire API surface. For GraphQL, introspection does the same. Check before you reverse-engineer anything.

## Tools Summary

| Task | Tool |
|---|---|
| Packet capture | Wireshark, tcpdump, tshark |
| Traffic replay | `tcpreplay`, custom scripts |
| Binary protocol decode | `ImHex`, `010 Editor`, `Kaitai Struct` |
| Structured binary templates | `Kaitai Web IDE` |
| Protocol fuzzing | `Boofuzz`, `AFL`, `Peach` |
| TLS inspection | `openssl s_client`, `sslyze`, **`ecapture`** |
| TLS keylog | `SSLKEYLOGFILE` + Wireshark (RFC 9850) |
| HTTP/2 frame analysis | Wireshark, `nghttp`, `curl --trace` |
| gRPC | `grpcurl`, `grpcui`, Postman |
| MQTT / CoAP | `mosquitto`, `paho-mqtt`, Wireshark dissectors |
| Protocol grammar inference | `Netzob`, `FieldHunter`, `Discoverer` |

Protocol RE is the bridge between web scraping and systems programming. Master it and no data source is out of reach.
