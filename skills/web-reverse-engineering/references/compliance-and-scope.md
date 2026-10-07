# Compliance, Scope, and Responsible Use

This document defines what this skill is for, where the line between legitimate and
illegitimate use falls, and how to keep work on the right side of it. Read it before
applying anything else in this skill.

The short version: **the techniques are neutral; the authorization is not.** Every
technique here is used daily by security teams, interoperability engineers, malware
analysts, academic researchers, and bug-bounty hunters. The same techniques become
criminal when applied to systems you were not permitted to touch. The technique does not
change; the permission does.

---

## 1. What this skill is

A knowledge base and a set of tooling templates for understanding how software,
protocols, and network clients actually behave — at the layers where documentation is
missing, incomplete, or deliberately withheld.

That covers:

- Reading and reproducing network protocols and APIs that have no published spec
- Understanding what a client sends, and why, when a server will not explain itself
- Recovering data formats so that data can be read, migrated, or preserved
- Analyzing binaries, firmware, and mobile apps to understand their behaviour
- Building test clients that behave like real ones, so that a system can be tested
  honestly

It is documentation and scaffolding. It is not a service, not a hosted capability, and
not an attack tool. Nothing in this skill acts on a target on its own; a human decides
what to point it at.

## 2. Intended use

Explicitly in scope:

| Context | Why it is legitimate |
|---|---|
| **Authorized penetration testing** | Signed engagement, defined scope, rules of engagement |
| **Bug bounty programs** | Scope defined by the program's policy; the program grants permission |
| **Security research** | Coordinated disclosure; the researcher reports rather than exploits |
| **Incident response and malware analysis** | Understanding hostile code to contain it |
| **Interoperability engineering** | Making your own system talk to another system, incl. your own accounts |
| **Data portability and archival** | Reading data you are entitled to, in a format nobody documented |
| **Academic study and CTF** | Isolated environments, published findings |
| **Accessing your own accounts and systems** | You are the principal; you may inspect your own client |
| **Lawful access to public data** | Publicly reachable data, at a rate that does not damage the service |

## 3. Authorization is the dividing line

The distinction that matters is not "which tool" but "whose system".

**Authorized** — you have permission, one of these ways:

- Written authorization: a contract, a scope document, a signed engagement letter
- A published policy: a bug-bounty scope, a vulnerability disclosure policy, a CTF
  rules page
- Ownership: the system is yours, or you are acting for the owner
- Public authorization: the resource is intentionally and openly public, and no access
  control is being circumvented

**Not authorized** — none of these is present:

- "It is publicly reachable" is not the same as "I may do anything to it". Public
  *read* access is not permission to probe for vulnerabilities, and it is not permission
  to cause load.
- "It is on the internet" is not permission.
- "I am just curious" is not permission.
- A third party's customer account is not your account, even if you can technically
  reach it.
- An employer's internal system is not authorized by being reachable from your laptop.

When authorization is unclear, the correct action is to ask the system owner in writing
before proceeding. Not to proceed carefully. Ask.

## 4. Where the legal exposure actually is

Three distinct risk categories get conflated. They are not the same, and treating them
as the same leads to bad decisions in both directions.

**Contract / ToS.** Terms of service are a contract. Breaching one is a civil matter
between you and the operator. It is not a crime. It may get you banned, and it may
support a civil claim, but it does not by itself create criminal liability. Treat ToS as
a business-risk input, not a criminal-law stop sign.

**Access control circumvention.** This is where criminal law attaches, in most
jurisdictions. The dividing line courts have drawn is roughly *gates-up-or-down*: if
the system requires authentication to reach a resource and you get past that
authentication without permission, you have crossed a criminal line. If the resource is
open to the public and you read it, you generally have not.

**Anti-circumvention of technical protection measures.** Separate again. Circumventing
a technological protection measure on a copyrighted work is its own cause of action in
the US (DMCA §1201) and in the EU, largely independent of whether you breached access
control. There are statutory exemptions for security research — see below.

The operational summary:

- ToS breach ≠ crime.
- Bypassing an anti-bot challenge ≠ unauthorized access, *unless* authentication is also
  being bypassed.
- Bypassing authentication or an access control **is** the criminal line.
- Circumventing a TPM on copyrighted material is a distinct risk with its own rules.

Jurisdiction-specific detail, case law, and thresholds live in
[`legal-ethical.md`](legal-ethical.md). That document is the authoritative reference for
this skill; this one is the scope statement.

## 5. Statutory research exemptions

Several jurisdictions carve out good-faith security research. These are the ones worth
knowing, because they are the closest thing to a safe harbour that exists without a
contract.

