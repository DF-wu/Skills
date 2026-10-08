# API_OCS.md - OCS and app-route reference

Shares, provisioning, unified search, user status, notifications, activity, webhooks, raw links and app
passwords. Verified on Nextcloud 33 (AIO): every endpoint was matched against `occ router:list` and exercised with
read-only calls; **write** endpoints were checked against the source / OpenAPI only and are marked "write, not
tested" unless stated otherwise. **UNVERIFIED** = inferred from source, not observed. Status-code troubleshooting:
`TROUBLESHOOTING.md`. occ equivalents: `OCC.md`.

curl examples use `NC=https://cloud.example.com` and `AUTH=alice:<app-password>` (`-u "$AUTH"`). Share tokens are
always written `<token>`: a real token is the key to a public URL and must never appear in a repo or a reply.

## `scripts/ncloud call` (escape hatch)

```
scripts/ncloud call METHOD PATH [-d k=v ...] [--json FILE] [--body-file FILE] [-H 'K: V'] [-i] [--no-ocs] [--no-auth] [--yes]
```

- A relative `PATH` is appended to `NEXTCLOUD_URL`; Basic auth and `OCS-APIRequest: true` are added; paths
  containing `/ocs/` get `format=json` (`--no-ocs` disables that). The HTTP status goes to stderr (`-i` adds the
  response headers), the body to stdout unchanged; exit 3 when HTTP >= 400.
- **Absolute URLs on another origin are refused** unless `--no-auth`, which sends the request without any
  `Authorization`. The app password is a full-account credential and is never sent to another host; a redirect to
  another origin also drops `Authorization`.
- `-d k=v` (repeatable) builds a form-encoded body; `--json FILE` (`-` = stdin) sends JSON with
  `Content-Type: application/json`; `--body-file FILE` sends raw bytes.
- `DELETE` requires `--yes` (after the user agreed). Other methods are not blocked: confirm writes yourself.
- Global `--url/--user/--password` override the login and must come **before** the subcommand
  (`scripts/ncloud --url https://cloud.example.com call GET /ocs/v2.php/cloud/user`); subcommand options such as
  `share create --password` never become credentials.

## Contents

1. Conventions (envelope, headers, format, status codes, pagination, language)
2. Capabilities and `/cloud/user`
3. Shares API
4. Provisioning (users, groups, apps, app config)
5. Unified search
6. User status
7. Notifications
8. Activity
9. Webhooks (webhook_listeners)
10. files_sharing_raw (non-OCS)
11. App passwords
12. Decision rules

---

## 1. Conventions

**Envelope** (`?format=json`): `{"ocs":{"meta":{"status":"ok","statuscode":200,"message":"OK"},"data":...}}`. v1
(`/ocs/v1.php`) adds usually empty `meta.totalitems` / `meta.itemsperpage` and uses success code **100**.

**Header**: every OCS and app route needs `OCS-APIRequest: true`; without it the answer is HTTP **412**
`{"message":"CSRF check failed"}` (no envelope). `Authorization: Bearer <app-password>` avoids the header on **OCS
routes** only, not on non-OCS app routes such as `/apps/files_sharing_raw/...` (still 412). Rule: always send the
header.

**Format**: XML by default; `?format=json` or `Accept: application/json`. Request bodies may be form-encoded
(`-d k=v`) or JSON (`--json FILE`); array parameters are `name[]=a&name[]=b` in forms and arrays in JSON.

- **Share passwords work as JSON or form** (observed on Nextcloud 33): `share create --password` and a
  form-encoded `call PUT .../shares/<share_id> -d password=...` both return 200. If such a request fails with
  401 / OCS 997, the *login* credential was wrong (and a brute-force failure was recorded), not the password
  format. The CLI sends JSON for `share create/update` and `user create/set`; that is an implementation detail, not a
  server requirement.
- JSON types matter (controller parameters are typed [src]): `shareType` and `permissions` are numbers;
  parameters declared as strings (`publicUpload`, `hideDownload`, `expireDate`, `attributes`, `sendMail`, ...) must
  be strings, e.g. `"hideDownload":"true"`, not `true`.

**Status codes** (v2 HTTP codes are meaningful; v1 answers HTTP 200 for everything except 997):

| Situation | v2 HTTP / `meta.statuscode` |
|---|---|
| success | 200 / 200 (v1: 200 / 100) |
| authentication failed | 401 / 997 |
| OCSNotFound: unknown share id, missing path, **malformed `expireDate` on create** | 404 / 404 |
| OCSBadRequest: search without a valid filter, sharees without `itemType`, malformed `expireDate` on update | 400 / 400 |
| OCSForbidden: non-admin on an admin route, `getapppassword` called with an app password | 403 / 403 |
| rate limit hit (e.g. share creation, 3.5) | 429, body `[]` (no envelope) |
| uncaught exception (unknown search provider, `title-only=true`) | 500 / 996 |
| 204 / 304 | empty body, no envelope |

**Pagination** has no common convention: provisioning lists use `search`/`limit`/`offset`; sharees use
`page`/`perPage` (**max 25**, from `sharing.maxAutocompleteResults`; a full page carries
`Link: <...&page=N+1>; rel="next"` until a page is not full); unified search uses `limit` + `cursor`; activity uses
`since` + `limit` + `Link`/`X-Activity-*` headers; share and notification lists are not paginated.

**Language**: `meta.message` and messages inside `data` follow the account language; add `forceLanguage=en` to
any call for English. Decide on `statuscode`, never on message strings:

```bash
scripts/ncloud call GET /ocs/v2.php/cloud/user | jq -e '.ocs.meta.statuscode == 200' >/dev/null || echo fail
curl -sS -u "$AUTH" -H 'OCS-APIRequest: true' "$NC/ocs/v2.php/cloud/user?format=json" | jq '.ocs.data.id'
```

## 2. Capabilities and `/cloud/user`

