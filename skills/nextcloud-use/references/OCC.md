# OCC.md - occ reference

Server-side administration with `occ`: transports, the CLI guard, a command catalogue by area, safety rules,
and Nextcloud AIO specifics. Behaviour was verified on Nextcloud 33 (AIO); items marked **[src]** come from the
Nextcloud 33 source, **UNVERIFIED** means not confirmed read-only. The full command index is
`occ_commands.generated.txt` (a command list captured from a Nextcloud 33 AIO install with `occ list --raw`, 312
commands). HTTP errors and ssh problems: `TROUBLESHOOTING.md`. Instance-specific rules (folders never to scan,
shares never to touch): the private site notes, `scripts/ncloud config notes` (see `SITE_NOTES.md`) - read them
before any occ task.

Placeholders: user `alice`/`bob`, group `team`, ssh host `nc-host`, `<fileid>`, `<share_id>`, `<mount_id>`
(external storage mount id), `<storage_id>` (numeric storage id), `<folder_id>` (team folder id).

## Contents

1. Running occ (CLI, transports, raw forms, flags, exit codes)
2. Read-only inspection
3. Configuration (config.php and app config)
4. Users and groups
5. Apps
6. Files and storage (incl. `files:scan` safety)
7. Full-text search
8. Share repair
9. Maintenance, background jobs, upgrades
10. Nextcloud AIO notes
11. Dangerous commands
12. Decision rules: occ vs API vs MCP

---

## 1. Running occ

### 1.1 `scripts/ncloud occ` (preferred)

```bash
scripts/ncloud occ [--yes] [--stdin] [--print-only] -- <occ-command> [args...]
scripts/ncloud occ -- status --output=json                  # read-only allow-list: runs as is
scripts/ncloud occ --print-only -- app:list --disabled      # print the argv, do not run
scripts/ncloud occ -- help files:scan                       # help for one command (help is on the allow-list)
scripts/ncloud occ --yes -- config:system:delete some.key   # anything else needs --yes (after the user asked)
```

Convention in this file: an example with `--yes` means "the user explicitly asked for this operation". `--yes` is
never a flag to add on your own.

**Flags go before `--`.** Everything after `--` is passed to occ verbatim (`occ -- status --print-only` is rejected
by occ itself: `The "--print-only" option does not exist`).

**Transport** (`NEXTCLOUD_OCC_MODE=auto|local|ssh|off`, default `auto`):

| Condition (auto mode, in order) | Mode | argv |
|---|---|---|
| `NEXTCLOUD_OCC_COMMAND` set | local, or ssh if `NEXTCLOUD_OCC_SSH_HOST` is set | `<NEXTCLOUD_OCC_COMMAND> <args>` |
| `docker` present and container `$NEXTCLOUD_OCC_CONTAINER` (default `nextcloud-aio-nextcloud`) running | local | `docker exec -i -u www-data -- <container> php occ <args>` |
| `NEXTCLOUD_OCC_SSH_HOST` set | ssh | `ssh -o BatchMode=yes -o ConnectTimeout=15 -- <host> '<argv>'` |
| none of the above | off | occ unavailable; `doctor` reports it; HTTP commands still work |

`NEXTCLOUD_OCC_COMMAND` is for non-docker installs, e.g. `sudo -u www-data php /var/www/nextcloud/occ`. In ssh mode
every argument is `shlex.quote`d and joined into one string for the remote shell, so spaces, non-ASCII, `#`, `$`
and quotes are safe - **do not escape them yourself**. `--print-only` shows the exact command:

```
$ scripts/ncloud occ --print-only -- info:file "/alice/files/Travel 2025/Readme.md" --children
docker exec -i -u www-data -- nextcloud-aio-nextcloud php occ info:file '/alice/files/Travel 2025/Readme.md' --children
$ NEXTCLOUD_OCC_MODE=ssh scripts/ncloud occ --print-only -- config:system:get trusted_domains
ssh -o BatchMode=yes -o ConnectTimeout=15 -- nc-host 'docker exec -i -u www-data -- nextcloud-aio-nextcloud php occ config:system:get trusted_domains'
```

**Stdin.** `--stdin` forwards local stdin to occ (`files:put -`, `config:import`, `files_external:import -`).
occ normally runs without a TTY (`docker exec` without `-t`, agent shells), so Symfony treats it as
non-interactive: **every interactive question takes its default answer** (usually No) and occ exits 0 having done
nothing. `files:delete`, overwriting `files:copy/move`,
`sharing:delete-orphan-shares`, `groupfolders:delete` and `files_external:delete` "succeed" without acting. In
automation pass `-f` / `-y` / `-n` explicitly and verify the result afterwards. Feeding passwords into prompts via
`--stdin` is UNVERIFIED; do not rely on it.

**The guard (deny by default).** Only the read-only commands in `OCC_READ_ONLY` (scripts/ncloud) run without
`--yes`; the check happens before `--print-only`:

| Area | Allow-listed commands |
|---|---|
| Server | `status`, `check`, `setupchecks`, `list`, `help`, `update:check`, `integrity:check-app`, `integrity:check-core` |
| Apps | `app:list`, `app:getpath` |
| Users, groups | `user:list`, `user:info`, `user:report`, `user:lastseen`, `user:auth-tokens:list`, `user:keys:verify`, `group:list`, `group:info`, `twofactorauth:state`, `admin-delegation:show` |
| Config | `config:list` (**not** with `--private`), `config:system:get`, `config:app:get` |
| Shares | `share:list` |
| Files, storage | `files:get`, `files:mount:list`, `files:reminders`, `files:recommendations:recommend`, `info:file`, `info:file:space`, `info:storage`, `info:storages`, `files_external:list`, `files_external:backends`, `files_external:verify`, `files_external:dependencies`, `groupfolders:list`, `trashbin:size` (**query form only**: a positional size argument sets the limit), `preview:queue-stats` |
| Logs, routing | `log:tail`, `log:watch`, `router:list`, `router:match` |
| Security | `security:bruteforce:attempts`, `security:certificates` |
| Jobs, tasks | `background-job:list`, `webhook_listeners:list`, `taskprocessing:task:list`, `taskprocessing:task:get`, `taskprocessing:task:stats` |
| Search | `fulltextsearch:check`, `fulltextsearch:test`, `fulltextsearch:search` |
| DAV | `dav:list-addressbooks`, `dav:list-calendar-shares`, `dav:list-calendars`, `dav:list-subscriptions` |
| Maintenance | `maintenance:mode` (**query form only**: `--on`/`--off` switch it) |

- **Everything else needs `--yes`**, including forms that are read-only but not listed (`log:file`, `log:manage`,
  reading `user:setting` / `user:profile`, `theming:config` listing, `tag:list`, `files_external:config/option/export`,
  `migrations:preview`, any `--dry-run`). Policy: add `--yes` to a write only after the user explicitly asked for
  it, after listing the targets; for unlisted read-only queries explain what you will run first; if unsure whether
  a command writes, treat it as a write.
