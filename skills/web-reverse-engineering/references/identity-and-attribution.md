# Identity, Attribution, and Operational Separation

Two audiences, one document. Both need the same mechanics, for different reasons:

- **Authorized engagements** — penetration tests, bug bounties, incident response,
  academic research. You need engagement data separated from personal data, and you
  need to not accidentally attribute your client's activity to yourself.
- **Personal privacy** — keeping routine research and browsing from being correlated
  into a profile.

The mechanics are identical. What differs is the justification, and the justification
matters: this document is about **compartmentalization for legitimate work and personal
privacy**, not about evading accountability for unauthorized activity. If you cannot
state who authorized your access, no amount of identity separation changes that.

---

## 1. The four layers

Identity separation fails at the weakest layer. A perfect browser profile on a network
that also carries your personal traffic is not separated.

| Layer | What it means | Minimum viable |
|---|---|---|
| **Identity** | Which persona you are acting as | Separate accounts, emails, credentials |
| **Machine** | Which device or environment the work happens in | Separate browser profile, VM, or device |
| **Network** | Which egress the traffic uses | Separate proxy/egress per persona |
| **Behaviour** | What patterns you leave | Consistent schedule, writing style, no cross-login |

Most failures are behavioural, not technical. The typical leak is logging into the
personal account in the engagement browser "just for a second".

## 2. Identity layer

One persona, one purpose. Rules:

- **One email per persona.** Never shared, never reused, never forwarded between.
- **One credential set per persona.** Never reuse a password. A single password that
  appears in two personas collapses the separation — credential stuffing and breach
  correlation both work on exactly that.
- **Age the persona.** An account created five minutes ago and used immediately is
  itself a signal. If the persona needs to look plausible, it needs history.
- **Do not reuse profile artefacts.** Same avatar, same bio phrasing, same username
  stem, same recovery phone → linkable.
- **Track personas deliberately.** A password manager entry (KeePassXC, Bitwarden) with
  creation date, purpose, and which engagements it is used for. Undocumented personas
  get reused by accident.

Pseudonymous research accounts frequently violate a platform's terms of service even
when the underlying activity is entirely lawful. That is a ToS issue, not a criminal
one — see [`compliance-and-scope.md`](compliance-and-scope.md) §4 — but decide
deliberately rather than discovering it later.

## 3. Machine layer

Three options, in increasing order of isolation:

**Separate browser profile.** Cheapest, and sufficient for most work. Chromium and
Firefox both support multiple profiles with fully separate cookie jars, storage, cache,
extensions, and history. The gaps that remain:

- Shared system fonts — a real correlation point across profiles on the same machine
- Shared clipboard
- Same canvas/WebGL output, because the GPU and driver are the same
- Same OS build, same installed software

**Virtual machine.** A genuine isolation boundary for state: cookies, local storage,
autofill, filesystem. What it does **not** do:

- It does not spoof your hardware fingerprint. A fresh Windows or Linux install has a
  predictable, near-identical rendering signature — and every VM built from the same
  base image shares it, which is worse than a unique fingerprint, not better.
- It does not touch behavioural signals at all.
- A VM running on your personal machine still shares the physical GPU, the host
  timezone, and often the host network.

**Separate physical device.** The most reliable boundary, and the one most often
skipped because it is inconvenient. Where the threat model justifies it — high-value
engagements, hostile targets — it is the only layer that actually holds.

Whichever you pick, the rule is the same: **the engagement environment never sees a
personal credential, and the personal environment never sees engagement data.**

## 4. Network layer

- **Egress must match the persona's claimed geography.** A profile claiming `zh-CN`,
  `Asia/Shanghai`, and a Windows build, exiting from a Frankfurt datacenter, is
  incoherent. Incoherence is more detectable than any single unusual value.
- **One egress per persona at a time.** Two personas from the same IP simultaneously
  links them regardless of what the browser claims.
- **Datacenter ASNs are a weak signal** on defended targets; residential or ISP egress
  is the norm for anything that matters. Mobile carrier egress is stronger still.
- **Do not put personal traffic through the engagement egress**, or the reverse. This is
  the most common accidental linkage.

For the proxy mechanics themselves — pools, health scoring, rotation — see
[`proxy-strategies.md`](proxy-strategies.md) and
[`proxy-rotation-strategies.md`](proxy-rotation-strategies.md).

## 5. Behaviour layer

The layer no tool fixes.

- **Timing.** Two accounts active on the same schedule, with the same gaps, correlate.
  Vary it, or accept that the correlation exists.
- **Writing style.** Stylometric analysis links pseudonymous and real-identity writing
  with more accuracy than most people expect. If the persona writes, it needs its own
  voice — and reusing your own phrasings across personas is a direct link.
- **Interaction graph.** Following the same accounts, liking the same content, joining
  the same servers.
- **Notification side channels.** "Viewed by" lists, read receipts, story views, profile
  visit notifications, LinkedIn's viewer list. Researching a subject from an account
  they can see tips them off. Browse logged-out or from an unlinked persona for anything
  the subject controls.