```bash
scripts/ncloud caps                                  # version + capability keys
scripts/ncloud caps --section files_sharing.public   # one subtree (dot path)
scripts/ncloud caps --full                           # everything
scripts/ncloud whoami                                # /cloud/user
scripts/ncloud status                                # /status.php, no auth (version, maintenance)
```

`GET /ocs/v2.php/cloud/capabilities` returns `data.version={major,minor,micro,string}` and `data.capabilities`,
whose keys depend on the installed apps and on the caller (anonymous requests get only a few, such as
`bruteforce` and `theming`). Values worth checking before acting:

- `files_sharing.public.{enabled, password.enforced, expire_date.enabled, multiple_links, upload, upload_files_drop, custom_tokens, send_mail}`
- `files_sharing.default_permissions`, `files_sharing.resharing`, `files_sharing.federation.outgoing`, `files_sharing.sharebymail.enabled`
- `core.can-create-app-token`, `core.webdav-root`, `files.chunked_upload.max_size`, `fulltextsearch.providers`
- `password_policy.minLength` and `password_policy.api.generate` = `GET /ocs/v2.php/apps/password_policy/api/v1/generate`
  -> `{"password":"..."}` (use it to make share passwords).

There is **no** capability for `webhook_listeners` or `files_sharing_raw` (detect them via `/cloud/apps`, section 4),
and the app config `core/shareapi_allow_federation_on_public_shares` that decides the extra SHARE bit (3.4) is not
exposed either.

`GET /ocs/v2.php/cloud/user` -> `{id, enabled, displayname, email, groups:[...], language, locale, timezone,
quota:{free,used,total,quota}, backend, storageLocation, lastLogin, subadmin:[], manager,
phone/address/website/...Scope, backendCapabilities:{setDisplayName,setPassword}}` (`-3` = unlimited quota). Same
shape as `/cloud/users/{id}`.

## 3. Shares API

Base `/ocs/v2.php/apps/files_sharing/api/v1`:

```
GET    /shares                     list (3.1)                    POST   /shares              create (3.5)
GET    /shares/{id}                one share; data is a 1-element array   PUT  /shares/{id}  update (3.6)
DELETE /shares/{id}                delete (3.7)                  POST   /shares/{id}/send-email  resend a mail share (body may carry password)
GET    /shares/inherited?path=     shares inherited from parent folders
GET    /shares/pending             user/group shares waiting for me; POST /shares/pending/{id} accepts
GET    /deletedshares              group shares I left; POST /deletedshares/{id} restores
GET    /remote_shares[/pending]    federated shares; GET|DELETE /remote_shares/{id}; POST|DELETE /remote_shares/pending/{id}
GET    /sharees?search=&itemType=  share recipients (3.9); GET /sharees_recommended?itemType=file
GET    /token                      a random unused token (no side effects)
```

### 3.1 List

```bash
scripts/ncloud share list                                   # all shares I created
scripts/ncloud share list --path /Photos --subfiles         # shares on a node (or its children); adds reshares=true and backfills token/url
scripts/ncloud share list --with-me                         # shared with me (status 0 ok / 1 pending / 2 rejected)
scripts/ncloud share list --type link --prefix /filehost/ --json   # client-side filters; --full for complete objects
```

`GET /shares?format=json[&path=/Folder][&reshares=true][&subfiles=true][&shared_with_me=true][&include_tags=true]`;
booleans are the strings `'true'|'false'`. Missing `path` -> 404 "Wrong path"; `subfiles=true` on a file -> 400.

**Pitfall: `?path=` can return link shares with `token: null` and no `url`.** Rule in the source: when
`(your permissions on the node & share permissions) != share permissions`, `token` and `url` are set to null
[src ShareAPIController]. This typically hits link shares on an **external storage mount root** (the mount root
lacks DELETE, e.g. `item_permissions` 23, while the share has 31) and nodes on which you have reduced permissions;
ordinary home folders return token and url. The `token` key is still present, only null, so test
`.token == null`, not `has("token")`. To get the token use `GET /shares/{id}`; `scripts/ncloud share list --path`
already backfills it per share.

### 3.2 One share

```bash
scripts/ncloud share get <share_id>            # compact fields; --full for the whole object
scripts/ncloud call GET /ocs/v2.php/apps/files_sharing/api/v1/shares/<share_id>
# filter: ... | jq '.ocs.data[0]'
```

`data` is an **array** here (`POST`/`PUT` return an object). Unknown id -> 404.

### 3.3 Response fields

Example link share (abridged; values in angle brackets are placeholders):

```json
{"id":"<share_id>","share_type":3,"uid_owner":"alice","displayname_owner":"Alice","permissions":17,"can_edit":true,"can_delete":true,
 "stime":1760000000,"parent":null,"expiration":null,"token":"<token>","url":"https://cloud.example.com/s/<token>","uid_file_owner":"alice",
 "note":"","label":"","path":"/Photos","item_type":"folder","item_permissions":31,"mimetype":"httpd/unix-directory",
 "storage_id":"home::alice","storage":<storage_id>,"item_source":<fileid>,"file_source":<fileid>,"file_target":"/Photos",
 "share_with":null,"share_with_displayname":"(Shared link)","password":null,"send_password_by_talk":false,"mail_send":0,
 "hide_download":0,"attributes":null}
```

| Field | Meaning |
|---|---|
| `id` | **string**; used by PUT/DELETE and the raw API |
| `share_type` | 0 user, 1 group, 3 link, 4 email, 6 federated, 7 circle/Team, 8 guest, 9 federated group, 10 Talk room, 12/13 Deck, 15 ScienceMesh |
| `permissions` | bit sum; link shares are usually 17 or 31 (3.4) |
| `token` / `url` | link shares: `/s/{token}`, `/raw/{token}`, `/public.php/dav/files/{token}/` |
| `file_source` / `item_source` | fileid; matches `/f/{id}`, WebDAV `oc:fileid`, raw `raw-shares/{fileId}`, activity download counts |
| `expiration` | `"Y-m-d H:i:s"` or null; midnight in the owner's timezone |
| `attributes` | **JSON string** or null, e.g. `"[{\"scope\":\"permissions\",\"key\":\"download\",\"value\":false}]"` |
| `password` / `share_with` (link), `hide_download` | the password is stored **hashed** and never returned in clear; `hide_download` is 0/1 |
| other types only | `share_with_displayname_unique`, `share_with_avatar`, `status` (user/group), `password_expiration_time` (mail), `is_trusted_server` (federated) |