- **Full command names only.** The CLI checks the name against `occ_commands.generated.txt`, then against the live
  `occ list` (for commands added later). Symfony abbreviations (`user:del` for `user:delete`) and unknown names are
  rejected (`not a full occ command name`), even with `--yes`. Leading global options (`-n`, `-q`, `-v`,
  `--no-ansi`, ...) are skipped when finding the name, so `occ -- -n config:system:set ...` is judged as
  `config:system:set`.
- `<command> --help` is judged as `<command>` itself (needs `--yes` if not listed). Use
  `scripts/ncloud occ -- help <command>` instead.
- **Exit code passes through**; stdout/stderr stream directly. occ needs no app password (it does not use HTTP).
- **Environment forwarding.** In local docker mode, if `NC_PASS` / `OC_PASS` are set the CLI adds
  `docker exec -e NC_PASS` (docker copies the value from its own environment; it never appears on the command
  line). In ssh mode they are **not** forwarded (warning on stderr, `-e` dropped): run password commands on the host
  or use the raw `read` form in 1.2. With `NEXTCLOUD_OCC_COMMAND` the child inherits the environment, but `sudo`
  drops it unless configured (`sudo --preserve-env=NC_PASS ...`).
- Run one occ command per `scripts/ncloud occ --` invocation.

### 1.2 Raw forms

```bash
# on the docker host
docker exec -u www-data nextcloud-aio-nextcloud php occ status --output=json
# from another machine (key-based ssh to the docker host)
ssh -o BatchMode=yes nc-host 'docker exec -u www-data nextcloud-aio-nextcloud php occ status --output=json'
# non-docker install
sudo -u www-data php /var/www/nextcloud/occ status --output=json
# add -i only when piping stdin
cat index.html | ssh -o BatchMode=yes nc-host 'docker exec -i -u www-data nextcloud-aio-nextcloud php occ files:put - /alice/files/Projects/site/index.html'
# password via environment, never on a command line
printf '%s\n' "$PW" | ssh -o BatchMode=yes nc-host 'IFS= read -r NC_PASS; export NC_PASS; docker exec -e NC_PASS -u www-data nextcloud-aio-nextcloud php occ user:resetpassword --password-from-env alice'
```

- Always run as `www-data` (uid 33 in the official images). Started as root, Nextcloud 33's occ tries to switch to
  the owner of `config.php` [src]; a uid mismatch otherwise makes `console.php` exit 1.
- **No `-it`**: without a TTY docker fails with `cannot attach stdin to a TTY-enabled container because stdin is not
  a terminal` (exit 1); `-t` alone turns `\n` into `\r\n` and breaks `jq`.
- zsh does not word-split variables: `OCC="docker exec ..."; $OCC status` gives `command not found`. Use a shell
  function or `${=OCC}`. To build an ssh string by hand:
  `cmd=$(printf '%q ' docker exec -u www-data nextcloud-aio-nextcloud php occ "$@"); ssh nc-host "$cmd"`.
- File arguments (`files:put <path>`, `files:get <path> <out>`, `config:import <file>`,
  `security:certificates:import`) are paths **inside the container**; send content through stdin instead.

### 1.3 Global options and output formats

`--output=plain|json|json_pretty` (per command), `-n/--no-interaction` (all questions take the default),
`--no-ansi`, `--no-warnings` (suppresses PCNTL warnings), `-q`, `-v|-vv|-vvv`; `status -e/--exit-code`. Scripts:
always add `-n --no-ansi --no-warnings`.

`--output=json` is not universal (observed on Nextcloud 33):

- Supported: `status`, `setupchecks`, `check`, `config:list`, `config:*:get`, `app:list`,
  `user:list/info/setting/profile/auth-tokens:list`, `group:*`, `share:list`, `info:storages/storage`,
  `files:mount:list`, `files:scan`, `files_external:list`, `groupfolders:list`, `background-job:list`, `router:*`,
  `security:bruteforce:attempts`, `admin-delegation:show`, `webhook_listeners:list`, `taskprocessing:task:*`,
  `fulltextsearch:*`.
- **Rejected** (`The "--output" option does not exist.`, exit 1): `info:file`, `user:lastseen`, `theming:config`.
  Rule: if `help <cmd>` does not list `--output`, do not pass it (e.g. `info:file:space`, `user:report`,
  `files:get/put/copy/move/delete`, `preview:*`, `log:manage`).
- **Accepted but ignored**: `log:tail`, `log:watch` (use `--raw` for JSON lines), `twofactorauth:state`.
  `fulltextsearch:check/test` also have `-j/--json`.

### 1.4 Exit codes

| Situation | Exit |
|---|---|
| success; unknown command | 0; 1 |
| `config:system:get <key>` / `config:app:get` / `user:setting <uid> <app> <key>` not set | **1 = not set, not an error**; with `--default-value=X` prints X and exits 0 |
| `user:info <missing>` (user not found), `files:get` on a missing path | 1 |
| `status -e` | 0 normal, 1 maintenance mode, 2 upgrade needed (prints nothing) |
| `setupchecks` with any non-`success` item | 1 (not a command failure; common on real servers) |
| **`user:delete <missing>`** | prints `User does not exist` but **exits 0** [src]; run `user:info` first |
| interactive question under `-n` / without TTY | 0 (default answer, usually nothing done) |

---

## 2. Read-only inspection

Commands without `--yes` below are on the allow-list and can run any time. Commands shown with `--yes` are
read-only but **not** on the allow-list: explain to the user first (1.1).

### 2.1 Status and health

```bash
scripts/ncloud occ -- status --output=json
# {"installed":true,"version":"33.0.x.y","versionstring":"33.0.x","edition":"","maintenance":false,"needsDbUpgrade":false,"productname":"Nextcloud","extendedSupport":false}
scripts/ncloud occ -- status -e                    # exit 0/1/2 (see 1.4)
scripts/ncloud occ -- check                        # dependency check; no output and exit 0 when fine
scripts/ncloud occ -- setupchecks                  # same as Administration settings > Overview
scripts/ncloud occ -- setupchecks --output=json
# filter: jq -c '[.[] | to_entries[] | select(.value.severity != "success") | {name: .value.name, severity: .value.severity}]'
scripts/ncloud occ -- update:check                 # informational; on AIO the mastercontainer decides when to update
scripts/ncloud occ -- maintenance:mode             # "Maintenance mode is currently disabled"
```

`setupchecks --output=json` shape: `{<category>:{<CheckClass>:{"name","severity":"success|info|warning|error",
"description","descriptionParameters","linkToDoc"}}}`; categories include `config database dav mail network php
security system` plus app-specific ones.

serverinfo has no read-only occ command: read it over OCS (`scripts/ncloud call GET
/ocs/v2.php/apps/serverinfo/api/v1/info`); `serverinfo:update-storage-statistics` is a write (recomputes stats).

