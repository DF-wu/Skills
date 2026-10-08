# SITE_NOTES.md - private site notes for one Nextcloud server

This skill is generic: it knows how Nextcloud behaves, not how *your* server is laid out. Facts that only hold for one installation (which mount is fragile, which share is load-bearing, which account belongs to a family member) live in a private notes file that agents read before acting. Nothing instance-specific belongs in the skill itself.

## Where it lives

| Item | Value |
|---|---|
| Path | `$NEXTCLOUD_USE_NOTES`, else `NOTES.md` in the same directory as the env file in use (typically `~/.config/nextcloud-use/NOTES.md`) |
| Format | Plain Markdown, written for an agent to read |
| Mode | `0600`, owned by the user that runs the CLI |
| Version control | **Never commit it.** It describes your infrastructure; keep it next to the env file, outside any repository |
| Secrets | **None.** Passwords, app passwords, base64 credentials and share tokens stay in the env file. The notes get printed into agent transcripts |

The CLI wires it in:

```bash
scripts/ncloud doctor          # row "notes": "present, read it before acting" or "none (<path>)"
scripts/ncloud config show     # "notes_file": "<path>", "notes_present": true|false
scripts/ncloud config notes    # prints the file (stderr hint when it does not exist)
```

## Why agents must read it first

- Some hazards cannot be detected through the API. Example: an external storage whose backing disk is not mounted looks like an empty folder; `files_external:verify` may still say `ok`, and a broad `files:scan` then wipes its filecache rows. Only the operator knows the disk is missing.
- Some objects look unused but are not: a long-lived public share embedded in other sites, a service account used by a backup job.
- Network layout changes how failures spread: if every agent reaches Nextcloud through the same reverse proxy, they share one brute-force bucket.

Rules for agents:

1. Run `scripts/ncloud doctor`; if `notes` is `present`, run `scripts/ncloud config notes` and follow it for the whole session.
2. When the notes are stricter than this skill, the notes win. When the user asks for something the notes forbid, stop, quote the note and ask; do not proceed on an assumption.
3. Do not edit the notes unless the user asks. Suggest additions in the reply instead (for example after discovering a new quirk).
4. Never copy note contents into commits, issues, public pages or shared documents.

## What belongs there

| Section | Examples of what to record |
|---|---|
| Deployment layout | Install type (AIO, docker image, bare metal) and version; container names; occ transport (`local`, `ssh` host alias, custom `NEXTCLOUD_OCC_COMMAND`); where the data directory and external storages are backed (local disk, NFS hard mount that hangs when the NAS is down); reverse proxy in front |
| Folders and mounts never to scan | External storages or team folders whose backend may be missing, with mount id and occ path (`/<user>/files/<folder>`); which subtrees are safe to scan explicitly |
| Shares never to touch | Share id, path and why (embedded in a website, given to a client, used by automation) |
| Accounts not to modify | Admin accounts, family members, service accounts, accounts managed by LDAP/SSO |
| Reverse-proxy and brute-force quirks | The address Nextcloud records for agents (for example all appear as `127.0.0.1`), brute-force whitelist entries, rate-limit surprises |
| App quirks | Disabled or missing apps, providers that fail (unified search `mail` without a mail account returns 500), settings such as custom share tokens being off, known app bugs on this version |
| Operations calendar | Backup / update windows (AIO stops containers), planned maintenance |
| Conventions | Scratch folder for write tests, filehost root folder, share label conventions, MCP sidecar network and URL as seen from agent containers |
| Contacts | Who to ask before risky changes |

Keep each entry short, state the reason, and date it. Remove entries that are no longer true: stale notes make agents refuse safe work.

## Creating the file

```bash
scripts/ncloud config show        # read "notes_file" for the exact path
( umask 077 && touch ~/.config/nextcloud-use/NOTES.md )   # adjust to the reported path
chmod 600 ~/.config/nextcloud-use/NOTES.md
```

Then edit it with any editor and check that `scripts/ncloud doctor` reports `notes ... present`.

## Template

Placeholders in `<angle brackets>`; example values are fictitious.

```markdown
# Nextcloud site notes (private; chmod 600; never commit; no secrets)

Last reviewed: <YYYY-MM-DD> by <operator>

## Deployment
- Nextcloud <33> (<AIO>) at https://cloud.example.com behind <a reverse proxy> on host `nc-host`.
- occ: over ssh (`NEXTCLOUD_OCC_SSH_HOST=nc-host`), container `nextcloud-aio-nextcloud`.
- Data directory on an NFS hard mount: when the NAS is down, file operations and occ hang instead of failing.

## Never scan
- External storage "<Archive>" (mount id <mount_id>, occ path `/alice/files/Archive`): its backing disk is
  often unmounted. Never run `files:scan alice`, `files:scan --all`, `files:scan --unscanned`,
  or `files_external:scan <mount_id>`. Safe: `files:scan --path=/alice/files/Projects/<subtree>` with consent.

## Shares never to touch
| share id | path | why |
|---|---|---|
| <share_id> | /Public | long-lived public folder linked from <a website> |
| <share_id> | /Clients/<name> | client upload drop; expires <YYYY-MM-DD> |

## Accounts not to modify
- `admin` (break-glass), `bob` (family member), `svc-backup` (backup job).

## Network and brute force
- All agents on the docker host appear to Nextcloud as 127.0.0.1 (proxy in trusted_proxies):
  one bad password throttles every agent. Never retry a 401.

## App quirks
- Mail app has no account configured: unified search provider `mail` returns 500.
- Custom share tokens are disabled.

## Operations
- AIO daily backup at <03:00>: containers are stopped for ~<10> minutes.

## Conventions
- Write tests go to `/Scratch/_agent-*`; delete them afterwards, including the trash.
- MCP sidecar joins docker network `agents`; agent containers use http://nextcloud-mcp:8000/mcp.
```
