# Scraping Frameworks (Scale and Reliability)

For one-off pages, scripts are enough. For sustained extraction, use a framework.

## Framework Comparison

| Framework | Language | Best for | Install | Pros | Cons |
|---|---|---|---|---|---|
| Scrapy | Python | high-throughput crawls, mature pipelines | `pip install scrapy` | robust ecosystem, strong middleware model | steeper learning curve |
| Crawlee/Apify SDK | Node/TS | browser-heavy + queue orchestration | `npm i crawlee` | great browser integration and request queues | JS stack required |
| Colly | Go | lightweight high-speed crawlers | `go get github.com/gocolly/colly/v2` | fast and simple | fewer built-in anti-bot features |
| Rod | Go | browser automation + scraping | `go get github.com/go-rod/rod` | native Go, single binary, fast | smaller ecosystem than Playwright |
| Ferret | Go | declarative web scraping | `go get github.com/MontFerret/ferret` | FQL query language, fast | less mature than Scrapy |
| spider (Rust) | Rust | fast, memory-safe crawling | `cargo add spider` | zero-cost abstractions, safe | smaller ecosystem |
| PlaywrightCrawler | Node/TS | browser-based at scale | `npm i crawlee` | built on Playwright, queue managed | requires browser binary |
| Scrapy-Redis | Python | distributed Scrapy | `pip install scrapy-redis` | horizontal scaling with Redis | adds infrastructure complexity |
| Splash | Python | headless browser for Scrapy | `docker run scrapinghub/splash` | integrates with Scrapy middleware | slower than direct Playwright |

## Scrapy Minimal Example

```python
import scrapy

class ExampleSpider(scrapy.Spider):
    name = "example"
    start_urls = ["https://example.com"]

    def parse(self, response):
        yield {"title": response.css("title::text").get()}
```

## Crawlee Minimal Example

```javascript
import { PlaywrightCrawler } from 'crawlee';

const crawler = new PlaywrightCrawler({
  async requestHandler({ page, request, log }) {
    log.info(`Processing ${request.url}`);
    const title = await page.title();
    console.log({ url: request.url, title });
  },
});

await crawler.run(['https://example.com']);
```

## Architecture Pattern (Production)

```text
scheduler -> url queue -> worker pool -> parser -> validation -> storage
                                 -> retry/dead-letter
                                 -> metrics/logs/traces
```

## Must-Have Reliability Controls

- idempotent fetch + parse steps
- bounded retries with exponential backoff
- dead-letter queue for hard failures
- checkpointing for resume after crash
- per-target rate policies

## Integration with Anti-Bot Stack

- inject proxy decisions at request scheduling layer
- separate identity pools by target family
- store challenge outcomes to improve routing
- trigger fallback path (managed API/browser escalation) automatically

**Concrete routing decision**:

```python
# pseudo-code: choose transport per target, not per request
TRANSPORT = {
    "plain_site":    "httpx",
    "cf_protected":  "curl_cffi",          # + residential proxy
    "js_challenge":  "curl_cffi",          # + challenge solver
    "spa_or_turnstile": "camoufox",        # browser path
    "cn_risk_control": "cn_reverse_stack", # signed-param layer, NOT browser
}
```

Route by target, not by request — per-request transport switching produces incoherent fingerprints.

## Data Contract Discipline

Define schemas early:
- raw payload
- normalized record
- extraction metadata (source URL, timestamp, parser version, confidence)

Without schema/versioning, replay and audit become painful.

## Cost Controls

- cache immutable pages
- prioritize API endpoints over rendered pages
- keep browser usage for pages that strictly require JS
- batch writes to storage sinks
- **measure useful-data-per-dollar, not requests-per-dollar** — a browser request that returns nothing costs the same as one that succeeds

## When a Framework Is the Wrong Answer

Frameworks add overhead. Skip them when:

- the target is a single API with a signed parameter (write a thin client)
- total volume is under ~10k requests (a script plus a queue is enough)
- the real work is reverse engineering, not crawling (framework choice is irrelevant)