### 2.2 Apps, users, groups

```bash
scripts/ncloud occ -- app:list --output=json         # {"enabled":{id:ver},"disabled":{id:"ver (installed ver)"}}
scripts/ncloud occ -- app:list --disabled
scripts/ncloud occ -- app:list --shipped=false --enabled   # third-party (app store) apps
scripts/ncloud occ -- app:getpath files_sharing_raw  # e.g. /var/www/html/custom_apps/files_sharing_raw
scripts/ncloud occ -- user:list -i --output=json     # {uid:{user_id,display_name,email,cloud_id,enabled,groups,quota,first_seen,last_seen,user_directory,backend}}
scripts/ncloud occ -- user:list --disabled -l 100 -o 0
scripts/ncloud occ -- user:info alice --output=json  # adds "storage":{free,used,total,relative,quota} (quota -3 = unlimited)
scripts/ncloud occ -- user:report --count-dirs       # table: total / active / disabled users
scripts/ncloud occ -- user:lastseen alice            # plain text (--all for everyone); --output is rejected
scripts/ncloud occ -- user:auth-tokens:list alice --output=json   # [{"id","name","lastActivity","type","scope"}], never secrets
scripts/ncloud occ -- twofactorauth:state alice
scripts/ncloud occ -- admin-delegation:show --output=json
scripts/ncloud occ -- group:list -i --output=json    # {"admin":["alice"],"team":["alice","bob"]}; optional search string
scripts/ncloud occ -- group:info team
scripts/ncloud occ --yes -- user:setting alice core lang --output=json   # read, not allow-listed; omit key/app for all; missing key exits 1
scripts/ncloud occ --yes -- user:profile alice --output=json             # read, not allow-listed
```

### 2.3 `share:list` (all users, admin view)

```bash
scripts/ncloud occ -- share:list --output=json                      # every share of every user
scripts/ncloud occ -- share:list --owner alice --type link --output=json
scripts/ncloud occ -- share:list --file <fileid> --output=json
# [{"id":"<share_id>","file":<fileid>,"target-path":"/Photos","source-path":"/alice/files/Photos","owner":"alice","recipient":null,"by":"alice","type":"link"}]
scripts/ncloud occ -- share:list --parent /alice/files/Projects --recursive   # --parent takes a path or fileid; --recursive needs --parent
scripts/ncloud occ -- share:list --recipient bob --output=json
scripts/ncloud occ -- share:list --status 0 --output=json
```

Filters: `--owner --recipient --by --file --parent --recursive --type --status`. `--status`: 0 pending,
1 accepted, 2 rejected. **`--type` takes names, not numbers** (`--type 3` gives `Unknown share type 3`):

| `--type` | OCS number | Notes |
|---|---|---|
| `user` | 0 | |
| `group` | 1 | 9 (remote group) has the same name but the filter matches only 1 |
| `link` | 3 | the only type files_sharing_raw can serve |
| `email` | 4 | |
| `remote` | 6 | federated |
| `room` | 10 | Talk |
| `deck` | 12 | |
| (not filterable) | 2, 7, 8, 13, 15 | user-group sub-shares, Team/circle, guest, deck-user, ScienceMesh show as `"type":"unknown"`; `--type circle` / `guest` exit 1 |

The output has **no** token, permissions, expiry or password: use OCS (`scripts/ncloud share get <share_id>`).

### 2.4 Files, storage, mounts

```bash
scripts/ncloud occ -- info:file /alice/files/Photos --children      # plain text: fileid, mimetype, size, etag, permissions, mount, storage, who has access
scripts/ncloud occ -- info:file <fileid> --storage-tree
scripts/ncloud occ -- info:file:space /alice/files/Photos --count=3 # largest children (--all for everything)
scripts/ncloud occ -- info:storages --all --output=json
# [{"numeric_id":<storage_id>,"id":"home::alice","files":<n>,...},{"numeric_id":<storage_id>,"id":"local::/srv/data/Photos/","files":<n>,"external_mount_id":<mount_id>}]
scripts/ncloud occ -- info:storage <storage_id>
scripts/ncloud occ -- files:mount:list alice --output=json          # home, external mounts, team folders, received shares (--cached-only)
scripts/ncloud occ -- files_external:list --all --output=json       # mount id, mount point, backend, config (datadir for "local")
scripts/ncloud occ -- files_external:verify <mount_id>              # NOTE: "status: ok" does not prove the backing directory is populated (6.2)
scripts/ncloud occ -- files_external:backends
scripts/ncloud occ -- groupfolders:list --output=json               # [{"id":<folder_id>,"mountPoint":"Team Share","groups":{"team":{"permissions":31}},...}]; -u <uid>
scripts/ncloud occ -- trashbin:size --user alice
scripts/ncloud occ -- preview:queue-stats
scripts/ncloud occ --yes -- files_external:config <mount_id> datadir      # read form, not allow-listed
scripts/ncloud occ --yes -- files_external:option <mount_id> enable_sharing
scripts/ncloud occ --yes -- tag:list --output=json                  # read, not allow-listed
scripts/ncloud occ --yes -- metadata:get <fileid>                   # read, not allow-listed
scripts/ncloud occ --yes -- trashbin:restore --dry-run --all-users  # dry run, not allow-listed
```

**Commands that print secrets**: `files_external:list --show-password`, `files_external:export`,
`config:list --private` (therefore not allow-listed), `user:auth-tokens:add` (the new token),
`config:system:get` on secret keys (`secret`, `passwordsalt`, `dbpassword`, mail/redis passwords). Never paste their
output into a reply, a file in a repo, or a log. `config:list` without `--private` masks these as
`***REMOVED SENSITIVE VALUE***`.

### 2.5 Logs, background jobs, config, routing, security

```bash
scripts/ncloud occ -- log:tail 20                    # table: Level / App / Message / Time
scripts/ncloud occ -- log:tail 50 --raw              # one JSON object per line
# filter errors: ... --raw | jq -c 'select(.level>=3) | {time,app,message,remoteAddr,user}'
timeout 30 scripts/ncloud occ -- log:tail -f --raw   # or log:watch; never follow without a timeout
scripts/ncloud occ --yes -- log:manage               # without arguments: shows backend, level, timezone (not allow-listed)
scripts/ncloud occ --yes -- log:file                 # without arguments: shows log file and rotation size (not allow-listed)
scripts/ncloud occ -- background-job:list --limit 20 --output=json   # [{"id","class","last_run","argument"}]
scripts/ncloud occ -- background-job:list --class 'OCA\Files_Trashbin\BackgroundJob\ExpireTrash' --output=json
scripts/ncloud occ -- config:app:get core backgroundjobs_mode        # ajax | webcron | cron (background:cron etc. are setters)
scripts/ncloud occ -- config:list system --output=json               # secrets masked
scripts/ncloud occ -- config:list bruteForce --output=json           # brute-force bypass list (whitelist_N entries)
scripts/ncloud occ -- router:list files_sharing_raw --output=json    # routes of one app; --ocs / --index variants
scripts/ncloud occ -- router:match /raw/abc/def --method GET         # which controller serves a URL
scripts/ncloud occ -- router:match /remote.php/dav/files/alice/      # "Path not matched": DAV is not in the router
scripts/ncloud occ -- security:bruteforce:attempts 127.0.0.1 --output=json   # {"bypass-listed":false,"attempts":<n>,"delay":<ms>}; optional action name
scripts/ncloud occ -- security:certificates --output=json
scripts/ncloud occ -- webhook_listeners:list --output=json
scripts/ncloud occ -- taskprocessing:task:stats
scripts/ncloud occ --yes -- theming:config            # listing is a read, but not allow-listed; --output rejected
```

