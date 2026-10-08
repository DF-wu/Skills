---
name: nextcloud-use
description: Operates a Nextcloud server through one Python CLI - WebDAV/OCS with an app password for files, search, trash, versions, shares, users and apps; occ via docker or ssh for server admin; an on-demand MCP sidecar for calendar, contacts, Deck and mail. Use when the user mentions Nextcloud, a cloud drive, uploading or downloading cloud files, share links, WebDAV, OCS, occ, app passwords, quotas, users, groups or trusted domains. Use filehost instead to publish web pages or files as public URLs.
compatibility: Requires python3 (standard library only; tested with 3.12) and HTTPS access to the Nextcloud server. occ and the MCP sidecar additionally need docker on the Nextcloud host, or ssh to that host. curl and jq appear only in optional manual examples in references/.
metadata:
  clawdbot:
    requires:
      bins:
        - python3
---

# nextcloud-use

`scripts/ncloud` is a single-file CLI (python3 standard library) that gives an agent three access layers to one Nextcloud server:

| Layer | Transport | Use it for |
|---|---|---|
| **1. HTTP API** | WebDAV (files), OCS (shares, users, search, notifications), app routes (raw links); Basic auth with an app password | Most tasks; works from any machine or agent runtime |
| **2. occ** | `docker exec -u www-data <container> php occ …`, or a custom occ command, locally or over ssh | Server-side admin: system config, apps, filecache scans, logs, repairs |
| **3. MCP** | On-demand sidecar container, registered in the agent runtime only for one task, then removed | Multi-step calendar / contacts / Deck / mail work |

Commands below are relative to the skill root (`scripts/ncloud …`); from elsewhere call `<skill dir>/scripts/ncloud`. Behaviour was verified on Nextcloud 33 (AIO).

## Before you act (every session)

1. `scripts/ncloud doctor` - checks config, `status.php`, OCS auth, sharing, WebDAV, the raw-link app, occ and the site notes. It stops authenticated checks at the first 401.
2. `scripts/ncloud config notes` - prints the operator's **private site notes**. When doctor's `notes` row says `present`, read them before any other action: they record folders never to scan, shares never to touch, accounts not to modify and local quirks. Stricter notes override the generic advice in this skill. See `references/SITE_NOTES.md`.
3. If doctor shows `ERR config`, fix the configuration (below) first. Never guess a URL, user or password.

## When to use

- Files: list, upload, download, move, copy, delete, restore from trash, versions, favorites, fileid <-> path
- Search by name / MIME / size / date (WebDAV SEARCH) or unified search (full text, contacts, calendar, Deck)
- Shares: create, inspect, update, delete (link, user, group, email); tokens, URLs, permissions, expiry
- Admin: users, groups, apps, system config, trusted domains, filecache scans, logs, setup checks, brute-force resets
- Deciding whether a task needs the API, occ or MCP

**Not for**: publishing web pages or files as public URLs -> the `filehost` skill (built on this one); local file work.

## Key gotchas

