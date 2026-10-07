# Legal and Practical Risk Framework

This is an engineering reference, not legal advice. Use it to build intuition, then verify with counsel for your jurisdiction and use case.

## Critical Distinction: Criminal vs Civil

| Category | What it is | Typical trigger |
|---|---|---|
| **Criminal unauthorized access** | Violating computer fraud statutes (CFAA, 刑法 285/286, etc.) | Bypassing technical access controls: passwords, encryption, authentication gates |
| **Civil contract dispute** | Violating Terms of Service | Scraping public pages after the provider says "don't" |
| **Privacy regulation** | GDPR, PIPL, CCPA, etc. | Collecting, processing, or retaining personal data |
| **IP/database rights** | Copyright, sui generis database rights | Replicating creative selection/arrangement or substantial database investment |
| **Unfair competition** | 反不正当竞争法 (CN) | Acquiring/using another's data by defeating technical measures |

**The key insight:** In most jurisdictions, scraping publicly available data from unauthenticated pages does not constitute criminal "unauthorized access." The hiQ v. LinkedIn precedent (US) and similar rulings elsewhere established that technical barriers matter, not contractual text alone.

## US: Case Law State of Play

| Case | Citation | Holding |
|---|---|---|
| Van Buren v. United States | 2021, 593 U.S. 374 | "Exceeds authorized access" = gates-up-or-down; using access for improper purpose is not a CFAA violation |
| hiQ v. LinkedIn (9th Cir.) | 938 F.3d 985 (2019); 31 F.4th 1180 (2022-04-18) | Public scraping likely not CFAA; injunction dissolved |
| LinkedIn v. hiQ (final) | Consent judgment 2022-12-08 | **$500,000 + permanent injunction + destroy scraped data/code/algorithms** |
| Meta v. Bright Data | N.D. Cal. 3:23-cv-00077-EMC, 2024-01-23 (Judge Chen) | Logged-out scraping is not "use" of the terms; Meta dropped the case Feb 2024 |
| X Corp. v. Bright Data | 3:23-cv-03698-WHA (Judge Alsup), 733 F. Supp. 3d 832 | 2024-05-09 dismissal: threadbare recitals + Copyright Act conflict preemption; **dismissed with prejudice 2025-06-27** |

**Net effect**: The CFAA route against public scraping is largely closed. Breach-of-contract remains the real civil exposure — and hiQ shows the endgame cost when it goes badly.

## EU: Case Law and Instruments

| Instrument / Case | Reference | Point |
|---|---|---|
| CNIL v. Clearview AI | €20M (2022-10-20), €5.2M (2023-05-10) | Scraped biometric data = GDPR violation; fines stack on non-compliance |
| EDPB Opinion 28/2024 | 2024-12 | AI model training and legitimate interest analysis |
| CNIL 2025 guidance | 2025 | Legitimate-interest balancing for web scraping |
| DSM Directive Art. 3 | 2019/790 | Research TDM exception — **cannot be overridden by contract** |
| DSM Directive Art. 4 | 2019/790 | General TDM exception + **Art. 4(3) machine-readable opt-out** (recital 18) |
| Database Directive Art. 7(1) | 96/9/EC | Sui generis right on substantial investment |
| Database Directive Art. 10 | 96/9/EC | 15-year term, **renewed by substantial new investment** |

**Practical reading**: Art. 3 (research) is non-overridable. Art. 4 (commercial) is subject to opt-out. A `robots.txt`-based or Content-Signals-based reservation can constitute a valid Art. 4(3) machine-readable opt-out.

## China: Criminal Exposure

| Provision | Content |
|---|---|
| 刑法 285(2) | 非法获取计算机信息系统数据 |
| 刑法 285(3) | 提供侵入、非法控制计算机信息系统的程序、工具 |
| 刑法 286 | 破坏计算机信息系统 |

