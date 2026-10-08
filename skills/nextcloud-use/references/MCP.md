# MCP.md — Nextcloud MCP: when to load it, which server, on-demand sidecar

MCP is the third, optional access layer of this skill. Agents never keep it loaded: decide whether the task needs
it, use the HTTP CLI or occ when they can do the job, load MCP only when they cannot, and unload it afterwards.
Commands run from the skill root (`scripts/ncloud …`). Read the site notes first (`scripts/ncloud config notes`,
see `SITE_NOTES.md`); they may restrict what an agent may do on this Nextcloud. MCP failures are also covered in
`TROUBLESHOOTING.md`.

## Contents

1. Summary
2. When MCP is warranted (decision tree)
3. Server options compared
4. The on-demand sidecar (`scripts/ncloud mcp`)
5. Credential: `mcp-basic.b64`
6. Load -> use -> unload (any runtime)
7. Claude Code
8. mcporter
9. Read-first stdio fallback (`nextcloud-mcp-connector`)
10. Official route: Context Agent / AppAPI
11. Security model
12. Verified facts and open items

---

## 1. Summary

- Nextcloud core has no MCP endpoint. The official MCP capability is the MCP server built into the **Context
  Agent** ExApp, which needs AppAPI, a deploy daemon (HaRP), the Assistant app and an LLM provider (§10).
- This skill therefore uses a **sidecar container** that it creates, starts and stops itself:

| Role | Option | Why |
|---|---|---|
| **Primary** | `cbcoutinho/nextcloud-mcp-server` 0.198.3 as a stopped-by-default Docker sidecar managed by `scripts/ncloud mcp`, in `MCP_DEPLOYMENT_MODE=multi_user_basic` (**credential pass-through**: the container stores no credential; every request carries `Authorization: Basic base64(user:app-password)`), streamable HTTP | No change to Nextcloud itself, no AppAPI, no downtime; actively maintained; `--enable-app` allow-list; `/health/ready` probe; works with any runtime that can send a header on an HTTP MCP server |
| **Fallback** | `street1983nk/nextcloud-mcp-connector` v0.5.0 over **stdio** (`uvx … nc-mcp`) | Read-first (never deletes or overwrites; writes only create), 23 tools, no infrastructure |
| **Optional, later** | Official Context Agent ExApp, or the `mcp_connector` ExApp (OAuth 2.1) | Worth it only if you want Nextcloud Assistant anyway (§10) |
| **Not adopted** | `sintax-tech/mcp-for-nextcloud`, `hithereiamaliff/mcp-nextcloud`, `andrewyager/nextcloud-mcp-connector` | See §3 |

---

## 2. When MCP is warranted (decision tree)

```
start
├─ The user explicitly asks for MCP or names an MCP tool?          -> load (§6), unload when done
├─ Files, folders, shares, public links, raw hosting, users, apps,
│  config, logs?                                                    -> no MCP: WebDAV, OCS, raw-link API, occ
├─ Doable with <= 3 WebDAV/OCS/occ calls?                           -> no MCP
├─ Simple "find X" across apps?                                     -> no MCP: `scripts/ncloud usearch <term>` (unified search)
├─ Calendar / Contacts / Deck / Mail / Notes / Tables / Talk semantics
│  or multi-step work ("what is on next week", create a card from a
│  thread, read the inbox, gather context across apps), or exploring
│  unknown structure (boards, calendars, address books)?            -> MCP
│     ├─ must be non-destructive / user wants a read-first guarantee -> stdio fallback (§9)
│     └─ needs update/delete/full CRUD, sharing, Deck, Mail breadth -> sidecar (§4)
├─ Needs Assistant-grade agent behaviour (Context Agent)?           -> only if AppAPI + Assistant exist (§10); else sidecar
└─ Done: unregister from the runtime, then `scripts/ncloud mcp stop`
```