- **OCS and app routes need `OCS-APIRequest: true`** or they answer 412 "CSRF check failed". The CLI adds it; `call` adds it too. WebDAV does not need it.
- **WebDAV paths are percent-encoded per segment** (`#`, `?`, `%`, spaces, non-ASCII). The CLI does it; see `references/API_WEBDAV.md` for manual curl.
- **Never retry a 401.** Each failed login is counted per source IP by Nextcloud's brute-force protection: delay 0.1 s x 2^n (n = failures in 12 h, capped at 25 s); HTTP 429 once there are >10 failures in 12 h AND >10 in the last 30 min. Agents behind the same reverse proxy or docker host often share one source IP (often `127.0.0.1`) and therefore one bucket: one bad password slows every agent. Failed share-password attempts count too. Check the credential once (`config show`), then stop. Details: `references/TROUBLESHOOTING.md`.
- **OCS writes are rate-limited per user** (Nextcloud 33 defaults): 20 share creations per 10 min (429 with body `[]`). Reuse existing shares; one share per folder in batch jobs.
- `share list --path X` on external-storage mounts (or nodes you hold fewer permissions on) returns link shares with `token: null`; the CLI refills them with `GET shares/<id>`.
- Share passwords work with form-encoded or JSON bodies. A subcommand's `--password` (share or new-user password) is never used as the login.
- OCS `message` strings are localized; decide on `ocs.meta.statuscode`, not the text.
- A link share created with `permissions=1` comes back as **17** (READ+SHARE). That is normal.
- `occ config:system:get <key>` exiting 1 means "not set", not an error.
- **occ is deny-by-default** in this CLI: only a read-only allow-list runs without `--yes`; full command names only (abbreviations are rejected even with `--yes`).
- **`files:scan` only on explicit subtrees** (`--path=/<user>/files/<subtree>`), and only with the user's consent. A broad scan (`--all`, `<user>`, `--unscanned`, `files_external:scan <mount_id>`) while an external storage's backing mount is missing makes the scanner treat the empty mount as deleted and wipe its filecache rows (previews, tags, shares on them). The site notes list such mounts.
- Files >= 64 MiB use chunked upload v2 automatically (resumable, per-chunk retry). Lower `NEXTCLOUD_CHUNK_THRESHOLD_MB` if a reverse proxy rejects large bodies (HTML 413).
- Delete moves to the trash bin (`trash restore`); **deleting a share is final** and its token dies at once.
- Nextcloud has no MCP server unless an ExApp provides one; this skill runs its own sidecar on demand (`references/MCP.md`).

## Configuration

Precedence: global flags > process environment > env file. Env file search order: `$NEXTCLOUD_USE_ENV` (must exist if set), `$XDG_CONFIG_HOME/nextcloud-use/env`, `~/.config/nextcloud-use/env` (KEY=VALUE lines, mode 0600). Global `--url/--user/--password` must come **before** the subcommand: `scripts/ncloud --url https://cloud.example.com --user alice ls /`. Prefer the env file for the app password (argv leaks into shell history and `ps`).

| Variable | Meaning | Default |
|---|---|---|
| `NEXTCLOUD_URL` | base URL, e.g. `https://cloud.example.com` | required |
| `NEXTCLOUD_USER` | login name | required |
| `NEXTCLOUD_APP_PASSWORD` | app password (Settings > Security > Devices & sessions) | required for HTTP |
| `NEXTCLOUD_OCC_MODE` | `auto`, `local`, `ssh`, `off` | `auto` |
| `NEXTCLOUD_OCC_CONTAINER` | docker container running Nextcloud | `nextcloud-aio-nextcloud` |
| `NEXTCLOUD_OCC_COMMAND` | occ prefix for non-docker installs, e.g. `sudo -u www-data php /var/www/nextcloud/occ` | unset |
| `NEXTCLOUD_OCC_SSH_HOST` | ssh host/alias of the Nextcloud server (ssh mode) | unset |
| `NEXTCLOUD_MCP_URL` | MCP endpoint override | derived |
| `NEXTCLOUD_MCP_CONTAINER` / `_PORT` | sidecar name / host port bound to 127.0.0.1 | `nextcloud-mcp` / `18000` |
| `NEXTCLOUD_MCP_NETWORK` | docker network the sidecar joins (agent containers reach it by name) | unset |
| `NEXTCLOUD_MCP_APPS` | MCP server apps (`--enable-app`) | `webdav,sharing,calendar,contacts` |
| `NEXTCLOUD_MCP_IMAGE` | sidecar image | `ghcr.io/cbcoutinho/nextcloud-mcp-server:0.198.3` |
| `NEXTCLOUD_USE_NOTES` | private site notes file | `NOTES.md` next to the env file |
| `NEXTCLOUD_INSECURE` | `1` disables TLS verification (warns on stderr; debugging only) | off |
| `NEXTCLOUD_TIMEOUT`, `NEXTCLOUD_CHUNK_THRESHOLD_MB`, `NEXTCLOUD_CHUNK_SIZE_MB` | tuning | 120 s, 64, 20 |