**Thresholds** (法释〔2011〕19号): 违法所得 5,000元 / 经济损失 1万元.

**Cases**:

| Case | Citation | Outcome |
|---|---|---|
| 晟品公司 | (2017)京0108刑初2384号 | **全国首例爬虫入刑** — forged `device_id` / UA / IP |
| 百度网盘 | (2019)苏1091刑初157号 | Criminal liability |
| 武汉元光「车来了」 | — | Criminal liability |
| 得物 | (2022)苏0213刑初223号 | Criminal liability |
| 上海普陀王某 | — | 违法所得 60余万，判三缓三，罚金 8万 |

**Pattern**: Criminal exposure in China attaches to **defeating technical measures** (forged device fingerprints, bypassed authentication), not to reading public pages.

## China: Civil Exposure

| Case | Citation | Outcome |
|---|---|---|
| 大众点评诉百度 | (2015)浦民三(知)初字第528号 / (2016)沪73民终242号 | 300万 + 23万；**robots.txt does not govern post-crawl use** |
| 百度诉360 | (2013)一中民初字第2668号 | 50万；robots protocol is not a contract but constitutes recognized business ethics |
| 新浪微博诉脉脉 | (2015)海民(知)初字第12602号 / (2016)京73民终588号 | 200万；**三重授权原则** (user→platform, platform→developer, user→developer) |
| 抖音诉六界小葫芦 | (2021)浙0110民初2914号 | 100万 |
| 抖竹刷量 / 抖商商标 | — | 100万 / 200万 |

**反不正当竞争法 2025 revision** (passed 2025-06-27, effective **2025-10-15**):

- **Art. 13 new para 3**: bans acquiring or using others' data by 欺诈 / 胁迫 / **避开或破坏技术管理措施**
- **Art. 13 new para 4**: bans 滥用平台规则

**This is the most important recent change.** 「避开或破坏技术管理措施」 now has explicit statutory footing — meaning anti-bot evasion moves closer to the unfair-competition core in China than in the US.

## China: Data Protection

| Instrument | Provision |
|---|---|
| PIPL Art. 13(6) | Lawful basis for processing publicly disclosed personal info |
| PIPL Art. 27 | 已公开个人信息 may be processed within 合理范围; **明确拒绝除外**; 重大影响 requires consent |
| 合规审计指引 第十二条 | Lists 5 violation patterns including scale / duration / purpose exceeding 合理范围 |
| 网络数据安全管理条例 Art. 24 | Automated collection must delete or anonymize unnecessary personal info |

**Practical reading**: Publicly disclosed ≠ free to collect at scale. Scale, duration, and purpose are the operative tests.

## AI Training Scraping

| Case | Status |
|---|---|
| NYT v. Microsoft/OpenAI (S.D.N.Y. 23-cv-11195, Judge Stein) | 2025-03-26 / 2025-04-04 MTD ruling: **all copyright infringement claims survive**; common-law unfair competition dismissed with prejudice; most DMCA §1202 dismissed without prejudice; 3-year limitations defense rejected. **Fair use is still at summary judgment — no final ruling.** |
| Reddit–Google / Reddit–OpenAI | Licensing deals — the commercial-alternative path |

## Practical Risk Matrix

| Scenario | Criminal risk | Civil/operational risk | Mitigation |
|---|---|---|---|
| Public pages, no auth, no PII, moderate rate | Very low | Low | Standard throttling, respectful rate limits |
| Public pages, high volume, commercial reuse | Very low | Medium | Document lawful basis, assess database rights exposure |
| Authenticated scraping (your own account) | Low | Medium | Review ToS for account termination risk |
| Bypassing auth/paywalls/technical controls | **High** | High | Do not proceed without explicit legal clearance |
| Forging device fingerprints to defeat risk control | **High (CN)** | High | This is the specific trigger in the 晟品 line of cases |
| Large-scale PII collection | Low (if public) | **High** | GDPR/PIPL obligations apply; implement data minimization and deletion |
| Scraping government, medical, financial records | Context-dependent | Context-dependent | Consult counsel; these categories attract heightened scrutiny |
| Scraping against an explicit AI-training reservation | Low | Medium–High | EU DSM Art. 4(3) opt-out may apply; Content Signals encodes this |