Raw log fields: `reqId level(0-4) time remoteAddr user app method url message userAgent version [exception|data]`.

**Brute force and source addresses** [src]: each failed login from an IP delays later attempts from that IP by
0.1 s x 2^n (n = failures in the last 12 h, capped at 25 s, reached after about 8 failures); more than 10 failures
in 12 h **and** more than 10 in the last 30 min gives HTTP 429. Nextcloud sees the address it derives from the
connection and `trusted_proxies` / forwarded headers. Agents behind the same reverse proxy or on the same docker host
(host shell, other containers, the MCP sidecar) often all appear as **one** address (e.g. `127.0.0.1` or the
proxy's IP), share one bucket, and are not helped by a LAN range on the bypass list. Check what Nextcloud records in
the `remoteAddr` of `log:tail --raw`. When slow or 429: `security:bruteforce:attempts <ip>`; reset only with user
consent: `scripts/ncloud occ --yes -- security:bruteforce:reset <ip>` (this clears the history for every agent
sharing that address). **Never retry a 401.**

---

## 3. Configuration

`config.php` is changed **only through occ** (there is no HTTP API; on Nextcloud AIO, do not edit it by hand).

### 3.1 `config:system:get|set|delete`

```bash
scripts/ncloud occ -- config:system:get trusted_domains            # arrays print one value per line
scripts/ncloud occ -- config:system:get redis port                 # nested key = several positional arguments
scripts/ncloud occ -- config:system:get nope --default-value=X     # prints X, exit 0; without --default-value: exit 1
# writes (user asked; --yes)
scripts/ncloud occ --yes -- config:system:set default_phone_region --value=DE
scripts/ncloud occ --yes -- config:system:set maintenance_window_start --value=1 --type=integer
scripts/ncloud occ --yes -- config:system:set some.flag --value=true --type=boolean     # without --type it is stored as the string "true"
scripts/ncloud occ --yes -- config:system:set trusted_domains 5 --value=cloud2.example.com   # array index (AIO rewrites 1 and 2 at every start)
scripts/ncloud occ --yes -- config:system:set redis timeout --value=5 --type=integer    # nested
scripts/ncloud occ --yes -- config:system:set allowed_raw_tokens --type=json --value='["<token>"]'   # whole array
scripts/ncloud occ --yes -- config:system:set some.key --value=y --update-only           # only if the key exists
scripts/ncloud occ --yes -- config:system:delete some.key --error-if-not-exists
```

- `--type`: help lists `string integer double boolean`; the source also accepts `json` and `null` [src]. Default
  `string`.
- `raw_csp` (files_sharing_raw) has **three levels**: `raw_csp <selector> <selector-value> --value=<policy>`,
  selector `token|path_prefix|path_contains|extension|mimetype` [src]. Example:
  `config:system:set raw_csp token <token> --value="default-src 'self'"`. Giving only two levels overwrites the
  whole selector map with a string and silently stops working.
- Always write `<token>` in docs and replies: a real share token is the key to a public URL.

### 3.2 `config:app:get|set|delete`

```bash
scripts/ncloud occ -- config:app:get files_sharing_raw csp_editor_group --default-value='(unset)'
scripts/ncloud occ -- config:app:get files_sharing_raw enabled --details      # value details; --key-details for lexicon flags (type lazy sensitive internal)
scripts/ncloud occ -- config:app:get password_policy minLength --default-value='(default)'
scripts/ncloud occ --yes -- config:app:set previewgenerator squareSizes --value="64 256"
scripts/ncloud occ --yes -- config:app:set <app> <key> --value=V --type=string    # --type string|integer|float|boolean|array, --lazy/--no-lazy, --sensitive/--no-sensitive, --internal, --update-only
scripts/ncloud occ --yes -- config:app:delete <app> <key> --error-if-not-exists
```

- Keys marked internal in the app's lexicon need `--internal` (otherwise `Config key is set as INTERNAL`, exit 1).
- Changing type/lazy/sensitive of an existing key asks for confirmation; under `-n` the default applies, so
  **re-read** after changing.
- Passwords for `user:add` / `user:resetpassword` must satisfy `password_policy` (`minLength` etc.).
- HTTP alternative (admin): `GET|POST|DELETE /ocs/v2.php/apps/provisioning_api/api/v1/config/apps/{app}[/{key}]`;
  it refuses `installed_version`, `enabled`, `types` and a few core keys (see `API_OCS.md`).

### 3.3 `config:import`, `theming:config`

```bash
scripts/ncloud occ --yes --stdin -- config:import             # no file argument = read stdin; {"system":{...},"apps":{app:{key:val}}}
scripts/ncloud occ --yes -- theming:config                    # list all (read, not allow-listed)
scripts/ncloud occ --yes -- theming:config name "Team Cloud"  # write; keys: name url imprintUrl privacyUrl slogan color primary_color background_color disable-user-theming
scripts/ncloud occ --yes -- theming:config slogan --reset
```

`config:import`: keys **absent** from the JSON are untouched, keys with value **`null` are deleted** [src], so an
import file containing `null` is destructive.

### 3.4 Keys Nextcloud AIO rewrites (AIO 14.x entrypoint)

| Scope | Keys | Consequence |
|---|---|---|
| **(a) reset at every container start** (manual changes are reverted) | `one-click-instance*`, `loglevel`, `log_type`, `log_type_audit`, `logfile`, `logfile_audit`, `updatedirectory`, `skeletondirectory`, `maintenance_window_start`, `allow_local_remote_servers`, `davstorage.request_timeout`, `trusted_domains[1]` (= `NC_DOMAIN`) and `[2]` (= `ADDITIONAL_TRUSTED_DOMAIN`), `overwrite.cli.url`, `htaccess.RewriteBase`, `dbpersistent`, `auth.bruteforce.protection.enabled`, `ratelimit.protection.enabled`, `files_external_allow_create_new_local`, `trusted_proxies[0,1,2,10]`, notify_push `base_endpoint`, `enabledPreviewProviders[0]/[23]` and `preview_imaginary_*` (when Imaginary is on) | change the mastercontainer environment instead (`ADDITIONAL_TRUSTED_DOMAIN`, `NEXTCLOUD_MAINTENANCE_WINDOW`, `ADDITIONAL_TRUSTED_PROXY`, `NEXTCLOUD_LOG_LEVEL`, ...); `log:manage --level=debug` lasts until the next restart |
| **(b) written once at install** (occ changes persist) | `updatechecker`, `log_rotate_size`, `log.condition`, `preview_max_x/y`, `jpeg_quality`, `enabledPreviewProviders[1-7]`, `upgrade.disable-web`, `trashbin_retention_obligation`, `versions_retention_obligation`, `share_folder` | `config:system:set` directly |
| **(c) run on image upgrades** | `occ upgrade`, `app:update --all`, `maintenance:repair`, `db:add-missing-*` | do not run them pre-emptively |
| custom keys (`raw_csp`, `allowed_raw_tokens`, `default_phone_region`, ...) | never touched | |

---

## 4. Users and groups

Apart from `user:list/info/report/lastseen`, `user:auth-tokens:list`, `group:list/info` and
`admin-delegation:show`, nothing here is on the allow-list: `--yes`, and only on explicit request. Password
commands (`--password-from-env`): in local docker mode `NC_PASS=... scripts/ncloud occ --yes -- ...` forwards the
variable (1.1); over ssh use the raw `read` form (1.2).

```bash
# create (uid characters: a-z A-Z 0-9, space and _.@-'; password must satisfy password_policy)
NC_PASS="$PW" scripts/ncloud occ --yes -- user:add alice --password-from-env --display-name=Alice --group=team --email=alice@example.com   # -g repeatable; missing groups are created
scripts/ncloud occ --yes -- user:add bob --generate-password --email bob@example.com   # a reset mail is sent only if mail delivery is configured
# password and state
NC_PASS="$PW" scripts/ncloud occ --yes -- user:resetpassword --password-from-env alice   # without NC_PASS occ would prompt, and the prompt gets no answer
scripts/ncloud occ --yes -- user:disable alice
scripts/ncloud occ --yes -- user:enable alice        # also unlocks accounts locked by password_policy
scripts/ncloud occ --yes -- user:delete alice        # no confirmation, irreversible, deletes the files; exit 0 even if missing
# settings
scripts/ncloud occ --yes -- user:setting alice settings email alice@example.org
scripts/ncloud occ --yes -- user:setting alice files quota "10 GB"
scripts/ncloud occ --yes -- user:setting alice core lang --delete
# app passwords (tokens)
scripts/ncloud app-password agent-cli --yes          # = occ user:auth-tokens:add <NEXTCLOUD_USER> --name agent-cli -n; token printed once on stdout
scripts/ncloud app-password agent-cli --uid alice --json --yes
NC_PASS="$LOGIN_PW" scripts/ncloud occ --yes -- user:auth-tokens:add alice --name=agent-cli --password-from-env   # token that includes the login password
scripts/ncloud occ --yes -- user:auth-tokens:delete alice <token_id>         # or --last-used-before=2026-01-01; disconnects that client
# groups
scripts/ncloud occ --yes -- group:add team --display-name="Team"
scripts/ncloud occ --yes -- group:adduser team alice bob
scripts/ncloud occ --yes -- group:removeuser team bob
scripts/ncloud occ --yes -- group:delete team
scripts/ncloud occ --yes -- admin-delegation:add 'OCA\Settings\Settings\Admin\Sharing' team
```

- `user:auth-tokens:add` with `-n` and without `NC_PASS` creates an app password **without** the login password:
  it prints `No password provided. ... limited capabilities ...`, then `app password:`, and the last line is the
  72-character token (shown once) [src]. `scripts/ncloud app-password <name> --yes` uses exactly this (minting a
  credential is sensitive, hence `--yes`; never paste the token into chat or a repo). Observed on Nextcloud 33: such
  a token works for OCS `/cloud/user`, WebDAV PROPFIND and share listing; only operations that need the login
  password (e.g. server-side encryption keys) fail. Use `NC_PASS ... --password-from-env` for a full token.
- The same operations exist in the OCS Provisioning API (`scripts/ncloud user ...`, admin) when there is no occ
  access (`API_OCS.md`).

---

## 5. Apps

```bash
scripts/ncloud occ -- app:list --disabled                 # shows "ver (installed ver)"
scripts/ncloud occ --yes -- app:enable notes              # -g <group> (repeatable) restricts; -f ignores version requirements
scripts/ncloud occ --yes -- app:disable notes
scripts/ncloud occ --yes -- app:install notes --keep-disabled   # -f, --allow-unstable
scripts/ncloud occ --yes -- app:update notes               # --all, --allow-unstable; --showonly / --showcurrent also need --yes
scripts/ncloud occ --yes -- app:remove notes --keep-data
```

HTTP covers only list / enable / disable (`/ocs/v2.php/cloud/apps[/{app}]`, POST enables, DELETE disables);
install / update / remove are occ-only.

On Nextcloud AIO (AIO 14.x entrypoint):

- `app:disable` on a normal store app **persists** across restarts. `REMOVE_DISABLED_APPS=yes` removes only the
  **companion apps** switched off in the AIO interface (richdocuments, onlyoffice, spreed, files_antivirus,
  fulltextsearch*, whiteboard).
- **Do not disable or install companion apps by hand**: `notify_push`, `richdocuments`, `fulltextsearch*` are
  re-installed / enabled / updated by the entrypoint at every start; `app_api` is toggled by AIO.
- Do not run `app:update --all`: the entrypoint runs it after image upgrades and, with
  `UPDATE_NEXTCLOUD_APPS=yes`, weekly. `STARTUP_APPS` (default deck, twofactor_totp, tasks, calendar, contacts,
  notes) are installed only on a fresh install.
- After an upgrade an app may be disabled as incompatible (standard Nextcloud behaviour): check
  `app:list --disabled` for `(installed x)`, then `app:update <id>` or `app:enable <id>` with consent; see
  `TROUBLESHOOTING.md`.

---

## 6. Files and storage

### 6.1 Path forms [src]

- A pure number is a fileid (also resolves inside shares and external storages).
- Otherwise an **absolute root path** `/<uid>/files/<sub>`: `/alice/files/Documents/...`. External mounts and team
  folders appear under the user's tree at their mount point (`/alice/files/<mount point>/...`). `files:scan --path`
  uses the same form; the `files` segment is required.

### 6.2 `files:scan` - and how not to wipe the file cache

```bash
scripts/ncloud occ --yes -- files:scan --path=/alice/files/Projects/site     # one subtree (user derived from the path; user argument and --all ignored) - preferred form
scripts/ncloud occ --yes -- files:scan --path=/alice/files/Projects --shallow # no recursion
scripts/ncloud occ --yes -- files:scan --home-only alice                     # home storage only, skips external storages and received shares
scripts/ncloud occ --yes -- files:scan --unscanned alice                     # only items marked incomplete (still walks external mounts)
scripts/ncloud occ --yes -- files:scan --generate-metadata alice             # also compute metadata
scripts/ncloud occ --yes -- files:scan --path=/alice/files/Projects -v --output=json   # {folders,files,new,updated,removed,errors,elapsed}
scripts/ncloud occ --yes -- files:scan-app-data preview                      # appdata
scripts/ncloud occ --yes -- files_external:scan <mount_id> --path=sub        # by external mount id; --unscanned
scripts/ncloud occ --yes -- groupfolders:scan <folder_id> --path=/sub        # or --all; --shallow
```

When a scan is needed: `filesystem_check_changes=1` covers only home storage and checks at most once per request;
files written **directly on the server's disk** (data directory or an external storage's backing directory) get a
fileid, ETag, search hits and raw serving only after `files:scan --path=...`. Writes through WebDAV need no scan.