### 3.4 Permission bits and "1 becomes 17"

`1 READ`, `2 UPDATE`, `4 CREATE`, `8 DELETE`, `16 SHARE`, `31 ALL`. Common values: `1` read-only (CLI `ro`), `15`
editable (`rw`, the old `publicUpload=true`), `4` file drop (`upload`: upload only, cannot read), `31` everything
(`full`).

Link-share rules (`ShareAPIController::getLinkSharePermissions`):

- Without `permissions`, a link share starts at **1**; user/group shares default to `shareapi_default_permissions`.
- **A link share that includes READ gets SHARE (16) added** when `files_sharing.federation.outgoing` is true and the
  app config `core/shareapi_allow_federation_on_public_shares` is true (its lexicon default). So `1` is stored as
  **17**, `15` as **31**, and `4` (no READ) stays **4**.
- Scripts must **not** assert `permissions == 1`; mask bit 16 first, e.g. shell `(( (perm & ~16) == 1 ))`. A truly
  read-only link (no SHARE) needs an admin to set that app config key to false (4, app config) - an admin decision.
- READ or CREATE is required; UPDATE/DELETE require READ; on a **single file** CREATE/DELETE are dropped silently
  (31 on a file comes back as 17). `publicUpload` on a file -> 400.

### 3.5 Create (parameters from OpenAPI + `createShare` source; `share create --password` observed 200, other writes not tested)

```bash
scripts/ncloud share create /Documents/report.pdf --perm ro --expire 2026-12-31 --label "For the team" --note "Draft" --password "$SHARE_PW"
scripts/ncloud share create /Inbox --perm upload --hide-download --yes      # file drop (anonymous upload) -> needs --yes; --hide-download is a follow-up PUT
scripts/ncloud share create /Projects --type user --with bob --perm rw      # --type user|group|email|remote|circle|team|room|deck; --with required
scripts/ncloud share create /Docs --type email --with someone@example.com --password "$SHARE_PW"
```

- `--password` is the **share password** (a subcommand option, not a login credential). Observed on Nextcloud 33:
  after setting it, public WebDAV with the password answers 207 and without it 401. Passwords on the command line
  show up in shell history and `ps`; generate them with the `password_policy` endpoint (section 2).
- **Public-exposure guard**: for `--type link`, permissions beyond READ|SHARE (`rw`, `upload`, `full`, `15`, `31`,
  `4`, ...) or `--public-upload` require `--yes`: anyone with the URL could write, upload or delete. Ask the user
  first.
- **Rate limit**: share creation is limited per user to **20 creations per 10 minutes** (Nextcloud's user rate
  limit on `createShare`, active while `ratelimit.protection.enabled` is true, the default). Beyond that the server
  answers **HTTP 429 with body `[]`** (no OCS envelope). Batch scripts must pace themselves; do not retry in a loop -
  wait out the window.

The CLI does not wrap `attributes`; use `call` (`-d` is form-encoded and may also carry `password`; or `--json FILE`):

```bash
scripts/ncloud call POST /ocs/v2.php/apps/files_sharing/api/v1/shares -d path=/Projects/site -d shareType=3 -d permissions=1 -d 'label=site preview' -d expireDate=2026-12-31 -d 'attributes=[{"scope":"permissions","key":"download","value":false}]'
curl -sS -u "$AUTH" -H 'OCS-APIRequest: true' "$NC/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json" \
  -d shareType=3 -d path=/Projects/site -d permissions=1 --data-urlencode 'attributes=[{"scope":"permissions","key":"download","value":false}]'
```

| Parameter | Meaning |
|---|---|
| `path` | required, relative to the user root (`/Folder/file.txt`); missing -> 404 |
| `shareType` | required int (3.3); unknown -> 400 |
| `shareWith` | required for types 0/1/4/6/7/10: uid, gid, email, cloud id, circle id (take `value.shareWith` from sharees) |
| `permissions` | int; values with READ gain bit 16 on link shares (3.4) |
| `publicUpload` | `'true'|'false'`, deprecated, equals permissions 15/1; pass `permissions` instead |
| `password` | optional unless `password.enforced`; never returned; form or JSON (section 1) |
| `expireDate` | **`YYYY-MM-DD`**, midnight in the owner's timezone; `''` = no expiry; **malformed -> 404** on create (400 on update) |
| `label` | <= 255 characters (else 400); link name shown in the UI; link/email only |
| `note` | string |
| `attributes` | JSON **string** `[{"scope","key","value"}]`: `permissions/download=false` disables download (view only); `fileRequest/enabled=true` turns a link/mail share into a file request |
| `sendPasswordByTalk` / `sendMail` / `hideDownload` | **not** create parameters; set them with PUT afterwards (`sendPasswordByTalk` -> 403 without Talk) |

The response `data` is the share **object**: keep `id` (PUT/DELETE/raw API) and `token` (`/s/`, `/raw/`, public
WebDAV). With `multiple_links=true` the same path can get further link shares (new id and token). Mail share with
several recipients: `shareWith=''` plus `attributes=[{"scope":"shareWith","key":"emails","value":["a@example.com","b@example.com"]}]`
(documented, UNVERIFIED).

### 3.6 Update (share password via form-encoded `call PUT ... -d password=...` observed 200; other writes not tested)

```bash
scripts/ncloud share update <share_id> --label "Team photos" --hide-download true
scripts/ncloud share update <share_id> --password "$SHARE_PW"                    # share password, not a login credential
scripts/ncloud share update <share_id> --perm rw --expire 2027-01-31 --clear-password --yes   # widens a link share -> --yes
scripts/ncloud share update <share_id> --clear-expire --yes                      # removing the expiry also widens -> --yes
scripts/ncloud call PUT /ocs/v2.php/apps/files_sharing/api/v1/shares/<share_id> -d hideDownload=true
```