## Operational Hygiene (Do These Regardless)

- Rate-limit to avoid service degradation
- Respect `robots.txt` as a signal, not a legal barrier — but note it **does** function as a machine-readable rights reservation in the EU
- Use identifiable User-Agent with contact info when practical
- Minimize data collection to what you actually need
- Implement retention limits and deletion schedules
- Do not scrape authenticated sessions you do not own without authorization
- Record your lawful basis **before** starting, not after a complaint arrives

## Actual Stop Signals

Pause and seek legal counsel when:
- You receive a formal cease-and-desist or court order
- You are bypassing encryption, passwords, or other technical access controls
- You are handling regulated categories: health data (HIPAA), financial data (GLBA), children's data (COPPA), biometric data (GDPR Art. 9)
- Your jurisdiction has specific anti-scraping statutes beyond general computer fraud law
- You receive **HTTP 402** with `crawler-*` headers (Cloudflare Pay Per Crawl) — this is an explicit commercial rejection, not a technical obstacle

## Do Not Confuse These

- **ToS violation ≠ crime.** Most scraping disputes are civil matters or platform enforcement, not law enforcement.
- **Public data ≠ private data.** If it loads in an incognito browser without logging in, it is generally public.
- **Anti-bot evasion ≠ unauthorized access.** Circumventing fingerprinting and behavioral detection is a technical arms race, not a legal boundary—unless you are also bypassing authentication.
- **CAPTCHA solving ≠ hacking.** The legal posture depends on what data you access after solving.
- **"It was public" is not a defense to unfair competition** in China if you defeated technical measures to get it at scale.

## Risk Assessment Workflow

```
1. Is the data behind authentication or technical access control?
   → Yes: High criminal risk. Stop unless authorized.
   → No: Continue to 2.

2. Does the data contain personal information?
   → Yes: Assess privacy regulation obligations (GDPR/PIPL).
   → No: Continue to 3.

3. Is this high-volume commercial use?
   → Yes: Assess civil / database rights / unfair-competition exposure.
   → No: Proceed with standard operational hygiene.

4. Did you defeat a technical measure to obtain it?
   → Yes: In China, assume 反不正当竞争法 Art. 13 exposure. Reassess.
   → No: Proceed.
```

A practical scraping operation distinguishes between real legal threats and platform discomfort. Treat the former seriously; treat the latter as an engineering problem.

## Source Index

- Van Buren v. United States, 593 U.S. 374 (2021)
- hiQ v. LinkedIn, 938 F.3d 985 (9th Cir. 2019); 31 F.4th 1180 (2022-04-18) — https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf
- Meta v. Bright Data — https://fbm.com/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data
- X Corp. v. Bright Data dismissal — https://blog.ericgoldman.org/archives/2024/05/x-corp-v-bright-data-is-the-decision-weve-been-waiting-for-guest-blog-post.htm
- EDPB Opinion 28/2024 — https://edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf
- DSM Directive 2019/790, Database Directive 96/9/EC — https://eur-lex.europa.eu
- 反不正当竞争法 2025 修订 — https://xzfg.moj.gov.cn/front/law/detail?LawID=1734
- 最高法 2026 反不正当竞争典型案例 — https://court.gov.cn/zixun/xiangqing/449641.html
- NYT v. OpenAI MTD opinion — https://nysd.uscourts.gov/sites/default/files/2025-04/yf%2023cv11195%20OpenAI%20MTD%20opinion%20april%204%202025.pdf
- Cloudflare Content Signals Policy — https://blog.cloudflare.com/content-signals-policy