Rule of thumb: single-file reads/writes and batch moves of known paths -> WebDAV; apps, settings, tokens -> occ;
"find the events / contacts / cards related to X and act on them" -> MCP.

---

## 3. Server options compared

| # | Option | Runs as | AppAPI | Transport | Auth | Tools (observed) | Safety model | Status | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Context Agent** (`nextcloud/context_agent` 2.9.1, official) | ExApp; MCP at `/index.php/apps/app_api/proxy/context_agent/mcp/` (Docker Socket Proxy) or `/exapps/context_agent/mcp` (HaRP, UNVERIFIED) | **required** (>= 3.1) + deploy daemon + Assistant + LLM provider | streamable HTTP (stateless) | `Authorization` forwarded to `/ocs/v2.php/cloud/user` (docs: Bearer app password; Basic also works) | the agent's whole tool set (files, Talk, Mail, Calendar, Deck, Tables, Contacts, …) | safe and dangerous tools both exposed; no confirmation layer on the MCP side | released 2026-09-30, NC 31.0.8–35; versions < 2.9.0 break with clients on MCP SDK >= 1.28 (incl. Claude Code) | only if you already run Assistant |
| 2 | **MCP Connector** (`street1983nk/nextcloud-mcp-connector` 0.5.0) | (a) ExApp `mcp_connector`; (b) standalone OAuth (needs `user_oidc`); (c) standalone HTTP; (d) **stdio `nc-mcp`** | (a) required; others no | stdio / streamable HTTP | (a) OAuth 2.1 or Basic; (c) Basic pass-through or static Bearer; (d) env | **23** | read-first: no deletes, writes only create, `files_upload` refuses to overwrite; `NC_MCP_FILES_ROOT`, `NC_MCP_DISABLED_TOOLS`, `kein-ki` tag exclusion | 0.5.0 2026-10-05, NC 32–35; **not on PyPI** (install from git); `requires-python >= 3.13` | **fallback (stdio)**; ExApp later |
| 3 | `sintax-tech/mcp-for-nextcloud` 0.11.0 | native PHP app at `/apps/mcp/` | no | streamable HTTP | OAuth (CIMD) or Basic app password | Files, Notes, Calendar, Contacts, Tasks, Deck, Talk | writes need `confirm: true` | NC 33 only; not in the app store; very new | not adopted: unaudited PHP inside the Nextcloud process, manual install |
| 4 | **`cbcoutinho/nextcloud-mcp-server` 0.198.3** | standalone Python; `uvx` or `ghcr.io/cbcoutinho/nextcloud-mcp-server:0.198.3` (amd64/arm64), port 8000 | no | streamable HTTP `/mcp`, stdio | single-user mode: **no auth on the endpoint**; `multi_user_basic`: Basic per request; `login_flow`: OAuth | **142** (all apps); **102** with six apps enabled | no read-only mode; `--enable-app` allow-list, `EXCLUDED_TAGS`; MCP annotations per tool (`readOnlyHint`, `destructiveHint`) | released 2026-10-01, actively maintained | **primary** |
| 5 | `andrewyager/nextcloud-mcp-connector` | fork of #2 (v0.3.2) | as #2 | as #2 | as #2 | 22 | as #2 | nothing unique | use upstream #2 |
| 6 | `hithereiamaliff/mcp-nextcloud` 1.0.0 | Node/TS, `npx mcp-nextcloud` | no | stdio / HTTP | custom `X-API-Key` + `X-Nextcloud-*` headers | 30 (incl. deletes) | no confirmation | npm unchanged since 2025-09 | not adopted |

---

## 4. The on-demand sidecar (`scripts/ncloud mcp`)

### 4.1 What `mcp create` builds

`scripts/ncloud mcp create` runs `docker create` (locally or over ssh, §4.2) and leaves the container **stopped**.
Settings come from the env file / environment (`SKILL.md` has the full variable table).