**Public-exposure guard** (CLI): on a link share (`share_type` 3), adding permission bits beyond the current ones and
beyond READ|SHARE, `--public-upload true`, `--clear-password` or `--clear-expire` require `--yes`; label, note,
hide-download, setting a password and setting an expiry do not. A raw `curl -X PUT ... -d permissions=15` bypasses
the guard: ask first. Never change existing shares the user did not name (check the site notes for protected
shares).

`PUT /shares/{id}` accepts `permissions`, `password`, `sendPasswordByTalk`, `publicUpload`, `expireDate`, `note`,
`label`, `hideDownload` (`'true'|'false'`), `attributes`, `sendMail`, `token`. **One field per request** is the
portable form, and the CLI sends one PUT per field. Nextcloud 33's controller accepts several fields at once and
answers 400 "Wrong or no update parameter given" only if all are null (source, not tested). `expireDate=''` clears
the expiry, `password=''` clears the password; malformed `expireDate` -> **400**. `permissions` re-applies 3.4.
`token=<custom>` -> **403** while `files_sharing.public.custom_tokens` is false (admin: app config
`core/shareapi_allow_custom_tokens`; format `^[a-z0-9-]+$`, case-insensitive). Response: the updated object;
403 "You are not allowed to edit incoming shares" for shares you received.

### 3.7 Delete (write, not tested)

```bash
scripts/ncloud share delete <share_id> --yes
scripts/ncloud call DELETE /ocs/v2.php/apps/files_sharing/api/v1/shares/<share_id> --yes   # same thing
```

200 deleted, 404 unknown, 403 not allowed. Deletion is final (the token stops working at once; there is no trash
bin); files_sharing_raw drops its raw state for that share too.

### 3.8 Pending and deleted shares

```bash
scripts/ncloud call GET /ocs/v2.php/apps/files_sharing/api/v1/shares/pending     # POST .../shares/pending/{id} accepts
scripts/ncloud call GET /ocs/v2.php/apps/files_sharing/api/v1/deletedshares      # POST .../deletedshares/{id} restores
```

User/group shares become pending only when the recipient enabled "accept shares"; otherwise they appear directly.

### 3.9 Sharees

```bash
scripts/ncloud share sharees bo                       # --item-type file (default) | folder, --limit 20 (server max 25)
scripts/ncloud call GET '/ocs/v2.php/apps/files_sharing/api/v1/sharees?search=bo&itemType=file&perPage=5&shareType[]=0&shareType[]=1'
```

`itemType` (`file`|`folder`) is **required** (missing -> 400 "Missing itemType"). Without `shareType` the server
expands to `0,1,4,6,7`; the CLI sends `lookup=false` (no global lookup server). Response:

```json
{"exact":{"users":[],"groups":[],"remotes":[],"remote_groups":[],"emails":[],"circles":[],"rooms":[]},
 "users":[{"label":"Bob","value":{"shareType":0,"shareWith":"bob"},"shareWithDisplayNameUnique":"bob","status":{"status":"offline"}}],
 "groups":[{"label":"team","value":{"shareType":1,"shareWith":"team"}}],"remotes":[],"emails":[],"circles":[],"lookupEnabled":false}
```

Pass `value.shareType` + `value.shareWith` unchanged to create. An email address shows up under `emails` (type 4);
`user@host` under `remotes` (6). Another picker endpoint:
`GET /ocs/v2.php/core/autocomplete/get?search=bo&itemType=files&shareTypes[]=0&limit=10` ->
`[{id,label,icon,source:"users",status,...}]` (`limit` default 10).

## 4. Provisioning

All under `/ocs/v2.php/cloud/...` (v1 has the same paths; the admin manual uses v1). Mostly admin or group
sub-admin only. v1 failure codes (101...113) become HTTP 400/403/404 in v2 with the same messages. CLI `--yes`
rules: `user create`, `user set --key password`, `user delete`, `group delete`, `app enable`, `app disable` need
`--yes` (after the user asked); the rest does not.

### Users

```bash
scripts/ncloud user list --search al --limit 50     # GET /cloud/users?search=&limit=&offset= -> ["alice",...]
scripts/ncloud user get alice                       # GET /cloud/users/{id} (shape of section 2); unknown -> 404
scripts/ncloud user create carol --password "$NEW_PW" --display-name "Carol" --email carol@example.com --quota "5 GB" --group team --yes   # POST /cloud/users (JSON)
scripts/ncloud user set alice --key quota --value "10 GB"      # PUT /cloud/users/{id}, body {key, value}; --key password needs --yes
scripts/ncloud user disable carol                   # PUT /cloud/users/{id}/disable (enable likewise)
scripts/ncloud user groups alice                    # GET /cloud/users/{id}/groups
scripts/ncloud user addgroup carol --gid team       # POST /cloud/users/{id}/groups
scripts/ncloud user rmgroup carol --gid team        # DELETE /cloud/users/{id}/groups
scripts/ncloud user delete carol --yes              # DELETE /cloud/users/{id}
scripts/ncloud call GET /ocs/v2.php/cloud/users/details   # {"users":{"alice":{...},...}} keyed by id; /recent?limit= and /disabled have the same shape
```

- `POST /cloud/users` body: `userid` (required), `password`, `displayName`, `email`, `groups[]`, `subadmin[]`,
  `quota`, `language`, `manager` -> `data:{"id":"..."}`. Empty `password` plus `email` sends a set-password mail.
  Passwords must satisfy `password_policy`.
- Writable keys for `PUT /cloud/users/{id}`: `displayname email quota password language locale timezone
  first_day_of_week notify_email manager phone address website twitter bluesky fediverse organisation role headline
  biography birthdate pronouns profile_enabled`; `quota` takes `none`, `default`, bytes or `"5 GB"`.
  `additional_mail` uses `PUT /cloud/users/{id}/additional_mail`; `GET /cloud/user/fields` lists the keys you may
  edit yourself.