**Hazard - missing backing mount.** The scanner cannot tell "the backing directory is empty because its disk or
network mount is missing" from "all files were deleted". If an external storage (or the data directory) points at a
mount that is absent or empty, any scan that reaches it **removes all its filecache rows** [src Scanner], and with
them previews, tags, comments, activity links and the validity of shares on those files. `files_external:verify`
can still report `status: ok` for an empty directory. Therefore:

1. Scan explicit subtrees (`--path=/<uid>/files/<sub>`). Avoid broad scans (`files:scan <uid>`, `--all`,
   `--unscanned`, `files_external:scan <mount_id>` without `--path`) unless the user asked and every mount they
   touch was checked.
2. Before scanning anything that includes an external "local" storage, check that the backing directory is mounted
   and populated, e.g. `docker exec nextcloud-aio-nextcloud sh -c 'ls -A <datadir> | head'`, and compare with
   `files_external:list` / `info:storages` (non-zero `files` with an empty directory is the danger sign).
3. Record such hazards (mounts that may be offline, folders never to scan) in the private site notes
   (`SITE_NOTES.md`) and read them (`scripts/ncloud config notes`) before any scan.
4. Every scan needs user consent (`--yes`).

### 6.3 `files:get|put|copy|move|delete`

```bash
scripts/ncloud occ -- files:get /alice/files/Readme.md           # to stdout; binary content to a TTY is refused -> give "-" or an output path (inside the container)
scripts/ncloud occ -- files:get <fileid> -
echo "text" | scripts/ncloud occ --yes --stdin -- files:put - /alice/files/Notes/today.md   # create or overwrite; parent must exist; target may be an existing fileid
scripts/ncloud occ --yes -- files:copy <src> /alice/files/Archive/ -f     # into a folder target; -T overwrites the folder itself
scripts/ncloud occ --yes -- files:move <src> /alice/files/Archive/ -f
scripts/ncloud occ --yes -- files:delete <fileid> -f              # without -f it asks [y/N] and silently does nothing
```