| Item | Value | Purpose |
|---|---|---|
| image | `$NEXTCLOUD_MCP_IMAGE` (default `ghcr.io/cbcoutinho/nextcloud-mcp-server:0.198.3`) | pinned version; pulled on first create |
| `--name` | `$NEXTCLOUD_MCP_CONTAINER` (default `nextcloud-mcp`) | |
| `-p 127.0.0.1:$NEXTCLOUD_MCP_PORT:8000` | port default 18000 | loopback only, never `0.0.0.0` |
| `--network $NEXTCLOUD_MCP_NETWORK` | only when set | agent containers on that network reach `http://<container>:8000/mcp` |
| `--init --restart no --stop-timeout 15` | | clean `docker stop`; never starts on its own |
| `--cap-drop ALL --read-only --tmpfs /tmp --security-opt no-new-privileges:true` | | hardening (starts and serves normally with it) |
| healthcheck | `curl -fsS http://127.0.0.1:8000/health/ready`, interval 30 s, timeout 5 s, start period 20 s, 3 retries | |
| `NEXTCLOUD_HOST` | `$NEXTCLOUD_URL` | the sidecar must resolve and reach this URL from inside its container |
| `MCP_DEPLOYMENT_MODE` | `multi_user_basic` | credential pass-through; never single-user mode (§11) |
| `NEXTCLOUD_VERIFY_SSL` | `true` (`false` only with `NEXTCLOUD_INSECURE=1`) | |
| `MCP_DNS_REBINDING_PROTECTION` | `true` | unknown `Host` headers on `/mcp` -> 421 |
| `MCP_ALLOWED_HOSTS` | `<container>:*,127.0.0.1:*,localhost:*` | |
| `CORS_ALLOW_ORIGINS` | `http://127.0.0.1:<port>` | no browser clients |
| `METRICS_ENABLED` | `false` | no metrics listener on the network |
| `OTEL_SERVICE_NAME` | `<container>` | |
| arguments | `--transport streamable-http --port 8000 --enable-app <app>` for each app in `$NEXTCLOUD_MCP_APPS` | default `webdav,sharing,calendar,contacts` |

- The container gets **no Nextcloud credential**. `mcp create` needs `NEXTCLOUD_URL` and `NEXTCLOUD_USER`, not the
  app password.
- Enable only apps that are installed and needed, e.g. `NEXTCLOUD_MCP_APPS=webdav,sharing,calendar,contacts,deck,mail`
  (add `notes` once Notes is installed); changing it needs a recreate.
- `EXCLUDED_TAGS=<tag>` (files carrying that system tag become invisible to MCP; create the tag in Nextcloud first)
  is not set by `mcp create`. To use it, take the command from `mcp create --print-only` before the container
  exists, add `-e EXCLUDED_TAGS=no-ai`, and run it yourself.

### 4.2 Where docker runs and which URL is used

Both follow the occ transport (`scripts/ncloud config show` prints `occ_mode` and `mcp_url`):

| occ mode | docker commands run | default MCP URL |
|---|---|---|
| `local` (the Nextcloud container runs on this machine, `NEXTCLOUD_OCC_COMMAND` without an ssh host, or `NEXTCLOUD_OCC_MODE=local`) | here | `http://127.0.0.1:$NEXTCLOUD_MCP_PORT/mcp` |
| `ssh` (`NEXTCLOUD_OCC_SSH_HOST`) | `ssh <host> docker …` | `http://$NEXTCLOUD_MCP_CONTAINER:8000/mcp` (reachable from a container on `NEXTCLOUD_MCP_NETWORK`) |
| `off` | nowhere: `mcp create/start/stop` fail | as ssh |