- `DELETE /cloud/users/{id}/groups` takes `groupid` as a **query** parameter (OpenAPI); also
  `POST|DELETE /cloud/users/{id}/subadmins` (`groupid`), `POST /cloud/users/{id}/welcome` (resend the welcome mail),
  `POST /cloud/users/{id}/wipe`.
- `user create --password` is the new account's password, not a login credential. Writes not tested; for password
  operations occ is an alternative (`OCC.md`).

### Groups

```bash
scripts/ncloud group list --search te       # GET /cloud/groups -> {"groups":["admin","team"]}
scripts/ncloud group members team           # GET /cloud/groups/{gid} -> {"users":[...]}
scripts/ncloud group create newgroup        # POST /cloud/groups -d groupid= [-d displayname=]
scripts/ncloud group delete newgroup --yes  # DELETE /cloud/groups/{gid}
scripts/ncloud call GET /ocs/v2.php/cloud/groups/details   # [{id,displayname,usercount,disabled,canAdd,canRemove}]; PUT /cloud/groups/{gid} -d key=displayname -d value=
```

### Apps

```bash
scripts/ncloud app list --filter enabled         # GET /cloud/apps?filter=enabled|disabled -> {"apps":[...]}
scripts/ncloud app info files_sharing_raw        # GET /cloud/apps/{appid} -> info.xml as JSON (id, name, version, ...)
scripts/ncloud app enable notes --yes            # POST /cloud/apps/{appid} (admin, not tested); same as occ app:enable
scripts/ncloud app disable notes --yes           # DELETE /cloud/apps/{appid}
```

On Nextcloud AIO do not toggle AIO-managed companion apps this way (`OCC.md`, section 5).

### App config (instead of `occ config:app:*`, no host access needed)

```bash
scripts/ncloud call GET /ocs/v2.php/apps/provisioning_api/api/v1/config/apps/files_sharing_raw   # {"data":["enabled","installed_version","types",...]}
scripts/ncloud call GET /ocs/v2.php/apps/provisioning_api/api/v1/config/apps/core/shareapi_allow_federation_on_public_shares   # {"data":""} = unset -> default true (?defaultValue= available)
scripts/ncloud call POST /ocs/v2.php/apps/provisioning_api/api/v1/config/apps/core/shareapi_allow_custom_tokens -d value=yes   # write, not tested; admin decision
scripts/ncloud call DELETE /ocs/v2.php/apps/provisioning_api/api/v1/config/apps/<app>/<key> --yes
```

Write restrictions (`AppConfigController`): `installed_version`, `enabled`, `types` of any app -> 403 "The given
key can not be set"; in `core`, `encryption_enabled` (unless the value is `yes`), `public_*` and `remote_*` are
refused too; `files/default_quota=none` is refused while `allow_unlimited_quota=0`. **`core/shareapi_*` is not
blocked** (share policy can be changed). 403 "App is not allowed" means the caller is not an admin and has no
delegation. User preferences: `POST|DELETE .../config/users/{appId}[/{key}]` (`configValue=`). System config
(`config.php`) has no OCS interface; occ only.

## 5. Unified search

Nextcloud has no client documentation for these endpoints; this follows `core/openapi-full.json` and
`UnifiedSearchController`.

```bash
scripts/ncloud providers                            # GET /ocs/v2.php/search/providers -> [{id,appId,name,order,filters,...}]
scripts/ncloud usearch invoice --provider files --limit 10 --json
scripts/ncloud usearch invoice                      # all default providers that exist on the server
scripts/ncloud call GET '/ocs/v2.php/search/providers/files/search?term=Readme&limit=3&path=/Documents&mime=text/markdown&since=2026-01-01'
scripts/ncloud call GET '/ocs/v2.php/search/providers/files/search?term=Readme&limit=3&cursor=3'   # next page
```

`usearch` without `--provider` queries, among the providers present: `files fulltextsearch contacts calendar
search-deck-card-board search-deck-comment settings`. **`mail` is left out on purpose**: it errors (HTTP 500)
until the user has a mail account configured; query it explicitly with `--provider mail`.

Providers observed on Nextcloud 33 (the list depends on installed apps; check `scripts/ncloud providers`):

| id | app | filters |
|---|---|---|
| `fulltextsearch` | full-text index (e.g. Elasticsearch) | term, since, until |
| `files` | filecache name substring | term, since, until, person, min-size, max-size, mime, type, path, is-favorite, title-only |
| `systemtags` / `circles` / `comments` / `settings` / `settings_apps` | - | term |
| `search-deck-card-board` / `search-deck-comment` | deck | term |
| `mail` | mail | term, since, until, person (500 until a mail account exists) |
| `contacts` | dav | term, since, until, person, title-only |
| `calendar` | dav | term, person, since, until |

`GET /search/providers/{id}/search?term=&limit=&cursor=&sortOrder=&from=` plus any name from that provider's
`filters` as a query parameter (`mime` alone also works). `limit` defaults to 5, capped by
`unified-search.max-results-per-request` (default 25). Response:

```json
{"name":"Files","isPaginated":true,"cursor":3,
 "entries":[{"title":"Readme.md","subline":"in Documents/...","resourceUrl":"https://cloud.example.com/f/<fileid>",
             "thumbnailUrl":".../core/preview?x=32&y=32&fileId=<fileid>","icon":"...","rounded":false,
             "attributes":{"fileId":"<fileid>","path":"/Documents/.../Readme.md"}}]}
```

Pass `cursor` back for the next page and stop when `entries` is empty (cursor may be int or string depending on the
provider). `fulltextsearch` entries: `title` is the matching excerpt (prefixed `(files)`), `subline` the path,
`resourceUrl` a **relative** `/apps/files/?dir=...`, `attributes: []`. Errors: no valid filter at all -> 400;
unknown provider -> 500/996; **`title-only=true` with `files` returns 500 on Nextcloud 33** (do not use). For exact
path/property queries use WebDAV `SEARCH` (`API_WEBDAV.md`, `scripts/ncloud search`).