These go through the normal node API: filecache, ETag and activity update immediately. Whether `files:delete`
goes to the trash bin is UNVERIFIED (it calls `$node->delete()`; the trash wrapper should apply, not documented).
For the configured user's own files prefer `scripts/ncloud get/put/rm` (WebDAV).

### 6.4 Checks and repair

```bash
scripts/ncloud occ --yes -- files:repair-tree --dry-run          # -s <storage_id>, -p <path>; drop --dry-run to write
scripts/ncloud occ --yes -- files:sanitize-filenames --dry-run alice   # -c _ ; without --dry-run it renames
scripts/ncloud occ --yes -- files:cleanup                        # removes orphaned filecache/mount rows (e.g. of deleted storages)
scripts/ncloud occ --yes -- files:transfer-ownership alice bob --path=Projects   # --move, --include-external-storage
scripts/ncloud occ --yes -- files:windows-compatible-filenames --enable
```

### 6.5 External storage and team folders

```bash
scripts/ncloud occ --yes -- files_external:create /Archive local null::null -c datadir=/srv/data/archive --user alice --dry   # local backend needs files_external_allow_create_new_local=true
scripts/ncloud occ --yes -- files_external:applicable <mount_id> --add-user alice --add-group team   # or --remove-all
scripts/ncloud occ --yes -- files_external:config <mount_id> datadir /srv/data/new
scripts/ncloud occ --yes -- files_external:option <mount_id> enable_sharing true
scripts/ncloud occ --yes --stdin -- files_external:import - --dry            # --dry also needs --yes
scripts/ncloud occ --yes -- files_external:notify <mount_id> --dry-run
scripts/ncloud occ --yes -- files_external:delete <mount_id> -y
scripts/ncloud occ --yes -- groupfolders:create "Team Share"
scripts/ncloud occ --yes -- groupfolders:group <folder_id> team read write share delete   # -d removes the group
scripts/ncloud occ --yes -- groupfolders:quota <folder_id> unlimited
scripts/ncloud occ --yes -- groupfolders:permissions <folder_id> -e     # enable advanced permissions (ACL); -d disables
scripts/ncloud occ --yes -- groupfolders:trashbin:cleanup <folder_id> -f
scripts/ncloud occ --yes -- groupfolders:delete <folder_id> -f
```

Also: `groupfolders:rename <id> <name>`, `groupfolders:expire`, ACL rules with
`groupfolders:permissions <id> [-u user|-g group|-c team] <path> -- +read -write`.
The groupfolders HTTP API lives under `/apps/groupfolders/folders...` (not `/ocs/v2.php`) and needs
`OCS-APIRequest: true`.

### 6.6 Trash bin, versions, previews

```bash
scripts/ncloud occ -- trashbin:size --user alice          # query (allow-list); with a <size> argument it is a write
scripts/ncloud occ --yes -- trashbin:expire alice         # apply retention; no uid = everyone
scripts/ncloud occ --yes -- versions:expire alice
scripts/ncloud occ --yes -- trashbin:cleanup alice        # empties the trash bin (--all-users for everyone)
scripts/ncloud occ --yes -- trashbin:restore --dry-run alice --since 2026-10-01   # -s user|groupfolders|all, --until
scripts/ncloud occ --yes -- versions:cleanup alice --path=/alice/files/Music      # deletes versions
scripts/ncloud occ --yes -- preview:pre-generate          # previewgenerator: new/changed files
scripts/ncloud occ --yes -- preview:generate-all -p /alice/files/Photos   # heavy; -w workers; uids
scripts/ncloud occ --yes -- preview:generate <fileid> -s 256x256         # -c crop, -m cover|fill
scripts/ncloud occ --yes -- preview:cleanup               # deletes all previews (regenerated later, expensive)
```

The matching background jobs (`ExpireTrash`, `ExpireVersions`, previewgenerator cron) do not run while maintenance
mode is on (9.1).

---

## 7. Full-text search