- Override with `NEXTCLOUD_MCP_URL` or the subcommand option `scripts/ncloud mcp status --url <endpoint>` (the
  global `--url` before the subcommand is Nextcloud's URL, not the MCP endpoint).
- `mcp start` and `mcp status` poll the MCP URL from where the CLI runs, so it must be reachable there. From another
  machine: `ssh -L 18000:127.0.0.1:18000 nc-host`, then `NEXTCLOUD_MCP_URL=http://127.0.0.1:18000/mcp`.
- Hosted Nextcloud without shell access: run the sidecar on your own docker host with `NEXTCLOUD_OCC_MODE=local`
  (occ itself is then unavailable).

### 4.3 Lifecycle

```bash
scripts/ncloud mcp create --print-only        # print the docker create command (see the caveat below)
scripts/ncloud mcp create                     # create, stopped
scripts/ncloud mcp start                      # docker start, wait for /health/ready (<= 60 s; cold start ~20 s), check auth_mode
scripts/ncloud mcp status                     # /health/ready, then an MCP initialize with Basic auth
scripts/ncloud mcp stop
scripts/ncloud mcp create --recreate --yes    # replace it (new image, apps, network or port); needs --yes
```

- `create` fails if the container already exists unless `--recreate --yes`. Caveat: `--print-only` still runs
  `docker inspect` first, and combined with `--recreate --yes` it **removes the existing container before printing**
  — preview only while no container exists.
- `start` reads `checks.auth_mode` from `/health/ready`. Anything other than `multi_user_basic` (e.g. single-user
  mode from credentials in the container env) makes it **stop the container again** and exit with an error: recreate
  it with `mcp create --recreate --yes`. Not ready within 60 s -> error; check `docker logs <container>`.
- `status` prints the health JSON (exit 2 when unreachable), then sends `initialize` with the Basic secret. It
  refuses to send the secret over plain `http://` except to `127.0.0.1`, `localhost`, `::1` or the container name
  (`https://` is always allowed). `initialize` does **not** check the password (only `tools/call` reaches
  Nextcloud), so a passing `status` says nothing about the secret.
- Upgrade: set `NEXTCLOUD_MCP_IMAGE` to the new tag, then `mcp create --recreate --yes` (still stopped). Read the
  upstream changelog first; re-check the tool list after upgrading.

---

## 5. Credential: `mcp-basic.b64`

The sidecar needs `Authorization: Basic base64("<user>:<app password>")`. The CLI writes that value to a 0600 file
so runtimes reference the file instead of putting the secret in a config file:

```bash
scripts/ncloud mcp credential            # show the secret file path and whether it exists
scripts/ncloud mcp credential --write    # verify the app password with one OCS call (/ocs/v2.php/cloud/user), then write the file
```

- File: `mcp-basic.b64` in the env file's directory (`$NEXTCLOUD_USE_ENV`'s directory when set, else
  `$XDG_CONFIG_HOME/nextcloud-use/` or `~/.config/nextcloud-use/`); mode 0600, written atomically, directory 0700.
  `scripts/ncloud config path` shows the env file next to it.
- `--write` refuses (without writing) when the app password fails; it never retries.
- Use a **dedicated** app password for MCP so it can be revoked on its own: Settings > Security > Devices & sessions,
  or with occ:

```bash
scripts/ncloud app-password nextcloud-mcp --yes     # needs --yes; the token is printed once on stdout, never paste it into chat
scripts/ncloud occ -- user:auth-tokens:list alice --output=json
scripts/ncloud occ --yes -- user:auth-tokens:delete alice <id>   # revoke (only when the user asks)
```

- `app-password` runs `occ user:auth-tokens:add <uid> --name <name> -n`. Without the login password occ prints a
  "No password provided … limited capabilities" notice, then `app password:`, then the 72-character token (the CLI
  keeps the last line). Such tokens work for OCS and WebDAV.
- To keep the MCP token apart, put it in its own 0600 env file and write the secret from it (the secret lands next
  to that env file; make sure `NEXTCLOUD_APP_PASSWORD` is not exported in the shell, since the process environment
  beats the env file):

