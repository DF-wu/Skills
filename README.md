# Skills

df skills in AI era.

Agent Skills for AI coding agents (Claude Code, Codex, Gemini CLI, and friends).
Each skill directory is **both the skill and the source code of the tool it
documents** — the `SKILL.md` an agent loads sits next to the Go/Python/Node
implementation that actually does the work.

## Skills

| Skill | What it does | Ships |
|---|---|---|
| [`df-meta-mcp`](skills/df-meta-mcp/) | Drives the live dfmcp MetaMCP endpoint (121 tools): GitHub, TickTick, HackMD, Grok/Tavily web search, Context7 library docs, DeepWiki repo Q&A. | `scripts/dfmcp` |
| [`new-api-manage`](skills/new-api-manage/) | Real operations against a [QuantumNous/new-api](https://github.com/QuantumNous/new-api) admin API — channels, tokens, users, options, models, vendors, subscriptions, deployments. | `scripts/newapi` |
| [`web-reverse-engineering`](skills/web-reverse-engineering/) | Reverse-engineering playbook: scraping, API RE, mobile/binary RE, JS deobfuscation, anti-bot and WAF strategy, authenticated session mapping. | Python templates |
| [`hackmd-browser-crud`](skills/hackmd-browser-crud/) | Manages HackMD notes via a cookie-backed browser session, avoiding the metered public API. | `scripts/hackmd-web-cli` |
| [`vits-tts-hf2api`](skills/vits-tts-hf2api/) | VITS Chinese/Japanese anime + game character TTS (804 voices — Genshin, Honkai Impact 3rd, Uma Musume, plus seiyuu lookup). | Go CLI + Python lib |
| [`qwen3-asr-tts-hf2api`](skills/qwen3-asr-tts-hf2api/) | Qwen3 TTS and ASR through HuggingFace Spaces. | Python lib |
| [`zhenhuan-elegant-chinese`](skills/zhenhuan-elegant-chinese/) | Generates understated, elegant Traditional Chinese prose in the register of 《甄嬛傳》. | Prompt-only |

## Layout

```
skills/<skill-name>/
├── SKILL.md          # the skill body the agent loads
├── references/       # supporting docs SKILL.md points at
├── scripts/          # runnable entrypoints
├── src/              # tool source code (go/, python/, ...)
└── tests/            # tests for that source
```

Prompt-only skills carry just `SKILL.md` and `references/`.
See [`skills/README.md`](skills/README.md) for the layout policy.

## Install

Point your skill manager at this repo, or symlink a skill straight into your
agent's skills directory:

```bash
git clone https://github.com/DF-wu/Skills.git ~/src/Skills
ln -s ~/src/Skills/skills/df-meta-mcp ~/.claude/skills/df-meta-mcp
```

Claude Code also reads `~/.claude/skills/`; most other agents take a directory
of `SKILL.md` files the same way.

## Building the tools

`vits-tts-hf2api` ships a prebuilt `vits-tts` binary. To rebuild from source:

```bash
cd skills/vits-tts-hf2api/src/go
go build -o ../../vits-tts ./cmd/vits-tts
```

The Python libraries use standard `pyproject.toml` layouts:

```bash
cd skills/vits-tts-hf2api && uv sync && uv run pytest
```

## Provenance

These skills were migrated out of [`DF-wu/TreasureBox`](https://github.com/DF-wu/TreasureBox)
on 2026-08-19 with full commit history preserved. Tool source for the two
`hf2api` skills was consolidated in from a separate private repository, so this
repo is now the single source of truth for both the skills and their tooling.