## 6. User status

Base `/ocs/v2.php/apps/user_status/api/v1`; not wrapped by the CLI, use `call`.

```bash
scripts/ncloud call GET /ocs/v2.php/apps/user_status/api/v1/user_status            # own: {userId,message,messageId,messageIsPredefined,icon,clearAt,status,statusIsUserDefined}
scripts/ncloud call GET '/ocs/v2.php/apps/user_status/api/v1/statuses?limit=5&offset=0'   # [{userId,message,icon,clearAt,status}]; /statuses/{uid}: 404 if none
scripts/ncloud call GET /ocs/v2.php/apps/user_status/api/v1/predefined_statuses    # meeting commuting be-right-back remote-work sick-leave vacationing
scripts/ncloud call PUT /ocs/v2.php/apps/user_status/api/v1/user_status/status -d statusType=dnd   # online|away|dnd|busy|invisible|offline
scripts/ncloud call PUT /ocs/v2.php/apps/user_status/api/v1/user_status/message/custom -d 'statusIcon=<one emoji>' -d message=deploying -d clearAt=1800000000
scripts/ncloud call PUT /ocs/v2.php/apps/user_status/api/v1/user_status/message/predefined -d messageId=meeting
```

`DELETE .../user_status/message` clears the message (with `--yes` via `call`). Writes not tested; 400 means the
icon is not a single emoji, the message is too long, or `clearAt` is in the past. Notification responses also carry
your status in the `X-Nextcloud-User-Status` header.

## 7. Notifications

Base `/ocs/v2.php/apps/notifications/api/v2` (`v1` routes exist too).

```bash
scripts/ncloud notifications list              # GET /notifications; data [] = nothing unread
scripts/ncloud notifications delete 123        # DELETE /notifications/{id}
scripts/ncloud notifications clear --yes       # DELETE /notifications
curl -sS -u "$AUTH" -H 'OCS-APIRequest: true' -H 'If-None-Match: "<etag>"' "$NC/ocs/v2.php/apps/notifications/api/v2/notifications?format=json"   # unchanged -> 304, empty body
```

Notification object: `notification_id` (int), `app`, `user`, `datetime` (ISO 8601), `object_type`, `object_id`,
`subject`, `subjectRich`, `subjectRichParameters`, `message`, `messageRich`, `messageRichParameters`, `link`,
`icon`, `shouldNotify`, `actions:[{label,link,type:GET|POST|DELETE|PUT|WEB,primary}]` - an action is executed by
calling `link` with method `type` (same auth and header). `GET /notifications/{id}` (404 = gone),
`POST /notifications/exists -d ids[]=1 -d ids[]=2` (<= 200 ids). 204 means no app can generate notifications (poll
hourly instead).

**Notify a person** (admin; not tested): `POST /ocs/v2.php/apps/notifications/api/v3/admin_notifications/{userId}`
with `subject` (<= 255), `message`, optional `subjectParameters` / `messageParameters` -> notification id; the v2
variant takes `shortMessage` / `longMessage`. occ equivalent: `notification:generate <userId> "<short>" -l "<long>"`.

```bash
scripts/ncloud call POST /ocs/v2.php/apps/notifications/api/v3/admin_notifications/alice -d 'subject=Deploy finished' -d 'message=site preview updated'
```

## 8. Activity

Base `/ocs/v2.php/apps/activity/api/v2/activity` (activity app 6.0, shipped with Nextcloud 33).

```bash
scripts/ncloud activity --limit 20                                     # GET /activity?limit=
scripts/ncloud activity --filter files --limit 20                      # GET /activity/{filter}
scripts/ncloud activity --filter files --object-type files --object-id <fileid>   # one fileid (needs a filter path)
scripts/ncloud activity --since <activity_id> --limit 50               # incremental
scripts/ncloud call GET /ocs/v2.php/apps/activity/api/v2/activity/filters   # e.g. all self by files files_favorites files_sharing security calendar contacts comments deck
```

Response `data` = `[{activity_id, app, type ("file_created", "file_deleted", "shared", ...), user, subject
(localized), subject_rich:[template,{file:{type,id,name,path,link}}], message, message_rich, object_type:"files",
object_id:<fileid>, object_name:"/path", objects:{fileid:path}, link, icon, datetime}]`. Headers:
`Link: <...?since=N&limit=...&sort=desc>; rel="next"`, `X-Activity-First-Known`, `X-Activity-Last-Given`. Polling:
remember `X-Activity-Last-Given`, next time `since=<it>&sort=asc`.

**Parameters supported by activity 6.0**: `since` (activity id), `limit` (default 50), `sort=asc|desc`,
`previews=true`, `object_type` + `object_id` (both, and only under `/activity/{filter}`; otherwise silently cleared).
Newer parameters (`search`, `from`, `to`, `actor`, `/histogram`) are **silently ignored** on Nextcloud 33 (observed:
an unknown `actor` still returns 200 with data); filter client-side on `user` / `datetime` / `object_name`. Status
codes: 200; 204 the user disabled all activity types; 304 empty result or ETag hit; 403 `since` belongs to someone
else; 404 unknown filter (`public_links` is a type, not a filter). No 400.

**Public-link download counts**: `GET /activity/downloads/count?object_type=files&object_id=<file_source>` ->
`{"total":0,"last30d":0}` (missing parameters -> 400 with an empty message). Download events are app
`files_sharing`, type `public_links`, subject `public_shared_file_downloaded` / `public_shared_folder_downloaded`,
visible under the `files_sharing` or `all` filter (subject to the owner's activity settings). Downloads via
`/raw/{token}` go through files_sharing_raw's own streaming and are most likely **not** counted (source inference,
UNVERIFIED); for raw hit counts use reverse-proxy logs or a `BeforeNodeReadEvent` webhook.