```bash
NEXTCLOUD_USE_ENV=~/.config/nextcloud-use/mcp.env scripts/ncloud config init --url https://cloud.example.com --user alice --app-password '<token>'
NEXTCLOUD_USE_ENV=~/.config/nextcloud-use/mcp.env scripts/ncloud mcp credential --write
```

  `--app-password` on the command line lands in shell history and `ps`; to avoid that, run `config init` without
  it and fill the value in with an editor.
- After rotating the password, re-run `mcp credential --write` on every machine that holds the secret; runtimes that
  read the file at call time pick it up (reload those that cache it). The container needs no rebuild.

---

## 6. Load -> use -> unload (any runtime)

`scripts/ncloud mcp snippet --runtime generic` prints the URL, the header and secret-file guidance for any runtime
that can register a streamable-HTTP MCP server and read a header value from a file or an environment variable at
call time. `--runtime claude` and `--runtime mcporter` print ready-made commands (§7, §8); `--id` sets the server
name (default `nextcloud`).

```text
0. scripts/ncloud config notes        read the site notes (they may restrict MCP use)
   scripts/ncloud whoami              must succeed. 401: stop, do not retry; fix the app password, then `mcp credential --write`
1. scripts/ncloud mcp credential      the secret file must exist (else `scripts/ncloud mcp credential --write`)
   scripts/ncloud mcp status          unreachable -> scripts/ncloud mcp start   (first time: scripts/ncloud mcp create)
2. scripts/ncloud mcp snippet --runtime generic|claude|mcporter
3. Register the server for this task only: streamable HTTP, header
   "Authorization: Basic <contents of mcp-basic.b64>", read from the file / an env var at call time.
   Do not hand it to subagents unless they need it.
4. List the tools first (tools/list) and check names; never guess tool names.
   Unless the user asked for changes, use only tools with annotations.readOnlyHint=true.
   Treat nc_share_* (can create public links) and anything with destructiveHint=true as writes: ask first.
5. Authentication error, 401 or "Authentication failed" from a tool: unregister immediately.
   Do not retry, do not reload: every call is another failed login (§11). Fix the secret first.
6. Unregister the server, then scripts/ncloud mcp stop (unless another task still uses it).
```

Tool names start with `nc_` (`nc_webdav_list_directory`, `nc_calendar_*`, `nc_contacts_*`, `nc_deck_*`,
`nc_mail_*`, `nc_share_*`, …) — confirm them with `tools/list`. Bulk file I/O stays on WebDAV even while MCP is
loaded.

---

## 7. Claude Code

Recommended: **session-only**. The config file holds only a `${NC_MCP_BASIC}` placeholder; the secret lives in the
environment of that one process and never reaches Claude's settings (`scripts/ncloud mcp snippet --runtime claude`
prints this with your URL and secret path):

```bash
cat > /tmp/nextcloud-mcp.json <<'EOF'
{"mcpServers":{"nextcloud":{"type":"http","url":"http://127.0.0.1:18000/mcp","headers":{"Authorization":"Basic ${NC_MCP_BASIC}"}}}}
EOF
NC_MCP_BASIC=$(cat ~/.config/nextcloud-use/mcp-basic.b64) claude --mcp-config /tmp/nextcloud-mcp.json --strict-mcp-config
```

Not recommended: a persistent registration copies the secret into Claude's settings (`~/.claude.json`). If it is
used anyway, remove it as soon as the task ends:

```bash
claude mcp add --transport http --scope user nextcloud http://127.0.0.1:18000/mcp --header "Authorization: Basic $(cat ~/.config/nextcloud-use/mcp-basic.b64)"
claude mcp remove nextcloud --scope user
```

- Run `scripts/ncloud whoami` and `scripts/ncloud mcp start` before the session, `scripts/ncloud mcp stop` after it.
- `${VAR}` and `${VAR:-default}` expand in `command`, `args`, `env`, `url` and `headers` (header expansion verified on
  Claude Code 2.1). An unset variable is sent as the literal `${VAR}` and flagged in `claude mcp list` / `/mcp`.