**United States — DMCA §1201 triennial exemptions.** The Librarian of Congress renews
classes of works exempt from the anti-circumvention prohibition every three years. The
ninth triennial rulemaking (final rule effective **2024-10-28**) renewed and expanded,
among others:

- **Computer programs — security research.** Circumvention for good-faith security
  research on devices or machines primarily designed for individual consumers.
- **Vehicle operational data.** A new exemption allowing owners, lessees, or those
  acting on their behalf to access, store, and share operational data including
  diagnostic and telematics data — broader than the existing vehicle-repair exemption.
- **Retail-level commercial food preparation equipment**, for diagnosis, maintenance,
  and repair.
- **Text and data mining** for scholarly research and teaching, extended to researchers
  affiliated with other nonprofit institutions.

These temporary exemptions run until **2027-10-28**. The tenth triennial proceeding
opened in 2026 with a renewal deadline of 2026-08-24. **Verify the current status before
relying on any exemption** — they expire, and renewal is not automatic.

Note also the limit: the Copyright Office declined to create an exemption for
AI-related security research on the reasoning that the adverse effects were caused by
terms of service and safety guidelines, not by §1201 — so §1201 was the wrong
instrument. That is not a statement that the research is unlawful; it is a statement
that the exemption process could not address it.

**EU.** Directive 2009/24/EC Article 6 permits decompilation for interoperability
purposes, under conditions. The DSM Directive (EU 2019/790) Article 3 permits text and
data mining for scientific research, and Article 4 creates a text-and-data-mining
exception that rights holders can reserve — which is why machine-readable reservations
(see §7) matter.

**China.** Reverse engineering for interoperability is recognized in principle, but the
2025 revision of the Anti-Unfair Competition Law, effective
**2025-10-15**) added explicit language targeting circumvention or destruction of technical management measures — that is, circumventing or
destroying technical management measures. This makes anti-bot evasion materially riskier
in China than in the US or EU. See [`legal-ethical.md`](legal-ethical.md).

**Coordinated disclosure.** Where a vulnerability is found, the norm is to report it
privately to the owner, allow a reasonable remediation window, and only then publish.
Most vendors publish a disclosure policy with a safe-harbour clause; where one exists
and you comply with it, the owner has committed not to pursue legal action over the
research. Where none exists, the norm still applies — report first. CISA publishes a
free vulnerability disclosure policy template that is widely used as the basis for these
programs.

## 6. Dual-use, stated plainly

This skill is dual-use and it does not pretend otherwise. Every capability here cuts
both ways:

- A TLS-impersonating HTTP client lets a researcher verify that a bank's bot detection
  works. It also lets someone evade it.
- Environment simulation lets an analyst run vendor code offline to understand a
  signing algorithm. It also lets someone forge that signature.
- Firmware extraction lets a researcher audit a router for backdoors. It also lets
  someone modify a device they do not own.
- An unpacking workflow lets a malware analyst see what a sample does. It also lets
  someone strip protections from software.

The honest position is not "this is only ever used for good". It is:

1. The knowledge is already public, distributed across vendor documentation, conference
   talks, academic papers, and open-source repositories. Withholding it here would not
   remove it.
2. Understanding a defensive system is a prerequisite to evaluating it. A detection
   mechanism that nobody can test is not a security control; it is a claim.
3. The controls that actually matter are authorization, intent, and consequence — not
   information availability.

What this means in practice: this skill states the constraints clearly, declines to
pretend the tools are harmless, and puts the decision about targeting where it belongs —
with the person who has the facts about their own authorization.

## 7. Respecting expressed preferences

Some operators publish machine-readable statements about how their content may be used.
These are preferences, not access controls, and they are legally meaningful in some
jurisdictions and not others. Read them, and make a deliberate decision rather than
ignoring them by default.

| Mechanism | What it expresses | Status |
|---|---|---|
| `robots.txt` | Crawl permission per path and per agent | De facto standard (RFC 9309). Voluntary. Courts have held it does not itself control access. |
| `Content-Signal` (Cloudflare, 2025-09-24) | `search` / `ai-input` / `ai-train` preferences, in `robots.txt` | Single-vendor proposal layered on RFC 9309, not an IETF standard. CC0 licensed. |
| `TDMRep` | Text-and-data-mining reservation, as JSON at `/.well-known/tdmrep.json` plus HTTP headers | W3C community group. Aligned with EU DSM Art. 4. Structured, therefore machine-interpretable. |
| `ai.txt` | Training / inference / RAG permissions | Voluntary. No standards body. |
| `llms.txt` | A content guide for LLM readers — navigational, **not** a restriction | Community convention (Answer.AI). Google has stated it ignores it. Confers no rights and reserves none. |
| `Content-Usage` header | `train-ai` / `search` = `y`/`n` | IETF AIPREF working group draft as of 2026. Not yet a published standard. |
| `X-Robots-Tag` / `noai` | Per-resource indexing and AI-use hints | Widely implemented, voluntary. |