- **Never click a subject-controlled link from your real browser.** It is logged, and it
  may carry a fingerprinting payload.

## 6. Fingerprint coherence

For any persona that presents a browser identity, the values must be internally
consistent. A detection system does not need one perfect signal; it needs one
contradiction.

Cross-checks that actually get performed:

| Check | Contradiction that exposes it |
|---|---|
| UA vs TLS fingerprint | UA says Windows Chrome, ClientHello says macOS Chrome or a Python stack |
| UA vs `navigator.platform` | Both must agree on the OS |
| Screen vs `devicePixelRatio` vs UA | 4K screen with DPR 1 and a mobile UA |
| Timezone vs IP geolocation | `Asia/Shanghai` from a US ASN |
| `Accept-Language` vs `navigator.languages` | Different sets, or an order that no real browser produces |
| Font list vs claimed OS | Windows font names on a claimed macOS profile |
| WebGL renderer vs claimed OS | `Apple M2` renderer string on a Windows profile |
| Browser version vs engine version | UA claims Chrome 150 but the engine is 120 |

The engineering consequence: **do not hand-tune these values.** Derive them from a real
capture. A profile that was recorded from an actual machine is coherent by construction;
one assembled from plausible-looking strings is coherent only until someone checks.

```bash
# Record a coherent profile from a real browser, then replay it.
# See scripts/fingerprint_probe.py to verify what your client actually sends.
python scripts/fingerprint_probe.py --json > my_client.json
```

`impersonate="chrome"` in curl_cffi is a concrete example of the trap: it resolves to the
newest build and reports a **macOS** User-Agent. Overriding that UA with a Windows string
produces exactly the UA-vs-TLS contradiction above. See
[`http-clients.md`](http-clients.md) for the measured per-version table.

## 7. Antidetect browsers: what they do and do not solve

Commercial "antidetect" browsers (Multilogin, AdsPower, GoLogin, Kameleo, BitBrowser,
and others) sell profile isolation plus fingerprint control. An honest assessment:

**They do solve:**

- Profile isolation — separate cookies, storage, cache per profile
- Consistent per-profile fingerprint generation, including canvas noise injected at the
  rendering layer rather than via JS overrides (which is the meaningful difference: a JS
  override is detectable, a rendering-layer change is much harder to detect)
- WebGL vendor/renderer string consistency
- Audio processing simulation per profile

**They do not solve:**

- **Network layer.** Fingerprint control does nothing if five profiles exit from one IP.
  The vendors say this themselves; the marketing page usually omits it.
- **Behaviour.** No antidetect browser models human behaviour.
- **Account graph.** If the accounts interact with each other, the graph links them.
- **Consistency across a batch.** This is the classic self-inflicted wound: if every
  profile reports the same rare font list, you have built a pattern for the platform to
  match against. Uniqueness per profile is not enough — the *distribution* across
  profiles must look like a real population.

The general caution: no tool in this category is undetectable or un-bannable, and any
vendor that frames it that way is selling something other than accuracy. Treat them as
convenience layers over the four-layer model, not as a substitute for it.

## 8. Threat-model worksheet

Before setting up anything, answer these. If you cannot, you do not yet have a threat
model, and the infrastructure choices will be arbitrary.

1. **Who is the adversary?** A platform's abuse team, a client's SOC, a hostile target,
   a state actor, a competitor?
2. **What can they see?** Network metadata only? Full TLS? Application logs? Legal
   process?
3. **What links me to the work?** Payment method, phone number, IP, writing style,
   schedule, hardware, a mistake?
4. **What is the cost of linkage?** Embarrassment, contract loss, civil claim, criminal
   exposure?
5. **What is the cost of over-separation?** Time, money, friction, abandoned work?
6. **Who authorized this?** If the answer is not a person or a document, stop here.

Answer 3 and 6 honestly. Almost every real-world failure traces to one of them.

## 9. Anti-patterns

Collected from what actually goes wrong:

- Logging into a personal account from the engagement browser, even once, even briefly.
- Reusing one password across personas.
- Reusing a phone number for verification across personas — phone numbers are the single
  strongest linkage in most account systems.
- Running two personas through one egress at the same time.
- Building all VM profiles from one base image and shipping the identical fingerprint to
  every target.
- Overriding the User-Agent without re-checking the TLS fingerprint.
- Keeping engagement data in a personal cloud account.
- Documenting personas nowhere, then reusing one by accident six months later.
- Assuming a VM or an antidetect browser is a substitute for a coherent network layer.
- Treating separation as a technical problem when the leak is behavioural.

## 10. Relationship to the rest of this skill

This document covers *who you appear to be*. It does not cover *what you send* — the
protocol-level fingerprint, which is a separate problem covered in
[`tls-http-fingerprinting.md`](tls-http-fingerprinting.md) and
[`http-clients.md`](http-clients.md). Both must be coherent, and they must be coherent
*with each other*: a perfect browser profile presenting a Python TLS fingerprint is the
contradiction that gets caught.

For the authorization question that governs whether any of this is appropriate to do at
all, see [`compliance-and-scope.md`](compliance-and-scope.md).