```bash
scripts/ncloud call GET '/ocs/v2.php/apps/activity/api/v2/activity/downloads/count?object_type=files&object_id=<fileid>' -i
```

## 9. Webhooks (webhook_listeners)

All routes are admin-only (otherwise 403).

```
GET    /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks[?uri=<filter>]   list
POST   /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks                  create
GET    /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks/{id}             one (unknown -> 404)
POST   /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks/{id}             update (POST, not PUT; full replacement, resend required fields)
DELETE /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks/{id}             delete -> data: true|false
```

```bash
scripts/ncloud webhook list
scripts/ncloud webhook create --uri https://hooks.example.com/nextcloud --event 'OCP\Files\Events\Node\NodeWrittenEvent' --method POST --user-filter alice --auth-method header --auth-data '{"Authorization":"Bearer <secret>"}' --filter '{"event.node.path":"/^\\/alice\\/files\\/Projects\\//"}' --yes
scripts/ncloud webhook delete <webhook_id> --yes
```

Registering a webhook sends events to an external URI, so `create` (and `delete`) need `--yes`. The CLI parses
`--filter` / `--headers` / `--auth-data` with `json.loads` before putting them into the JSON body (invalid JSON is
an error). Complex payloads also work with `call --json`:

```bash
cat > hook.json <<'EOF'
{"httpMethod":"POST","uri":"https://hooks.example.com/nextcloud","event":"OCP\\Files\\Events\\Node\\NodeWrittenEvent",
 "eventFilter":{"event.node.path":"/^\\/alice\\/files\\/Projects\\//"},"userIdFilter":"","headers":{"X-Source":"nextcloud"},
 "authMethod":"header","authData":{"Authorization":"Bearer <shared-secret>"}}
EOF
scripts/ncloud call POST /ocs/v2.php/apps/webhook_listeners/api/v1/webhooks --json hook.json
```

- Required: `httpMethod`, `uri`, `event`; `event` must be an existing class implementing `IWebhookCompatibleEvent`
  (else 400). `eventFilter` is a MongoDB-style query (`{}` = everything); `userIdFilter` keeps only events triggered
  by that uid; `headers` adds request headers; `authMethod` `none|header`; with `header`, `authData` is merged into
  the request headers (stored encrypted); `tokenNeeded={"user_ids":[...],"user_roles":["owner"|"trigger"]}` embeds a
  1-hour temporary app token in the payload (Nextcloud 33). Response `data` = `{id (string), userId, httpMethod,
  uri, event, eventFilter, userIdFilter, headers, authMethod, authData, tokenNeeded}`.
- Event classes (depend on installed apps): `OCP\Files\Events\Node\{Before,}Node{Created,Touched,Written,Read,Deleted,Copied,Restored,Renamed}Event`
  (Read only as Before), `OCP\Calendar\Events\CalendarObject{Created,Updated,Deleted,Moved,MovedToTrash,Restored}Event`,
  `OCP\SystemTag\{TagAssignedEvent,TagUnassignedEvent}`, `OCA\Mail\Events\{NewMessageReceived,MessageSent,MessageFlagged,MessageDeleted}Event`;
  Forms and Tables add their own.
- Filter syntax: `{"user.uid":"bob"}`, `{"event.node.path":"/^\\/alice\\/files\\/Special\\//"}` (regex as a `/.../`
  string, slashes escaped); operators `$e $ne $gt $gte $lt $lte $in $nin $and $or $not $nor`.
- Payload (JSON POSTed to `uri`):

```json
{"event":{"class":"OCP\\Files\\Events\\Node\\NodeWrittenEvent","node":{"id":<fileid>,"path":"/alice/files/Projects/site/index.html"}},
 "user":{"uid":"alice","displayName":"Alice"},"time":1760000000,"authentication":{}}
```

  Rename/copy events carry `source`/`target` instead of `node`; `Before*Created` may lack `id`. `path` is the
  **internal path** `/<uid>/files/<relative path>`, so filters must include that prefix. For public-link uploads
  (file drop) `user` is `null`: `userIdFilter` cannot catch anonymous uploads.
- Delivery is a **background job**: with `backgroundjobs_mode=cron` every 5 minutes (the AIO default) expect up to
  ~5 minutes of delay; for immediate delivery an admin can loop
  `occ background-job:worker -t 60 'OCA\WebhookListeners\BackgroundJobs\WebhookCall'`.
- **Reachability**: requests leave from the Nextcloud server (on Docker: from the Nextcloud container, where
  `localhost` is the container itself). Private targets (RFC 1918, CGNAT/VPN ranges) are refused with "violates
  local access rules" unless `allow_local_remote_servers=true` (Nextcloud AIO sets it at every start). TLS is
  verified with Nextcloud's own CA bundle, not the host's: private CAs need
  `occ security:certificates:import <cert.pem>`, or plain `http://` inside a trusted LAN.
- occ only has `webhook_listeners:list [--output=json]`; creation and deletion are OCS-only.

## 10. files_sharing_raw (non-OCS, no envelope)

Details (CSP presets, caching, `/raw/u/`) are in the filehost skill's `references/RAW_FILESERVER.md`; this is the
endpoint map. Needs Basic auth **and** `OCS-APIRequest: true` (the Bearer shortcut does not apply). Verified with
files_sharing_raw 0.7.3.

```bash
scripts/ncloud raw get <share_id>                  # GET /apps/files_sharing_raw/api/v1/raw-share/{shareId}
scripts/ncloud raw list /Projects/site             # GET /apps/files_sharing_raw/api/v1/raw-shares/{fileId} (fileId = the share's file_source)
scripts/ncloud raw enable <share_id> --preset site --raw-only   # POST raw-share/{shareId} enabled=1 rawOnly=1 csp=...
scripts/ncloud raw disable <share_id>
scripts/ncloud raw url <share_id> index.html       # raw URL (+ optional sub path)
scripts/ncloud call GET /apps/files_sharing_raw/api/v1/raw-share/<share_id>
```

