# TROUBLESHOOTING.md - nextcloud-use

Symptom -> cause -> fix. Commands run from the skill root (`scripts/ncloud …`). Start with:

```bash
scripts/ncloud doctor --deep     # every check, one line each; exit 2 if any fails
scripts/ncloud config show       # effective settings (password shown only as set/None), occ_mode, mcp_url, notes_file
scripts/ncloud config notes      # the operator's private site notes: known quirks of the configured server live there
```

CLI errors print `HTTP <code>` plus the server message (the `<s:message>` of WebDAV errors is extracted). Exit codes: 0 ok; 1 guard refusal or other CLI error; 2 missing configuration, argument error, or a failed doctor/MCP check; 3 HTTP/OCS error (`call`: any status >= 400); 4 not found (`stat`, `path`); `occ` passes through occ's own exit code.

## Contents

1. HTTP status codes
2. OCS `statuscode`
3. Authentication and brute-force protection
4. WebDAV specifics
5. Configuration and CLI guard messages
6. occ, ssh and docker
7. Maintenance mode, AIO backups and upgrades
8. MCP sidecar

---

## 1. HTTP status codes

| Code | Likely cause | Fix |
|---|---|---|
| 401 | Wrong or revoked app password; a global `--user/--password` override is wrong or placed after the subcommand; public-share DAV (`/public.php/dav/files/<token>/`) without or with a wrong share password | **Do not retry** (section 3). Check `config show` once. Global flags go before the subcommand; a subcommand's `--password` is a share/new-user password, never the login |
| 403 | No permission: someone else's file, read-only share, sharing disabled for the group | Use another path; inspect `stat <path> --json` (`permissions`) |
| 404 | Wrong path (case, double or non-breaking spaces), unknown share id, app disabled (its routes disappear) | `ls` the parent; `app list --filter disabled` |
| 405 | MKCOL on an existing folder | Treat as "exists" (the CLI does) |
| 409 | Parent folder missing for MKCOL/PUT | `mkdir -p` the parent |
| 412 | OCS/app route without `OCS-APIRequest: true` ("CSRF check failed"); MOVE/COPY target exists with `Overwrite: F`; `If-Match` mismatch | Add the header (CLI and `call` do); `--overwrite` |
| 413 | Body too large. HTML body = reverse proxy limit; XML body = storage backend (EntityTooLarge). Observed on Nextcloud 33 AIO: single PUTs up to ~100 GiB pass Apache/PHP | Chunked upload (automatic at >= 64 MiB); lower `NEXTCLOUD_CHUNK_THRESHOLD_MB` / `NEXTCLOUD_CHUNK_SIZE_MB` below the proxy limit. A body/`Content-Length` mismatch is 400, not 413 |
| 423 | File locked (another client writing, or a stale lock) | Back off and retry 1-30 s; if it persists for minutes, an admin inspects the lock table or rescans that exact subtree with consent. Not `files:cleanup` (unrelated, and a write) |
| 429 with JSON body `[]` (OCS write) | Per-user rate limit, not brute force. Nextcloud 33 defaults: 20 share creations, 10 share e-mails, 50 user edits per 10 min | Wait 10 min; reuse shares; one share per folder in batch jobs |
| 429 (other) | Brute-force lockout: >10 failures in 12 h AND >10 in the last 30 min from one IP | Stop all retries; section 3 |
| 500 | App bug, SEARCH with >100 operators, unknown unified-search provider, `mail` provider without a configured mail account; `GET /apps/files_sharing_raw/api/v1/raw-public-url` in files_sharing_raw 0.7.3 (route points to a missing controller; the CLI does not use it) | `scripts/ncloud occ -- log:tail 20`; change endpoint or query; `usearch` skips `mail` by default |
| 503 + `X-Nextcloud-Maintenance-Mode: 1` + `Retry-After` | Maintenance mode or database upgrade (raw links answer 503 too) | Section 7: poll `scripts/ncloud status` every 60 s, report after 30 min |
| 502 / connection refused | Containers stopped (AIO backup/update stops them instead of using maintenance mode) or the server is down | Section 7; do not restart anything yourself |
| 507 | Quota exceeded | Free space; changing quota (`user set <uid> --key quota --value …` or occ) is a write: ask first |
| HTML page instead of JSON | Hostname not in `trusted_domains` ("Access through untrusted domain"), login redirect, or a proxy error page | Use the configured `NEXTCLOUD_URL`; an admin adds the domain with occ `config:system:set trusted_domains <n> --value=<host>` (with consent) |

## 2. OCS `statuscode`

