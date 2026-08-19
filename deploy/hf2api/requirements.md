# hf2api — System Requirements

## 1. Purpose

hf2api wraps HuggingFace Spaces voice AI services into **OpenAI-compatible HTTP APIs** behind a VPN tunnel, enabling any AI agent to perform TTS and ASR by reading a single skill markdown file and calling `localhost` endpoints — without understanding Gradio APIs, HF Space internals, or VPN configuration.

## 2. System Architecture

```
AI Agent (any env) → curl localhost:8820/8830
    → gluetun (VPN, isolates all outbound traffic)
        → qwen3-asr-tts-hf2api (:8820) → Qwen/Qwen3-TTS-Demo + Qwen/Qwen3-ASR (HF Spaces)
        → vits-tts-hf2api  (:8830) → zomehwh/vits-uma-genshin-honkai (HF Space)
```

All outbound traffic routes through gluetun VPN — the host IP is never exposed to upstream services.

## 3. Functional Requirements

### FR-1: Text-to-Speech (TTS)
- **Endpoint**: `POST /v1/audio/speech`
- **Format**: OpenAI Audio API compatible
- **Input**: JSON with `input` (text), `voice` (speaker), `language`, optional voice parameters
- **Output**: `audio/wav` binary stream
- **Services**: Both qwen3-asr-tts-hf2api and vits-tts-hf2api

### FR-2: Automatic Speech Recognition (ASR)
- **Endpoint**: `POST /v1/audio/transcriptions`
- **Format**: OpenAI Audio API compatible
- **Input**: multipart form-data with `file` (audio), optional `language`, `model`
- **Output**: JSON `{"text": "...", "language": "..."}`
- **Services**: qwen3-asr-tts-hf2api only

### FR-3: Model Discovery
- **Endpoint**: `GET /v1/models`
- **Output**: JSON with available models, voices, speakers, languages
- **Services**: Both

### FR-4: Authentication
- Bearer token via `Authorization: Bearer <key>` header
- Enabled only when `API_KEY` environment variable is set
- When not set, all requests are allowed (open access)

### FR-5: CORS
- All responses include CORS headers for browser compatibility
- Preflight `OPTIONS` requests return 204

## 4. Non-Functional Requirements

### NFR-1: Network Isolation
- All outbound HTTP/WebSocket traffic must route through gluetun VPN
- Host machine IP must never be exposed to any upstream service
- `network_mode: "service:gluetun"` enforced in docker-compose

### NFR-2: Pre-Built Docker Images
- No runtime `pip install` — all dependencies pre-installed at build time
- Based on `python:3.13-alpine` for minimal image size
- Single container per service, no build volumes mounted at runtime

### NFR-3: Health Monitoring
- Each API container must expose `GET /health` returning `{"status": "ok"}`
- Docker healthchecks must verify the endpoint is responsive
- gluetun healthcheck verifies VPN connectivity via `ipinfo.io`

### NFR-4: Environment Configuration
- All configuration via environment variables with documented defaults
- No hardcoded values that differ between environments
- `.env` file support via docker compose variable substitution

### NFR-5: Container Security
- Non-root user execution (UID 1001)
- `tini` as PID 1 for proper signal handling
- Minimal Alpine base with only required packages

### NFR-6: Error Resilience
- Upstream errors mapped to appropriate HTTP status codes
- Text length limits enforced at API layer (matching HF Space limits)
- Timeout handling with configurable durations

## 5. Service Specifications

### 5.1 qwen3-asr-tts-hf2api

| Property | Value |
|----------|-------|
| Port | 8820 |
| Upstream TTS | `https://qwen-qwen3-tts-demo.hf.space` |
| Upstream ASR | `https://qwen-qwen3-asr.hf.space` |
| Protocol | Gradio SSE API (`/gradio_api/call/{endpoint}`) |
| Voices | 48 preset voices with OpenAI aliases |
| TTS Languages | 11 (zh, en, ja, ko, de, fr, ru, pt, es, it, auto) |
| ASR Languages | 32 |
| Text Limit | None (GPU timeout only) |
| Request Timeout | 300s |
| Default Voice | cherry |
| Default Language | auto |

### 5.2 vits-tts-hf2api

| Property | Value |
|----------|-------|
| Port | 8830 |
| Upstream | `https://ikechan8370-vits-uma-genshin-honkai.hf.space` (primary) + `https://zomehwh-vits-uma-genshin-honkai.hf.space` (fallback) |
| Protocol | REST API (`/api/generate/`) primary, Gradio 3.x WebSocket fallback |
| Speakers | 500+ anime/game characters (Genshin, HSR, HI3, Uma Musume, etc.) |
| Languages | zh, ja, mix |
| Text Limit | 500 characters (primary), 100 characters (fallback) |
| Request Timeout | 120s |
| Default Speaker | 派蒙 |
| Default Language | mix |

## 6. Deployment

### Requirements
- Docker Engine with Compose plugin
- WireGuard VPN credentials (provider, private key, addresses)
- Outbound internet access

### Deployment Command
```bash
cp .env.example .env    # Edit .env with VPN credentials
docker compose up -d     # Builds images, starts all services
```

### Verification
```bash
curl http://localhost:8820/health   # → {"status": "ok"}
curl http://localhost:8830/health   # → {"status": "ok"}
curl http://localhost:8820/v1/models | python3 -m json.tool
```

## 7. API Compatibility

### OpenAI Audio Speech Compatibility

| Feature | Supported | Notes |
|---------|-----------|-------|
| `input` (text) | ✅ | Required |
| `voice` | ✅ | Preset voices per service |
| `language` | ✅ | Service-specific language sets |
| `speed` | ⚠️ | Qwen3: ignored (warning). VITS: mapped to length_scale |
| `response_format` | ⚠️ | Always returns WAV (warning for other formats) |
| `model` | ✅ | Ignored (single model per service) |

### OpenAI Audio Transcriptions Compatibility

| Feature | Supported | Notes |
|---------|-----------|-------|
| `file` (multipart) | ✅ | WAV, MP3, etc. |
| `language` | ✅ | 32 languages |
| `model` | ⚠️ | `qwen3-asr` or `qwen3-asr:itn` (ITN toggle) |

## 8. Known Limitations

1. VITS text limit is 500 characters (primary) or 100 characters (fallback) — longer text must be split
2. VITS falls back to WebSocket if REST API fails
2. Qwen3 TTS `speed` parameter is not supported by upstream
3. Audio output is always WAV format (no format conversion)
4. Some Qwen3 voices (Chelsea, Luna) occasionally return upstream errors
5. VITS speaker 卡芙卡 (Kafka) fails with `zh` language (upstream bug)
6. Gradio API contracts are implicit — may break if HF Space updates
