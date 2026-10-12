# Stock Monitor — 40-company research dossiers

Generate one **English, two-page Word document per company** from the previous **three calendar months** of news. Uses EODHD for news, fundamentals and daily close; Tavily news search when EODHD coverage is below a threshold; OpenAI for source-grounded synthesis. The company list is in `companies.json`.

The layout follows the supplied PLTR, TSLA and SpaceX dossiers: market snapshot, financial/operational/strategic themes, risks and catalysts, valuation table, optional SOTP and source notes. Template figures are never reused as facts.

## Setup

Python 3.11+ and LibreOffice Writer are required for production output. On Debian/Ubuntu:

```bash
apt-get install -y --no-install-recommends libreoffice-writer
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Set these **secret environment variables** through your environment's secure settings:

- `EODHD_API_TOKEN` — news, fundamentals and EOD access (plan entitlements matter).
- `TAVILY_API_KEY` — fallback news search.
- `STOCK_OPENAI_API_KEY` — OpenAI API access (`OPENAI_API_KEY` also works locally).
- Optional `STOCK_OPENAI_MODEL` — defaults to `gpt-4.1-mini`, requiring JSON Schema support.

`.env.example` documents variable names only. The app does not automatically load `.env` files. Never commit keys or paste them into command lines. Required HTTPS destinations: `eodhd.com`, `api.tavily.com`, `api.openai.com`, plus Python package registries for installation. Proxy-backed credentials use their supported HTTPS destination; the code does not inspect or print their values.

For this rootless Debian cloud environment, use `bash scripts/install-renderer.sh` instead of the system install and run `export PATH=/workspace/tools/bin:$PATH`. It installs a verified local renderer outside the checkout; no administrator permission is needed.

## Run

```bash
# One company first; refresh makes API snapshot timing explicit.
.venv/bin/python -m stock_monitor --tickers PLTR --refresh
# All 40 companies, sequentially to reduce rate-limit pressure.
.venv/bin/python -m stock_monitor --refresh
# Reproducible news end date (valuation metrics remain current provider snapshots).
.venv/bin/python -m stock_monitor --as-of 2026-10-12 --tickers PLTR,TSLA
```

Output: `output/YYYY-MM-DD/`, with one DOCX, rendered PDF, evidence JSON and a batch `manifest.json`. Exactly **two rendered PDF pages** are required before a production report is accepted. The generator tries 10, 9.5 and 9 pt body fonts; a report that still overflows is retained as `LAYOUT_FAILED` and the batch exits nonzero. Word pagination can differ by fonts and client; PDF is the checked layout reference. `--no-render` produces clearly named **DRAFT** DOCX files with unverified page counts.

Each company is independent; failures are recorded and remaining companies continue. Nonzero exit means at least one company failed. `partial` means a rendered report exists but documented evidence/valuation limitations remain; `draft` and `demo` are never live production success. Failed companies receive an explicit failure JSON, not a fabricated dossier. Reruns replace files for the same ticker/date; manifests describe only the current run. Use a separate `--output` directory to retain previous runs.

## News coverage and fallback

- Default window: today minus three calendar months through today, inclusive (e.g. July 12–October 12).
- EODHD pagination: 100 articles/page, default maximum 20 pages; cap exhaustion is marked incomplete. Change `--max-news-pages` if needed.
- Default `--min-news 10`: if fewer eligible unique EODHD articles are found, call Tavily once with a dated news query (up to 20 results), merge and deduplicate by URL/title.
- Undated and out-of-window results are excluded. Search results can mention other companies; human relevance review remains necessary. Fewer than the threshold is disclosed, not treated as exhaustive coverage.
- All eligible inputs are saved; at most 60 articles spread across the quarter enter the AI prompt, each with up to 5,000 content characters. This is a bounded digest, not an exhaustive full-text analysis.
- The API response cache excludes keys, records original retrieval times, and is reused unless `--refresh` is supplied. Refresh for current prices/fundamentals. News and evidence files may contain licensed content; observe provider usage terms.

`SPCX` is **unverified by default**. Its dossier uses a SpaceX-name Tavily query, without unverified equity prices or multiples. If you establish the correct EODHD listing identity, update its `symbol` and `verified` fields in `companies.json`. The uploaded template is a layout example, not proof of a listing or of its figures.

## Valuation

EODHD market capitalization, EV, trailing/forward P/E, price/sales, EV/revenue, EV/EBITDA, TTM revenue and shares outstanding are kept separate from AI interpretation. Raw (unadjusted) daily close and its trading date are shown; fundamentals include retrieval time and latest financial period. Provider snapshots may have different timestamps. Revenue uses the provider's financial-reporting currency, separately from the equity quote currency; if absent, its currency is explicitly unconfirmed. Missing metrics are `N/A`; non-positive multiples are `N/M`. No model-generated target prices.

Optional `--sotp assumptions.json` calculates segment EV as forecast metric × assumed multiple. The file must supply currency, assumption date/source, explicit net debt and diluted shares. Equity value = total segment EV − net debt; per-share value = equity / diluted shares. Assumptions must use consistent currency and units. `sotp.example.json` is synthetic documentation, not a valuation input for any real company. Segment EV is **not** divided by shares and mislabeled as equity value.

## Offline validation

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m stock_monitor --demo --tickers PLTR,TSLA,SPCX
```

Demo files and folders are explicitly marked synthetic and make no API requests. Offline tests exercise date windows, pagination, fallback/dedup, identity checks, missing metrics, citation rejection, SOTP equity reconciliation and DOCX generation. A successful demo validates mechanics and layout; it does not verify API credentials or live company facts.

No scheduler or outbound email is included. Reports are saved locally for review. This cloud task already has an isolated checkout; no additional Git worktree is needed.