- Use your own variable name (`NC_MCP_BASIC`): Claude Code expands some credential-like names (e.g.
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `AWS_BEARER_TOKEN_BEDROCK`, `HTTPS_PROXY`, `NPM_TOKEN`) to an empty
  string in remote-server `url`/`headers`.
- `--strict-mcp-config` ignores every other MCP configuration, including servers provided by plugins.
- The snippet also prints a session-only variant of the stdio fallback (§9).

---

## 8. mcporter

For scripted calls without an agent runtime (`scripts/ncloud mcp snippet --runtime mcporter`):

```bash
export NC_MCP_BASIC=$(cat ~/.config/nextcloud-use/mcp-basic.b64)
mcporter list --http-url http://127.0.0.1:18000/mcp --allow-http --header "Authorization=Basic $NC_MCP_BASIC" --schema
mcporter call --http-url http://127.0.0.1:18000/mcp --allow-http --header "Authorization=Basic $NC_MCP_BASIC" \
  --tool nc_webdav_list_directory --args '{"path":""}' --output json
# persistent alternative (placeholder resolved at call time); remove when done
mcporter config add nextcloud --url http://127.0.0.1:18000/mcp --header 'Authorization=Basic ${NC_MCP_BASIC}' --scope home
mcporter call nextcloud.nc_webdav_list_directory path=""
mcporter config remove nextcloud
```

- Ad-hoc `--http-url` calls to plain `http://` need `--allow-http`; configured `http://` entries do not (observed).
- `config add --scope home` writes `~/.mcporter/mcporter.json` (`$XDG_CONFIG_HOME/mcporter/` when that is set);
  without `--scope` it writes the project's `./config/mcporter.json`.

---

## 9. Read-first stdio fallback (`nextcloud-mcp-connector`)

No sidecar: the runtime spawns the server itself and passes the app password through its environment.

```text
command: uvx                         (use an absolute path inside containers)
args:    --from git+https://github.com/street1983nk/nextcloud-mcp-connector@v0.5.0 nc-mcp
env:     NC_MCP_URL=https://cloud.example.com
         NC_MCP_USER=alice
         NC_MCP_APP_PASSWORD=<from a 0600 file or an env var at spawn time; never inline in a config file>
         UV_PYTHON_INSTALL_DIR=<persistent dir>   # containers: keep the managed CPython across rebuilds
         NC_MCP_FILES_ROOT=/Documents/AI          # optional: confine the file tools to one folder
         NC_MCP_DISABLED_TOOLS=mail,calendar      # optional
```

- Needs **Python >= 3.13**. When the system Python is older, uv downloads a managed interpreter (into its default
  data directory, which in a container is often not on a persistent volume — set `UV_PYTHON_INSTALL_DIR`). The first
  `uvx` run clones and builds the package (1–2 minutes); later runs use the uv cache.
- Install from git as above: the package is **not on PyPI** (the README's `uv tool install nextcloud-mcp-connector`
  fails with 404).
- Claude Code, session-only (the app password stays in this process's environment):

```bash
cat > /tmp/nextcloud-mcp-ro.json <<'EOF'
{"mcpServers":{"nextcloud-ro":{"type":"stdio","command":"uvx","args":["--from","git+https://github.com/street1983nk/nextcloud-mcp-connector@v0.5.0","nc-mcp"],"env":{"NC_MCP_URL":"https://cloud.example.com","NC_MCP_USER":"alice","NC_MCP_APP_PASSWORD":"${NEXTCLOUD_APP_PASSWORD}"}}}}
EOF
NEXTCLOUD_APP_PASSWORD=$(sed -n 's/^NEXTCLOUD_APP_PASSWORD=//p' "$(scripts/ncloud config path)") \
  claude --mcp-config /tmp/nextcloud-mcp-ro.json --strict-mcp-config
```

  Do not use `claude mcp add --transport stdio … --env NC_MCP_APP_PASSWORD=…`: that stores the raw app password in
  `~/.claude.json`.
- Tools (23): files_search/list/read/download/read_as_markdown/upload, calendar_list_events/create_event, notes_*,
  deck_browse/create_card, tables_browse/create_row, talk_browse/send, mail_browse, contacts_search, unified_search,
  prepare_context, search, fetch.
- `cbcoutinho/nextcloud-mcp-server` also has a stdio mode
  (`uvx --from nextcloud-mcp-server==0.198.3 nextcloud-mcp-server run --transport stdio`; Python >= 3.11, SQLite
  >= 3.35), but it is not read-first and the install is heavy (about 150 packages).

---

## 10. Official route: Context Agent / AppAPI

- Nextcloud AIO: the AIO interface's optional containers include **HaRP** (the older Docker Socket Proxy is
  deprecated). Enabling it starts `nextcloud-aio-harp`; the Nextcloud container gets `HARP_ENABLED=yes` and its
  entrypoint enables `app_api` and registers the deploy daemon automatically.