occ transport (`auto`): `NEXTCLOUD_OCC_COMMAND` set -> run it locally (over ssh if `NEXTCLOUD_OCC_SSH_HOST` is set); else the Nextcloud container runs on this machine -> `docker exec -u www-data <container> php occ`; else `NEXTCLOUD_OCC_SSH_HOST` set -> `ssh <host> docker exec …`; else `off` (occ features unavailable, HTTP still works). The default MCP URL follows it: `http://127.0.0.1:$NEXTCLOUD_MCP_PORT/mcp` in local mode, otherwise `http://$NEXTCLOUD_MCP_CONTAINER:8000/mcp`.

```bash
scripts/ncloud config init --url https://cloud.example.com --user alice --occ-ssh-host nc-host   # writes a 0600 template
scripts/ncloud config path      # file that init writes
scripts/ncloud config show      # JSON: url, user, password set/None, missing, occ_mode, mcp_url, notes_file
scripts/ncloud config notes     # print the private site notes
```

`config init` requires `--url` and `--user`; paste the app password into the file afterwards (or pass `--app-password`, which lands in shell history). Missing `NEXTCLOUD_URL`/`NEXTCLOUD_USER` -> exit 2 with guidance. Without an app password, doctor reports `password=MISSING`, skips authenticated checks and exits 2.

New app password (user consent required): `scripts/ncloud app-password agent-x --yes` mints one via occ `user:auth-tokens:add -n` without the login password. The token is printed once: write it into the env file, never into chat. Such tokens work for WebDAV/OCS; only operations that need the login password (e.g. server-side encryption keys) fail. Revoke: `scripts/ncloud occ -- user:auth-tokens:list alice --output=json`, then `scripts/ncloud occ --yes -- user:auth-tokens:delete alice <id>`. OCS `getapppassword` refuses app-password logins (403).

## Choose the layer

| Need | Layer | Why |
|---|---|---|
| List, upload, download, move, search, favorites, trash, versions | **API (WebDAV)** | any runtime; streaming; no host access |
| Shares, tokens, sharees, notifications, activity, unified search, capabilities | **API (OCS)** | JSON, user-scoped permissions |
| Raw link on/off and CSP | **API (app route)** | `files_sharing_raw` has its own API (filehost uses it) |
| System config, trusted domains, app install, cross-user share listing, logs, setup checks, brute-force reset, background jobs | **occ** | no HTTP API, or admin-only server view |
| Files written directly into the data directory, filecache repair, previews, full-text index | **occ** (write, `--yes`) | server-side only; scan explicit subtrees |
| Multi-step calendar / contacts / Deck / mail work, or the user explicitly asks for MCP | **MCP (on demand)** | hand-rolling CalDAV/CardDAV/app REST is costly |

1. **Default to the HTTP CLI.** It behaves the same on any host, container or runtime.
2. **Use occ only when the API cannot do it.** Allow-listed read-only commands (`status`, `check`, `setupchecks`, `list`, `help`, `app:list`, `user:list`, `user:info`, `group:list`, `config:list` without `--private`, `config:system:get`, `config:app:get`, `share:list`, `files:get`, `info:*`, `log:tail`, `router:list`, `security:bruteforce:attempts`, `background-job:list`, `maintenance:mode` without `--on/--off`, `trashbin:size` without a size, …; full list in `references/OCC.md`) run any time. Everything else needs an explicit user request, then `--yes`.
3. **Load MCP only when the HTTP CLI or occ can't do the job** in a few calls. Read `references/MCP.md` first and unload afterwards.
4. "Publish on the web" -> `filehost`; "share with a person or group" -> `ncloud share`.

## Quick start

```bash
scripts/ncloud doctor                 # config, notes, status.php, OCS auth, sharing, WebDAV, raw app, occ
scripts/ncloud doctor --deep --json   # plus share counts, search providers, SEARCH, /raw route
scripts/ncloud --help                 # all subcommands; `scripts/ncloud share --help` for one
scripts/ncloud ls / -l
scripts/ncloud put ./report.pdf /Projects/report.pdf
scripts/ncloud share create /Projects/report.pdf --perm ro --expire 2026-12-31 --label "for review"
```

Order of work: doctor and notes -> high-level subcommands -> `call` for endpoints the CLI does not wrap -> occ (`references/OCC.md`) -> MCP only for app-semantic tasks. Inspect before changing; for guarded operations show the targets to the user and add `--yes` only after consent.