Read `ocs.meta.statuscode`, not `message` (it is localized to the account language). v2 success = 200 (v1 = 100). `996` server error, `997` unauthorized, `998` not found, `999` unknown. The sharing API also uses 400 (invalid parameter, e.g. CREATE permission on a file), 403 (sharing not allowed) and 404 (path not found).

## 3. Authentication and brute-force protection

How Nextcloud core throttles (verified on Nextcloud 33):

- Each failed login from an IP adds a delay of 0.1 s x 2^n (n = failures in the last 12 h), capped at 25 s after about 8 failures.
- HTTP 429 when there are >10 failures in 12 h **and** >10 in the last 30 min (`auth.bruteforce.max-attempts`, default 10). Records expire after 48 h.
- A successful login by the same user from the same IP clears that IP's `login` counter, so `security:bruteforce:attempts <ip>` often shows 0 while other agents keep logging in fine. That does not mean failures are free: a loop that only fails still climbs to 429 and blocks every agent sharing the IP.
- Failed share-password attempts on public share DAV count as failures too.

Shared buckets: when agents reach Nextcloud through a reverse proxy listed in `trusted_proxies`, or from the same docker host, Nextcloud may record all of them under one address (often `127.0.0.1`). One bad password then throttles every agent, and a brute-force whitelist for LAN ranges does not apply to them. Find the recorded address in the log (`Login failed: '<user>' (Remote IP: '<ip>')`) and record it in the site notes. A `trusted_proxies` range that is wider than the proxy itself lets any host in that range spoof `X-Forwarded-For`; tightening it is the operator's decision, not the agent's.

| Symptom | Cause | Fix |
|---|---|---|
| 401 on every call | Wrong/revoked app password, or wrong account | Do not retry. `config show`, `config path`; get a new app password from the user (Settings > Security) or, with consent, `scripts/ncloud app-password agent-x --yes` |
| 401 only on share commands with `--password` | Old CLI versions reused the share password as the login | Current CLI: global `--url/--user/--password` have their own dests and must precede the subcommand |
| Requests get slower, then 429 | Brute-force throttling of the shared source IP | Stop. `scripts/ncloud occ -- security:bruteforce:attempts <ip>` (read-only); reset only with the user's consent: `scripts/ncloud occ --yes -- security:bruteforce:reset <ip>` |
| `getapppassword` returns 403 "Password confirmation is required" | OCS `/core/getapppassword` needs the login password, not an app password | Use `scripts/ncloud app-password <name> --yes` (occ) or the web UI |
| A minted token fails for some operation | `user:auth-tokens:add -n` without the login password creates a token with limited capabilities (e.g. server-side encryption keys) | Fine for WebDAV/OCS. For a full token run occ `user:auth-tokens:add <uid> --name <n> --password-from-env` with `NC_PASS` on the host (see `OCC.md`) |

App passwords: list with `scripts/ncloud occ -- user:auth-tokens:list alice --output=json`; revoke with `scripts/ncloud occ --yes -- user:auth-tokens:delete alice <id>` (only when asked).

## 4. WebDAV specifics

| Symptom | Cause | Fix |
|---|---|---|
| 404 for a name containing `#`, `?`, `%`, `+` or non-ASCII | Path not percent-encoded per segment | Let the CLI encode; manual curl: encode each segment (`API_WEBDAV.md`) |
| `share list --path X` shows `token: null` and no URL | OCS `GET shares?path=X` on an external-storage mount, or a node where you hold fewer permissions than the share | CLI refills via `GET shares/<id>`; manually use `share get <share_id>` |
| SEARCH returns 400 | Invalid XML, or `d:scope/d:href` not `/files/<user>/…` | Fix the query; use `scripts/ncloud search` |
| Huge PROPFIND response | `Depth: infinity` is enabled on Nextcloud 33 and returns the whole tree | Use `tree`/`download-dir` (they recurse with Depth 1) |
| Uploaded file has size 0 | `Transfer-Encoding: chunked` through a proxy that drops it | The CLI sends `Content-Length`; do the same manually |
| Old content "comes back" / files reappear | Overwrites create versions, deletes go to trash; both have retention | `versions list`, `trash list` |
| Team folders or external storage behave differently | They appear in the same `/remote.php/dav/files/<user>/` tree but with different permission strings; some lack versions | Check `stat <path> --json` |
| `/raw/<token>/` (trailing slash) is 404 | files_sharing_raw 0.7.3 routing | Use `/raw/<token>` or `/raw/<token>/index.html` |
| Custom share token rejected | `shareapi_allow_custom_tokens` is off (an admin setting, not a hard limit) | Use the generated token, or ask an admin |

## 5. Configuration and CLI guard messages