- Cost: AIO "Stop containers" -> "Start containers" (Nextcloud downtime); ExApp containers join the `nextcloud-aio`
  network; ExApps are served under `https://cloud.example.com/exapps/<appid>/…`, so a reverse proxy in front of
  Nextcloud must forward `/exapps/` (verify).
- Non-AIO installs: enable AppAPI and register a deploy daemon yourself (HaRP recommended).
- Then: the app store's `mcp_connector` ExApp (OAuth 2.1, audit log) or `context_agent` >= 2.9.0 (also needs
  Assistant and an LLM provider).
- A leftover `app_api` app config `default_daemon_config` from an earlier setup is harmless: when AppAPI is enabled
  in HaRP mode its migration (`DataInitializationStep`) registers the `harp_aio` daemon and overwrites that value
  (source, AppAPI 33.0.0). Confirm afterwards with `occ app_api:daemon:list`.

---

## 11. Security model

- **Credentials.** An app password is the whole account (it bypasses 2FA). Give MCP a dedicated one and revoke it
  when no longer needed. Secrets live only in 0600 files: the env file and `mcp-basic.b64` (plus wherever the stdio
  fallback reads its app password). Never put them in a repo, a container env, a chat, or a persistent runtime
  config; the session-only forms (§7, §9) keep them out of Claude's settings.
- **Pass-through, never single-user mode.** In `multi_user_basic` the container stores nothing and every request
  must carry Basic auth. Upstream switches to single-user mode as soon as `NEXTCLOUD_USERNAME`/`NEXTCLOUD_PASSWORD`
  are in the container env; `/mcp` is then **completely unauthenticated** and acts as that user. `mcp create` never
  sets them, and `mcp start` stops the container when `auth_mode` is not `multi_user_basic`.
- **Host check.** Upstream accepts any `Host` header by default (observed). With
  `MCP_DNS_REBINDING_PROTECTION=true` and `MCP_ALLOWED_HOSTS`, a foreign `Host` on `/mcp` gets **421**
  (`/health/ready` is not host-checked). Upstream refuses to start when the protection is on but no allowed hosts are
  set.
- **CORS.** Upstream defaults to `*` with credentials; the sidecar allows only `http://127.0.0.1:<port>`. Never put
  the sidecar behind a browser-reachable proxy.
- **Metrics off.** `METRICS_ENABLED=false`: no metrics listener that other containers on the network could reach.
- **Loopback port.** The host port binds `127.0.0.1` only. `NEXTCLOUD_MCP_NETWORK` is optional: every container on
  that network can reach port 8000, so use a dedicated network that holds only the sidecar and the agent containers
  that need it.
- **Unauthenticated surface.** `tools/list` works without auth and returns full tool definitions (names,
  descriptions, schemas, annotations; no user data). `tools/call` without valid Basic auth fails with a tool error
  (`BasicAuth credentials not found`).