## Command catalogue

```bash
# files
scripts/ncloud ls /Photos --depth 1 -l --json
scripts/ncloud tree /Projects -l
scripts/ncloud stat /Projects --json                       # fileid, etag, permissions, share_types
scripts/ncloud get /Projects/notes.md -                    # to stdout
scripts/ncloud put ./a.pdf /Projects/a.pdf                 # overwrite creates a version
echo "text" | scripts/ncloud put - /Projects/today.md
scripts/ncloud mkdir -p /Projects/2026/q4
scripts/ncloud mv /Projects/a.txt /Archive/a.txt --overwrite
scripts/ncloud upload-dir ./dist /Projects/site --prune --dry-run   # preview deletions; real prune needs --yes
scripts/ncloud download-dir /Projects ./out                # never writes outside ./out
scripts/ncloud rm /Projects/old --yes                      # to trash
scripts/ncloud trash list
scripts/ncloud trash restore "<name>.d<timestamp>"
scripts/ncloud versions list /Projects/a.pdf
scripts/ncloud fileid /Projects/a.pdf
scripts/ncloud path <fileid>
# search
scripts/ncloud search --name "%.pdf" --path /Projects --after 2026-01-01T00:00:00Z --limit 20 -l
scripts/ncloud search --mime image/ --min-size 5000000 --files-only
scripts/ncloud providers
scripts/ncloud usearch "invoice" --provider fulltextsearch --json   # default skips mail (500 without a mail account)
# shares (perm: ro=1, rw=15, upload=4, full=31; bits READ 1, UPDATE 2, CREATE 4, DELETE 8, SHARE 16)
scripts/ncloud share list --path /Projects --json
scripts/ncloud share list --with-me
scripts/ncloud share get <share_id>
scripts/ncloud share create /Projects/x.pdf --perm ro --password "$SHARE_PW" --expire 2026-12-31
scripts/ncloud share create /Projects --type group --with staff --perm ro
scripts/ncloud share create /Inbox --perm upload --yes     # anonymous upload: --yes after consent
scripts/ncloud share update <share_id> --label "client files" --hide-download true
scripts/ncloud share sharees bo
scripts/ncloud share delete <share_id> --yes
# raw links (fully public; workflow lives in filehost)
scripts/ncloud raw list /Projects/site
scripts/ncloud raw enable <share_id> --preset site --raw-only
scripts/ncloud raw url <share_id> index.html
# admin
scripts/ncloud user get bob
scripts/ncloud group members staff
scripts/ncloud app list --filter enabled
scripts/ncloud caps --section files_sharing.public
scripts/ncloud notifications list
scripts/ncloud activity --limit 20
# occ: CLI flags before `--`, occ arguments after it
scripts/ncloud occ -- status --output=json
scripts/ncloud occ -- config:system:get trusted_domains
scripts/ncloud occ -- share:list --owner alice --output=json
scripts/ncloud occ -- log:tail 20
scripts/ncloud occ -- help files:scan
scripts/ncloud occ --print-only -- app:list
scripts/ncloud occ --yes -- files:scan --path=/alice/files/Projects/site
# escape hatch: same-origin auth + OCS-APIRequest added automatically
scripts/ncloud call GET /ocs/v2.php/cloud/capabilities
scripts/ncloud call PROPFIND /remote.php/dav/files/alice/Projects -H "Depth: 0" --no-ocs -i
scripts/ncloud call DELETE /ocs/v2.php/apps/files_sharing/api/v1/shares/<share_id> --yes
```

Link shares need `--yes` when they grant write bits (`rw`, `upload`, `full`) or `--public-upload`; `share update` needs it when it widens a link share (write bits, public upload, `--clear-password`, `--clear-expire`). `raw enable` warns on stderr: raw content is fully public, the share password is not checked (expiry is). After `raw disable`, a later `raw enable` resets rawOnly to false unless `--raw-only` is passed. `call` refuses absolute URLs on another origin unless `--no-auth`, and drops `Authorization` on cross-origin redirects.

## MCP: load -> use -> unload