```bash
scripts/ncloud occ -- fulltextsearch:check              # platform, index name, providers and their options (files_local, files_external, files_group_folders, size limit)
scripts/ncloud occ -- fulltextsearch:search alice readme   # positional <user> <needle>; there is no --user
scripts/ncloud occ -- fulltextsearch:test -j
scripts/ncloud occ --yes -- fulltextsearch:index '{"users":["alice"],"providers":["files"],"path":"/files/Projects/site"}' -r
scripts/ncloud occ --yes -- fulltextsearch:index '{"errors":"reset"}'
timeout 600 scripts/ncloud occ --yes -- fulltextsearch:live -r -s   # foreground indexer instead of waiting for cron
scripts/ncloud occ --yes -- fulltextsearch:stop
scripts/ncloud occ --yes -- fulltextsearch:reset --provider files   # destroys the index; explicit request only
scripts/ncloud occ --yes -- fulltextsearch:document:index alice files <fileid>
```

External storages and team folders are indexed only if `fulltextsearch:check` shows the corresponding options
enabled (`files_external`, `files_group_folders`). Indexing advances on cron ticks and pauses in maintenance mode.
On Nextcloud AIO the fulltextsearch apps are managed by AIO (section 5). User-level search goes through
`scripts/ncloud usearch` / WebDAV SEARCH; use occ only to debug the index.

---

## 8. Share repair

occ **cannot create shares** (only `share:list`, 2.3); create/update/delete with `scripts/ncloud share ...`.
Repair commands: dry-run first.

```bash
scripts/ncloud occ --yes -- sharing:fix-share-owners --dry-run
scripts/ncloud occ --yes -- sharing:cleanup-remote-storages --dry-run
scripts/ncloud occ --yes -- sharing:delete-orphan-shares -f          # --owner X --with Y; without -f it asks and does nothing
scripts/ncloud occ --yes -- maintenance:repair-share-owner alice -y  # fixes owners of received shares; without -y it asks
scripts/ncloud occ --yes -- sharing:expiration-notification          # sends mail
```

Never modify existing shares unless the user names them; the site notes may list shares that must not be touched.

---

## 9. Maintenance, background jobs, upgrades

### 9.1 `maintenance:mode`

```bash
scripts/ncloud occ -- maintenance:mode                # query (allow-list)
scripts/ncloud occ --yes -- maintenance:mode --on     # only when the user says so; --off to end it
```

While on: every `index.php` request (web UI, OCS, app routes including `/raw/...`) returns **503** with
`X-Nextcloud-Maintenance-Mode: 1`; WebDAV returns 503 `System is in maintenance mode.`; sessions are locked; occ
still runs but loads only a minimal app set, so `share:list`, `trashbin:*`, `preview:*`, `groupfolders:*`,
`fulltextsearch:*` are unavailable or incomplete; **all background jobs stop**. On Nextcloud AIO a container restart
clears a stuck maintenance mode (the entrypoint runs `maintenance:mode --off`). `maintenance: true` in
`status.php` can also mean an AIO update is running: wait first (`TROUBLESHOOTING.md`).

### 9.2 Repair, database, upgrades

```bash
scripts/ncloud occ --yes -- maintenance:repair                    # --include-expensive; AIO also runs it on upgrades
scripts/ncloud occ --yes -- maintenance:data-fingerprint          # after restoring a backup
scripts/ncloud occ --yes -- maintenance:mimetype:update-db
scripts/ncloud occ --yes -- maintenance:update:htaccess
scripts/ncloud occ --yes -- db:add-missing-indices --dry-run      # prints SQL only
scripts/ncloud occ --yes -- db:add-missing-indices                # DDL; also db:add-missing-columns, db:add-missing-primary-keys
scripts/ncloud occ -- update:check                                # read-only (allow-list)
scripts/ncloud occ --yes -- migrations:preview <app>              # read-only, not allow-listed
scripts/ncloud occ --yes -- upgrade                               # never by hand on AIO: the entrypoint runs it on image upgrades
```

Other maintenance commands: `maintenance:mimetype:update-js`, `maintenance:theme:update`. `db:convert-type`,
`db:convert-filecache-bigint` and `encryption:*` are in section 11.

### 9.3 Background jobs, notifications, webhooks, task processing

```bash
scripts/ncloud occ -- background-job:list --limit 20 --output=json
scripts/ncloud occ --yes -- background-job:execute <job_id> --force-execute   # run one job now
scripts/ncloud occ --yes -- background-job:worker 'OCA\WebhookListeners\BackgroundJobs\WebhookCall' --once   # -t 10m
scripts/ncloud occ --yes -- background-job:delete <job_id>
scripts/ncloud occ --yes -- notification:generate alice "Short message" -l "Long message"   # --object-type/--object-id, --output-id-only
scripts/ncloud occ --yes -- notification:test-push alice
scripts/ncloud occ -- webhook_listeners:list --output=json        # creating webhooks is OCS-only (scripts/ncloud webhook)
scripts/ncloud occ -- taskprocessing:task:list -u alice --output=json
scripts/ncloud occ --yes -- taskprocessing:task:cleanup 86400
```

`background:cron|ajax|webcron` are **setters** (change the job mode), not queries; read the mode with
`config:app:get core backgroundjobs_mode`.

---

## 10. Nextcloud AIO notes

Observed with Nextcloud AIO 14.x (Nextcloud 33):

- **Containers**: Nextcloud itself runs in `nextcloud-aio-nextcloud` (`/var/www/html/occ`, always `-u www-data`);
  siblings `nextcloud-aio-apache`, `-database` (PostgreSQL), `-redis`, `-notify-push`, and optional `-collabora`,
  `-imaginary`, `-fulltextsearch`, ...; the management UI is `nextcloud-aio-mastercontainer`.
- **Paths inside the container**: apps from the store in `/var/www/html/custom_apps/`, `config.php` in
  `/var/www/html/config/` (volume `nextcloud_aio_nextcloud`), logs per `log:file` (by default
  `/var/www/html/data/nextcloud.log` and `audit.log`); the user data directory is the host path chosen as
  `NEXTCLOUD_DATADIR`.
- **Do not edit `config.php` by hand**: use `config:system:*` (atomic, validated, respects `--type`), and expect AIO
  to rewrite the keys in 3.4 (a).
- **The mastercontainer owns the lifecycle**: updates, BorgBackup, stopping/starting the stack (AIO interface, or
  `docker exec --env AUTOMATIC_UPDATES=1 nextcloud-aio-mastercontainer /daily-backup.sh` and its `DAILY_BACKUP`,
  `STOP_CONTAINERS`, `START_CONTAINERS` variants - admin actions, not agent actions). `update:check` reporting a
  new version is information only. **Never run `occ upgrade` or `app:update --all` by hand.**
- **Backups stop containers** (not maintenance mode; grace periods around 600 s for Nextcloud and 1800 s for the
  database), so during the backup/update window occ cannot connect and HTTP calls fail. Nextcloud's own
  `maintenance_window_start` is unrelated to the AIO backup time.