- **A bad secret means one failed login per tool call.** The sidecar replays the Basic secret to Nextcloud on every
  `tools/call`, so a stale or wrong `mcp-basic.b64` produces a 401 per call. Nextcloud's brute-force protection
  delays each failed login per source IP by 0.1 s x 2^n (12 h window, cap 25 s) and answers 429 after more than
  10 failures in 12 h and more than 10 in the last 30 min. Agents and the sidecar behind the same reverse proxy or
  docker host may share one source IP and therefore one bucket: one bad secret slows down or locks out every agent's
  WebDAV/OCS. So: `scripts/ncloud whoami` with the same app password before loading; on any authentication error
  unregister at once and **never retry a 401**. Unlocking is in `TROUBLESHOOTING.md` (only with the user's consent).
- **CLI guards.** `mcp start` stops a container in the wrong auth mode; `mcp status` sends the secret over plain
  http only to loopback or the container name; `mcp credential --write` verifies before writing; `mcp create
  --recreate` and `app-password` need `--yes`.
- **Bearer vs Basic.** The cbcoutinho pass-through accepts **Basic** only (observed); Nextcloud core itself also
  accepts `Authorization: Bearer <app password>` (the Context Agent docs use that).
- **Blast radius.** The primary server has no read-only mode. Narrow it with `NEXTCLOUD_MCP_APPS`, `EXCLUDED_TAGS`,
  a dedicated app password and client-side discipline (with six apps enabled, 42 of 102 tools carry
  `readOnlyHint: true` and 13 carry `destructiveHint: true`). For a hard guarantee use the stdio fallback (§9).
  With the `admin_audit` app enabled, file operations through the app password are audited.
- **Shares.** `nc_share_*` tools can create public links: treat them as writes and ask first. Raw links stay with the
  OCS / `files_sharing_raw` API (filehost skill).

---

## 12. Verified facts and open items

Verified on Nextcloud 33 with image 0.198.3 and the hardening that `mcp create` applies:

- Cold start about 20 s (about 22 s hardened); `/health/ready` returns
  `{"status":"ready","checks":{…,"auth_mode":"multi_user_basic",…}}`; `initialize` reports `server=Nextcloud MCP`.
- Streamable HTTP session flow: `initialize` -> `Mcp-Session-Id` -> `notifications/initialized` -> `tools/list`.
  With `webdav,sharing,calendar,contacts,deck,mail` enabled and Basic auth: **102 tools** (an unauthenticated
  `tools/list` returned 104 definitions). A read-only `tools/call nc_webdav_list_directory` succeeded from the host
  (`127.0.0.1:<port>`) and from agent containers on a shared docker network (`<container>:8000`).
- **Unauthenticated `tools/call` is rejected** (`BasicAuth credentials not found`), also when Authorization is dropped
  inside an existing session; a wrong password returns 401 text and counts as a failed login in Nextcloud.
- A foreign `Host` header on `/mcp` -> 421 (before hardening upstream answered 200); `/health/ready` is not
  host-checked.
- `--cap-drop ALL`, `--read-only` + `--tmpfs /tmp` do not break startup or tool calls; `docker stop` exits cleanly
  with `--init`.
- Single-user mode serves `/mcp` without authentication (do not use it).
- mcporter: configured `http://` entries work without `--allow-http`; ad-hoc calls work with it.
- `occ user:auth-tokens:add <uid> --name <name> -n` output format (notice line, `app password:`, 72-character token);
  such tokens work for OCS and WebDAV.
- The stdio fallback lists 23 tools; Nextcloud core accepts a Bearer app password; Claude Code expands `${VAR}` in
  `--mcp-config` headers.

Open (UNVERIFIED):

- Context Agent's `/exapps/…/mcp` path under HaRP, and whether a given reverse proxy forwards `/exapps/`.
- The managed-CPython download for the stdio fallback inside containers (inferred from `requires-python` and
  `uv python list`, not run).
- Tool count with the default four apps (fewer than 102; check with `tools/list`).