Load MCP only if all hold: (a) `scripts/ncloud whoami` succeeds and `scripts/ncloud mcp credential` shows the secret file exists (else `scripts/ncloud mcp credential --write`, which verifies the app password once before writing `mcp-basic.b64`, mode 0600, next to the env file); (b) the task is calendar / contacts / Deck / mail semantics or the user asked for MCP; (c) you will unload afterwards. Otherwise report "MCP layer unavailable" and use the API/occ. Never guess tool names.

1. First time only: `scripts/ncloud mcp create --print-only` to review, then `scripts/ncloud mcp create`. It creates a **stopped** container (locally, or on `NEXTCLOUD_OCC_SSH_HOST`) in `multi_user_basic` credential pass-through mode: it stores no credential and every request must carry Basic auth. Replacing an existing one needs `--recreate --yes`.
2. `scripts/ncloud mcp status`; if it is down, `scripts/ncloud mcp start` (cold start ~20 s; refuses and stops the container if `auth_mode` is not `multi_user_basic`).
3. `scripts/ncloud mcp snippet --runtime generic` (or `claude`, `mcporter`) prints the URL and header; register the server for this task only, with the header value read from the secret file or an env var at call time, never pasted into config or chat.
4. List the tools first, then call them by their real names. On 401 / `authentication_required`, unregister immediately: every call replays the bad secret and counts as a failed login.
5. Unregister from the runtime, then `scripts/ncloud mcp stop`. Do not keep Nextcloud MCP registered permanently.

## Safety rules

- Read the site notes first; never touch what they protect without the user naming it explicitly.
- Inspect before changing. Guarded operations (`--yes`): `rm`, `trash delete/empty`, `share delete`, `upload-dir --prune` (unless `--dry-run`), link shares with write bits or public upload, widening `share update`, `user create`, `user set --key password`, `user/group delete`, `app enable/disable`, `webhook create/delete`, `notifications clear`, `call DELETE`, `app-password`, `mcp create --recreate`, any occ command outside the allow-list. `--yes` means the user already agreed after seeing the targets.
- Never paste app passwords, `mcp-basic.b64` contents or share tokens into replies or commits; `config show` prints only `set`/`None`. Pass secrets via env vars (`--password "$SHARE_PW"`, `NC_PASS=…`).
- Leave existing shares alone unless the user names them.
- State-changing occ (`config:system:set`, `app:enable`, `maintenance:mode --on`, `user:*` writes, `files:scan`, `files:cleanup`, …) only on explicit request. Never switch maintenance mode on yourself: every API call then returns 503.
- Raw links are completely public; confirm the content may be public first.
- Unset `NEXTCLOUD_INSECURE` after debugging. Put write tests in a scratch folder and clean up, including the trash.

## References

- `references/OCC.md` - occ transports, read-only allow-list and `--yes` guard, recipes, AIO notes, dangerous commands. Read before any occ task.
- `references/occ_commands.generated.txt` - command list captured from a Nextcloud 33 AIO install; the CLI checks full command names against it (then live `occ list`). Grep it for names.
- `references/API_OCS.md` - shares, provisioning, unified search, notifications, activity, webhooks, raw-link API, app passwords: parameters, fields, status codes.
- `references/API_WEBDAV.md` - PROPFIND properties, PUT headers, chunked upload, SEARCH syntax, trash/versions endpoints, curl equivalents.
- `references/MCP.md` - MCP server comparison, sidecar settings, credential file, per-runtime registration and removal, stdio read-first fallback.
- `references/TROUBLESHOOTING.md` - symptom -> cause -> fix for HTTP codes, brute force, config and guard errors, occ/ssh, maintenance, MCP.
- `references/SITE_NOTES.md` - the private site notes file: purpose, what to record, template.

## Maintaining this skill

1. After a major Nextcloud upgrade, regenerate the command list from the skill root: `scripts/ncloud occ -- list --raw > references/occ_commands.generated.txt`, then run `python3 -B tests/test_ncloud.py`.
2. When `files_sharing_raw` changes version, check its routes (`scripts/ncloud occ -- router:list files_sharing_raw`) and update filehost's references.
3. Keep instance facts out of this skill: they belong in the private site notes.