- **Cron**: a supervisord program in the Nextcloud container starts `cron.php` every 5 minutes (no host crontab);
  background work such as webhook delivery and indexing therefore lags by up to about 5 minutes.
- **Restarting** `nextcloud-aio-nextcloud` reruns the entrypoint (re-applies 3.4 (a), runs `maintenance:mode --off`,
  checks companion apps) and **kills running occ commands** (`files:scan`, `preview:generate-all`,
  `fulltextsearch:live`). Stop/start the whole stack from the AIO interface; never `docker rm` AIO containers. PHP
  limits come from the AIO environment (`PHP_MEMORY_LIMIT`, `PHP_MAX_TIME`); wrap long occ commands in `timeout`
  on the agent side.
- **Brute force**: AIO forces `auth.bruteforce.protection.enabled` and `ratelimit.protection.enabled` to `true` at
  every start. Whether local agents share one source address depends on the reverse proxy and `trusted_proxies`
  (2.5).
- **Network storage**: if the data directory or an external storage sits on a network filesystem mounted `hard`,
  an outage makes file operations (occ included) hang instead of failing; see 6.2 for what a missing mount does to
  scans.

---

## 11. Dangerous commands

None of these is on the allow-list: the CLI requires `--yes`, and `--yes` may only be added after the user
explicitly asked. One-line consequences:

| Command | Consequence |
|---|---|
| `user:delete` | no confirmation; deletes the account and all its files; exit 0 even if the user does not exist |
| `user:disable`, `user:resetpassword` | locks the user out / changes the password at once; sync clients disconnect |
| `user:auth-tokens:delete` | that device's / agent's app password stops working immediately |
| `user:auth-tokens:add` | mints a full-account credential (prints it once) |
| `group:delete`, `group:removeuser admin ...` | group shares and admin rights disappear |
| `files:delete`, `files:move/copy -f`, `files:put` over an existing file | overwrites or moves other users' files (trash behaviour UNVERIFIED) |
| `files:transfer-ownership`, `files:cleanup`, `files:repair-tree` / `files:sanitize-filenames` without `--dry-run` | mass moves, deleted filecache rows, renamed files |
| `files:scan <uid>`, `files:scan --all`, `files:scan --unscanned`, `files_external:scan <mount_id>`, `groupfolders:scan --all` | if any reached mount is missing or empty: all its filecache rows are wiped (6.2) |
| `trashbin:cleanup`, `trashbin:expire`, `versions:cleanup`, `versions:expire`, `groupfolders:trashbin:cleanup`, `groupfolders:expire` | permanently deletes trash / versions |
| `groupfolders:delete`, `files_external:delete`, `files_external:create/config/option/applicable/import` | mounts vanish or point elsewhere; users see whole trees disappear |
| `sharing:delete-orphan-shares`, `maintenance:repair-share-owner` | deletes / rewrites share rows |
| `preview:cleanup`, `preview:generate-all`, `fulltextsearch:reset`, broad `fulltextsearch:index` | deletes all previews / destroys the index / hours of CPU |
| `config:system:delete`, `config:app:delete`, `config:system:set` on core keys (`trusted_domains`, `overwrite*`, `redis`, `db*`, `datadirectory`, `secret`, `passwordsalt`, `instanceid`), `config:import` containing `null` | site unreachable, keys invalidated, settings deleted |
| `config:system:set` on AIO-managed keys (3.4 a) | wasted: reverted at the next restart |
| `maintenance:mode --on` | every API returns 503, all background jobs stop |
| `upgrade`, `app:update`, `app:install`, `app:enable/disable`, `app:remove` | races the AIO entrypoint; companion apps get reverted; features disappear for users |
| `db:convert-type`, `db:convert-filecache-bigint`, `db:add-missing-*`, `encryption:*` | DDL / site-wide encryption changes; must not be interrupted |
| `background:cron|ajax|webcron`, `background-job:delete`, `log:manage --level=debug`, `log:file --file` | changes the job mode / deletes jobs / fills the disk |
| `security:bruteforce:reset <ip>` | clears failure history for every client sharing that address (2.5) |
| `notify_push:reset/setup`, `theming:config <key> <value>`, `admin-delegation:add`, `integrity:sign-*`, `richdocuments:activate-config`, `memcache:*:clear/delete`, `memcache:redis:command`, `dav:delete-calendar`, `dav:remove-invalid-shares`, `dav:retention:clean-up`, `calendar:import`, `deck:import`, `deck:transfer-ownership`, `mail:account:delete`, `tag:delete`, `tag:files:delete-all`, `twofactorauth:disable`, `oauth2:delete-client`, `security:certificates:remove` | each irreversible or affects other users |

---

## 12. Decision rules: occ vs API vs MCP

| Need | Layer | Why |
|---|---|---|
| The configured user's own files: list, upload, download, move, trash, versions, search | **API** (`scripts/ncloud ls/put/get/mv/trash/search`) | user-scoped, works from any runtime, filecache updated at once; occ `files:*` only without a network path |
| Create / change / delete shares, tokens, expiry, passwords | **API** (`scripts/ncloud share`) | occ cannot create shares and `share:list` shows no tokens |
| Raw link switch and CSP (filehost) | **API** (app routes); occ only for the global fallbacks `allowed_raw_tokens` / `raw_csp` | the per-share registry is in the database |
| List shares across users, `info:file` on other users' nodes | **occ** `share:list`, `info:file` | admin view; OCS shows only your own |
| `config.php`, app install / update / remove | **occ** | no HTTP API |
| Users, groups, app passwords, app enable/disable, app config | **occ** when available, else the OCS Provisioning API | both admin-only; occ sends no admin credential over HTTP |
| Files written directly on the server disk, after a backup restore | **occ** `files:scan --path=...` / `files_external:scan` / `groupfolders:scan` | only the server can rebuild the filecache (read 6.2 first) |
| Logs, setupchecks, brute force, background jobs, trash/version expiry, previews, full-text index | **occ** | server side |
| Maintenance mode, repair, database indices, upgrades | **occ with human approval**; on AIO prefer the mastercontainer | sections 9, 10 |
| Calendar / contacts / Deck / Talk / Notes / Mail multi-step semantics | **MCP** (on demand, `MCP.md`), else CalDAV/CardDAV/app OCS | occ has only `dav:*`, `calendar:export/import`, `deck:export`, `mail:*` admin commands |
| Agent without occ access (`occ_mode: off`) | **API**; tell the user which occ command to run by hand (e.g. a `files:scan --path`) | |
| Batch work on the Nextcloud host itself | **occ** (local docker exec) | fastest, no token needed |

Tie-breakers: one user's own data -> API; `config.php`, app installation, server-side files, filecache, logs, jobs
-> occ; other users' data or site-wide -> occ if available, else admin OCS; multi-step app semantics with MCP
deployed -> MCP; no occ -> API plus a manual step for the user.