| Endpoint | Response |
|---|---|
| `GET raw-share/{shareId}` | `{"shareId":<share_id>,"enabled":false,"csp":null,"rawOnly":false,"canEditCsp":true,"token":"<token>","rawUrl":"https://cloud.example.com/raw/<token>"}` |
| `GET raw-shares/{fileId}` | `{"fileId":<fileid>,"shares":[{"shareId":<share_id>,"token":"<token>","enabled":false,"rawUrl":"..."}]}` |
| `POST raw-share/{shareId}` body `enabled=1|0`, `rawOnly=1|0`, `csp=` | link shares (type 3) only, share owner only; `csp` takes effect only for members of `csp_editor_group` (default admin) |
| `GET raw-public-url?token=` | **500 in 0.7.3** (the route points at a missing controller); do not use |
| `GET /raw/{token}[/{path}]`, `GET /raw/u/{user}/{path}` | not enabled -> 404 text/plain; `/raw/{token}/` (trailing slash) -> 404 |

- A raw link **does not check the share password** (the expiry still applies); deleting the share removes the raw
  state.
- `raw enable` needs no `--yes` but prints a stderr warning: the content becomes fully public and the share password
  no longer protects it. Never enable raw for private content.
- **rawOnly retention**: the app's POST treats a missing `rawOnly` as false, and GET reports `rawOnly: false` while
  the share is disabled. So `raw enable` without `--raw-only` / `--no-raw-only` keeps the current rawOnly only if the
  share is **currently enabled**; after `raw disable`, a later `raw enable` comes back with rawOnly=false unless
  `--raw-only` is passed again. The CSP survives disable/enable (an absent `csp` keeps the stored value;
  `csp=''` clears it). Observed on 0.7.3: `raw enable --raw-only`, `raw disable`, `raw enable` gives rawOnly=false
  with the CSP intact.

## 11. App passwords

- **`GET /ocs/v2.php/core/getapppassword`** (a GET) with the **login password** in Basic auth; the `User-Agent`
  becomes the token name -> `data:{"apppassword":"<72 characters>"}`. Called with an app password it returns
  **403 "Password confirmation is required"** and creates nothing; decide on the 403. Works only for accounts
  without 2FA; with 2FA use Login Flow v2. `getapppassword-onetime` needs a one-time-token session (not for agents).
- Manage the token in use (core endpoints, not tested): `DELETE /ocs/v2.php/core/apppassword` (revoke the current
  token), `POST /ocs/v2.php/core/apppassword/rotate` (new token, old one invalid),
  `PUT /ocs/v2.php/core/apppassword/confirm` (body `password` = login password).
- **occ (on the server, no login password needed)**:

```bash
scripts/ncloud app-password agent-x --yes           # = occ user:auth-tokens:add <NEXTCLOUD_USER> --name agent-x -n; token printed once on stdout
scripts/ncloud app-password agent-x --uid alice --json --yes
scripts/ncloud occ -- user:auth-tokens:list alice --output=json   # [{id,name,lastActivity,type,scope}]
scripts/ncloud occ --yes -- user:auth-tokens:delete alice <token_id>   # revoke
```

  A token minted this way (no login password) works for WebDAV and OCS (observed on Nextcloud 33); only operations
  that need the login password (e.g. server-side encryption keys) fail. For a full token run
  `NC_PASS=<login password> ... occ user:auth-tokens:add <uid> --name <name> --password-from-env` (local docker mode
  forwards `NC_PASS`; see `OCC.md` 1.1-1.2). Minting a credential always needs the user's explicit request.
- **Login Flow v2** (interactive, works with 2FA): `POST $NC/index.php/login/v2` (no auth, no OCS header; send a
  `User-Agent`) -> `{"poll":{"token","endpoint"},"login":"https://.../login/v2/flow/<flow>"}`; a human opens `login`
  and approves; `POST <poll.endpoint> -d token=<poll token>` returns 404 until then and, once,
  `{"server","loginName","appPassword"}` (valid 20 minutes, delivered once). Not tested (creates server state).
- Store new tokens only in the 0600 env file (`scripts/ncloud config init --url ... --user ... --app-password ...`,
  or `--force` to replace); never in chat, logs or git.
- **Brute force**: each failed login from an IP delays later attempts by 0.1 s x 2^n (n = failures in the last
  12 h, capped at 25 s); more than 10 failures in 12 h **and** more than 10 in the last 30 min gives 429. Wrong or
  missing share passwords on public links count too. Agents behind the same reverse proxy or docker host may share
  one source address and one bucket. **Never retry a 401**; unlocking: `TROUBLESHOOTING.md` and `OCC.md` 2.5.

## 12. Decision rules

- **OCS (this file)**: create / read / update / delete shares (neither occ nor WebDAV can), sharee and user lookups,
  capabilities, unified search, user status, notifications (including `admin_notifications` to message a person),
  activity and download counts, webhook registration, provisioning, app config (including `core/shareapi_*`), raw
  link switches. Works anywhere with HTTPS and an app password; actions are attributed to that token (and to the
  admin audit log if enabled).
- **WebDAV** (`API_WEBDAV.md`): bytes and properties - upload/download, MKCOL/MOVE/COPY/DELETE, PROPFIND, fileid,
  tags/favorites, chunked upload, `SEARCH`/`REPORT`. OCS does not move file content.
- **occ** (`OCC.md`): what has no HTTP API - app passwords without the login password, `config:system:set`
  (`raw_csp`, `allow_local_remote_servers`, ...), importing CA certificates, force-enabling apps, maintenance mode,
  the full-text index, `files:scan` after direct disk writes, logs; or when admin ground truth is needed
  (`twofactorauth:state`, unset vs default), or an HTTP route is broken (`raw-public-url` 500). Slower and needs host
  access; prefer OCS when it can do the job.
- **MCP** (`MCP.md`): load on demand only for multi-step app semantics (calendar / contacts / Deck / Mail) that
  API/occ cannot finish in three steps; scripted, unattended work always uses the OCS/WebDAV calls in this file.