| Message | Cause | Fix |
|---|---|---|
| `NEXTCLOUD_URL, NEXTCLOUD_USER not set …` (exit 2) | No configuration; the skill has no instance defaults | `scripts/ncloud config init --url https://cloud.example.com --user alice`, or export the variables |
| `config init needs --url and --user` | One of them missing | Pass both |
| `<file> exists; use --force to overwrite` | Env file already present | Edit it, or `config init … --force` |
| `NEXTCLOUD_USE_ENV=… does not exist` | Pinned env file missing; the CLI never falls back to another account's file | Fix the path, unset it, or `config init` |
| `NEXTCLOUD_APP_PASSWORD is not set` | Password missing in env and env file (message lists all candidate files) | Fill it in the 0600 env file. doctor then shows `password=MISSING`, skips authenticated checks, exits 2 |
| `connection failed: …` | Wrong URL, DNS, TLS or network | Check `NEXTCLOUD_URL`; `NEXTCLOUD_INSECURE=1` only to debug a self-signed certificate |
| `warning: NEXTCLOUD_INSECURE=1 -> TLS certificates are NOT verified` | Debug setting left on | Unset it |
| `refusing destructive operation (…) without --yes` | Guarded subcommand | Show the targets to the user; add `--yes` only after consent |
| `--prune deletes remote files that are not in the local tree …` | `upload-dir --prune` without `--yes` | Run with `--dry-run` first (a missing remote folder counts as empty), then `--prune --yes` |
| `this link share would let ANYONE with the URL write/upload/delete …` | Link share with `rw`/`upload`/`full` or `--public-upload` | Confirm with the user, then `--yes`; suggest `--password` and `--expire` |
| `this change widens what anonymous visitors of a link share can do …` | `share update` adding write bits / upload, `--clear-password`, `--clear-expire` | Same: consent, then `--yes` |
| `refusing to send credentials to a foreign origin` | `call` with an absolute URL on another origin | Use `--no-auth` for foreign hosts; the app password only goes to `NEXTCLOUD_URL` |
| `refusing to write outside <dir>` | `download-dir` got a server path escaping the target | Do not bypass; report to the user |
| `unknown permission '…'` | Bad `--perm` | Number or `ro`/`rw`/`upload`/`full` |
| `--with <uid\|gid\|...> is required for this share type` | User/group/remote share without a recipient | Add `--with`; find ids with `share sharees <term>` |
| `give at least one of --name/--mime/--min-size/--max-size/--after` | Empty `search` | Add a filter |
| `unrecognized arguments: --user …`, or the wrong account/URL is used | Global `--url/--user/--password` placed after the subcommand: most subcommands reject them; `share create/update --password`, `user create --password` and `mcp --url` silently take them as their own option | Put them first: `scripts/ncloud --user alice ls /` |

## 6. occ, ssh and docker

| Symptom | Cause | Fix |
|---|---|---|
| `occ is not configured: …` / doctor `occ … not configured` | No local Nextcloud container, no `NEXTCLOUD_OCC_SSH_HOST`, no `NEXTCLOUD_OCC_COMMAND` | Set the one that fits; HTTP features keep working without occ |
| `NEXTCLOUD_OCC_SSH_HOST is not set` | `NEXTCLOUD_OCC_MODE=ssh` forced without a host | Set the host or use `auto` |
| `'<cmd>' is not on the read-only allow-list …` | Command can change state or expose secrets (including `config:list --private`, `maintenance:mode --on/--off`, `trashbin:size <size>`) | Run only when the user asked; then `occ --yes -- …` |
| `'<cmd>' is not a full occ command name` | Symfony abbreviation (`user:del`) or unknown name; rejected even with `--yes` | Use the full name from `occ_commands.generated.txt` or `scripts/ncloud occ -- list <namespace>`. Leading global options (`-n`, `-q`, `-v`, `--no-ansi`) are skipped when finding the name |
| `The "--print-only" option does not exist` | CLI flag placed after `--` | CLI flags (`--yes`, `--stdin`, `--print-only`) go before `--` |
| `<cmd> --help` refused | Treated as the command itself | `scripts/ncloud occ -- help <cmd>` (allow-listed) |
| Command "succeeds" but did nothing | No stdin: interactive prompts take the default (usually No) and exit 0 | Pass explicit `-f`/`-y`/`-n` flags, forward stdin with `--stdin` where needed, verify afterwards |
| `config:system:get` exit 1 | Key not set | Not an error; `--default-value=X` prints X |
| `user:delete <unknown>` exit 0 | occ prints "User does not exist" but succeeds | Check with `user:info` first |
| `warning: NC_PASS/OC_PASS are not forwarded over ssh` | Secrets are forwarded only in local docker mode (`docker exec -e NC_PASS`) | Run on the host, or use the `read -r` pattern in `OCC.md` |
| `ssh: Permission denied (publickey)` | The CLI runs as a user whose key is not authorized (ssh uses `BatchMode=yes`) | Authorize the key for that user, or run as the right user |
| `Host key verification failed` | First connection, no `known_hosts` entry | Connect once interactively, or add the host key |
| `docker: permission denied` / `Cannot connect to the Docker daemon` | User not in the docker group, or no docker in this container | Use ssh mode (`NEXTCLOUD_OCC_SSH_HOST`) |
| occ hangs | Data directory on a hard network mount whose server is down, or a long job | Wrap long jobs in `timeout`; check the site notes for storage layout |