Two things worth internalizing:

**A machine-readable reservation is stronger than prose.** A German court held in
December 2025 that an opt-out buried in terms of use is insufficient because a machine
cannot read it; what counts is a machine-readable signal. If you are operating at scale,
record which signal you read, and when.

**Most of these are not enforced, and that is not permission.** The absence of
enforcement says nothing about legality. It says the operator has not chosen to spend
money on this particular fight yet.

Also: an `llms.txt` is a navigation aid, not a licence. Do not read it as granting
permission.

## 8. Commercial gates are not technical obstacles

A distinct case, because engineers routinely misread it:

An **HTTP 402 Payment Required** response, or `crawler-*` headers, is a commercial
statement. It means: this content is licensed, and you may pay for it or stop. It is not
a puzzle. It is not a detection failure. Retrying with a better fingerprint does not
address it, and treating it as a bypass problem is both ineffective and a bad-faith
reading of an explicit signal.

Same category: sites that publish a licensing program, or that gate content behind a
paid API. The correct engineering response is to evaluate the licence or use a different
source — not to escalate evasion.

## 9. Attribution hygiene

Separate concern, and worth stating because it is easy to get wrong in a way that harms
you personally rather than legally.

When doing authorized work, keep the work identity separate from the personal one:

- Dedicated browser profile or VM per engagement — not because you are hiding, but
  because engagement data must not leak into personal accounts, and personal credentials
  must not touch engagement infrastructure.
- Do not log into personal accounts from a research browser session, or vice versa.
- Keep client data out of personal cloud storage.
- Assume anything you send is logged, attributable, and retained.

See [`identity-and-attribution.md`](identity-and-attribution.md) for the operational
detail. The framing there is legitimate separation for authorized work and personal
privacy — not evasion of accountability for unauthorized work.

## 10. Stop conditions

Stop, and reassess, when any of these is true:

- You cannot state, in one sentence, who authorized this and what the scope is.
- You are about to bypass an **authentication** control rather than a bot challenge.
- The target responds with a commercial gate (402, licensing program, paid API).
- The work requires accessing another person's account or data.
- The target is a safety-critical or medical system.
- You are being asked to evade monitoring on a system you do not own.
- The marginal cost of the work exceeds the value of the data at your volume — this is
  usually a signal to reconsider the whole approach.
- You receive a cease-and-desist, an injunction, or any contact from legal process.

Note that "the site blocks me" is not on this list. A block is a technical fact and a
signal to diagnose which layer is failing. See the Layer Diagnosis Table in
[`../SKILL.md`](../SKILL.md).

## 11. What this skill does not provide

Stated so that nothing is ambiguous:

- It does not provide authorization, and it cannot. Only the system owner can.
- It does not provide credentials, keys, tokens, or licence data.
- It does not target any specific system.
- It does not provide a service that acts on a target; every artifact here is a template
  or a diagnostic that a human points somewhere.
- It does not guarantee that any technique will work, or that using it is lawful in your
  jurisdiction.

## 12. Note for AI agents using this skill

If you are an agent reading this skill, apply the following:

1. **Ask what the authorization is** when a task moves from reading public
   documentation to interacting with a live third-party system. A user statement of
   ownership or of engagement scope is sufficient; do not demand a contract for a CTF
   or a self-hosted test instance.
2. **Do not escalate past an authentication boundary** on the basis that the user seems
   to want the data. An access control is the line; a bot challenge is not.
3. **Treat a commercial gate as final.** Do not produce evasion steps for a resource
   that has answered 402.
4. **Prefer the least invasive technique that answers the question.** Reading a public
   API beats simulating a browser; simulating a browser beats patching a binary.
5. **State the limits of what you verified.** If a technique was not tested, say so. A
   confident wrong answer costs more than an admitted gap.

## 13. Summary

- Techniques are neutral; authorization is not.
- Public read access is not permission to probe.
- Bypassing authentication is the criminal line; bypassing a bot challenge usually is
  not.
- ToS breach is a civil matter, not a crime.
- Circumventing a TPM on copyrighted material is a separate risk with its own rules.
- Statutory research exemptions exist, are time-limited, and must be re-verified.
- Commercial gates are decisions, not obstacles.
- When authorization is unclear, ask. Do not proceed carefully — ask.
