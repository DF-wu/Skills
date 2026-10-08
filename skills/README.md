# skills/

`skills/` is the canonical home for active Agent Skills in this repository.

## Layout policy

- Active skills must live at `skills/<skill-name>/SKILL.md`.
- Do not create parallel top-level `SKILL/`, `SKILLS/`, or scattered skill directories.
- Deprecated skill names should not remain as active duplicates.
- If a retired skill should remain recoverable, move it to `skills/_ARCHIVE/<skill-name>/` and keep its original `SKILL.md` plus a short archive note.
- If a skill is obsolete and not worth preserving, remove it instead of leaving duplicate copies under another directory name.

## Skill-with-source layout

Skills that ship a real tool keep the tool's source alongside the skill body, so
one directory is both the skill and its implementation:

```
skills/<skill-name>/
├── SKILL.md          # the skill body loaded by the agent
├── references/       # supporting docs the skill points at
├── scripts/          # runnable entrypoints
├── src/              # tool source code (go/, python/, ...)
└── tests/            # tests for the tool source
```

Prompt-only skills carry just `SKILL.md` plus `references/`.

## Current active skills

As of 2026-10-06, the active skill directories are:

- `skills/df-meta-mcp/`
- `skills/filehost/`
- `skills/hackmd-browser-crud/`
- `skills/new-api-manage/`
- `skills/nextcloud-use/`
- `skills/qwen3-asr-tts-hf2api/`
- `skills/vits-tts-hf2api/`
- `skills/web-reverse-engineering/`
- `skills/zhenhuan-elegant-chinese/`

## Migration note

These skills were migrated from `DF-wu/TreasureBox` (`SKILLS/`) on 2026-08-19 with
full commit history preserved via `git subtree split`. Tool source for the two
`hf2api` skills was consolidated in from the private `DF-wu/hf2api` repository.

The deprecated `qwen3-hf2api` and `vits-hf2api` directory names were previously
retired in favor of the canonical `qwen3-asr-tts-hf2api` and `vits-tts-hf2api`.