## 7. Maintenance mode, AIO backups and upgrades

| Symptom | Cause | Fix |
|---|---|---|
| `status.php` shows `maintenance: true`, API 503 | Upgrade in progress or someone ran `maintenance:mode --on` | Wait; never switch it off yourself (an upgrade may be running) |
| 502 / connection refused for minutes (AIO) | AIO backups and updates stop the containers instead of using maintenance mode; the schedule lives in the AIO mastercontainer UI (`maintenance_window_start` is Nextcloud's background-job window, unrelated) | Wait and poll; record the backup window in the site notes |
| Feature vanished after an upgrade | Incompatible apps get disabled | `scripts/ncloud app list --filter disabled`; re-enabling is a write (consent, `--yes`) |
| Raw links and the raw API return 404 `text/html` | `files_sharing_raw` disabled (generic Nextcloud 404 page) | Its registry survives; after `app enable files_sharing_raw --yes` published sites work again |

## 8. MCP sidecar

| Symptom | Cause | Fix |
|---|---|---|
| `mcp status`: unreachable | Sidecar stopped | `scripts/ncloud mcp start` (~20 s cold start) |
| `mcp start`: `docker start … failed … (first time: ncloud mcp create)` | Container never created | `scripts/ncloud mcp create` (review with `--print-only`) |
| `mcp create`: `container … already exists` | Already created | `mcp start`; to change image, port, network or apps: `mcp create --recreate --yes` |
| `docker create failed` | Image pull failed, or `NEXTCLOUD_MCP_NETWORK` does not exist on that docker host | `docker network ls`; fix the variable; retry |
| `mcp start`: `reports auth_mode=…, expected 'multi_user_basic': stopped it again` | Container not in credential pass-through mode (e.g. created by hand with a username/password, which makes `/mcp` unauthenticated) | `scripts/ncloud mcp create --recreate --yes`; never bypass |
| `did not become ready in 60s` | Slow start, or the sidecar cannot reach `NEXTCLOUD_URL` (DNS/hairpin NAT inside docker) | `docker logs <container>`; make the URL resolvable from the container |
| `refusing to send the Basic secret over plain http to …` | Plain-http URL whose host is not `127.0.0.1`, `localhost` or the container name | Fix `NEXTCLOUD_MCP_URL` or `mcp status --url` (the global `--url` is the Nextcloud URL) |
| Default URL `http://nextcloud-mcp:8000/mcp` does not resolve | Not on the sidecar's docker network (e.g. a laptop using ssh for occ) | Tunnel (`ssh -L 18000:127.0.0.1:18000 nc-host`) and set `NEXTCLOUD_MCP_URL=http://127.0.0.1:18000/mcp`, or set `NEXTCLOUD_MCP_NETWORK` and recreate |
| Agent container gets connection refused on `127.0.0.1` | Inside a container, loopback is the container itself | Join the sidecar to the agent's network (`NEXTCLOUD_MCP_NETWORK`, recreate) and use `http://<container>:8000/mcp` |
| `/mcp` answers 421 | `Host` header not in `MCP_ALLOWED_HOSTS` (container name, `127.0.0.1`, `localhost`) | Connect by one of those names. `/health/ready` is not host-checked, so a healthy status does not prove `/mcp` is reachable |
| `mcp status` initialize OK but tool calls fail with 401 | `initialize` does not validate the credential | `scripts/ncloud whoami`; then `mcp credential --write` |
| Tool call: `BasicAuth credentials not found` | Runtime did not send `Authorization: Basic …` | Check the header and the secret file path in the registration (`mcp snippet`) |
| Tool call: `Authentication failed … 401` / runtime shows `authentication_required` | Wrong or revoked secret; every call is one more failed login on the shared bucket | Unregister immediately, do not retry; `whoami`, then `mcp credential --write`, re-register |
| stdio fallback (`uvx … nc-mcp`) fails to start | Needs Python >= 3.13; uv may download a managed interpreter | Allow the download; inside containers set `UV_PYTHON_INSTALL_DIR` to a persistent directory |

When done: unregister the server from the runtime, then `scripts/ncloud mcp stop`.
