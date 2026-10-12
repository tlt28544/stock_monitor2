import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .api import APIError, EODHD, merge_news, openai_summary, tavily_news
from .data import three_months_before, valuation_snapshot, validate_identity, sotp_rows
from .report import build_report, render_pdf


def demo_inputs(company, start, end):
    """Synthetic examples only. Never presented as live company data."""
    articles = [{'title': f'SYNTHETIC DEMO: {company["ticker"]} research topic {i}', 'date': (end-timedelta(days=i*10)).isoformat(), 'content': 'Synthetic fixture for document layout testing. No actual company event or valuation.', 'link': f'https://example.com/demo/{i}', 'provider': 'Synthetic'} for i in range(1, 7)]
    return articles, {'General': {'Code': company['symbol'].split('.')[0], 'Name': company['name']+' — SYNTHETIC', 'Type': 'Common Stock', 'CurrencyCode': 'USD'}, 'Highlights': {}, 'Valuation': {}}, []


def demo_summary(articles):
    return {'overview': 'SYNTHETIC DEMO — layout validation only. This document contains no live research or actual valuation data.',
            'themes': [{'heading': h, 'text': 'Synthetic layout placeholder. Live mode replaces this with a source-grounded English analysis of company developments over the selected three-month period.', 'source_ids': [i+1]} for i,h in enumerate(['Financial momentum & operating metrics', 'Business developments & competitive position', 'Regulatory exposure & capital allocation'])],
            'valuation_commentary': 'No real valuation figures supplied. Live reports use EODHD financial metrics and explicitly distinguish analyst assumptions.',
            'risks': 'Synthetic demonstration; no company-specific conclusions.', 'catalysts': 'Review source-backed company disclosures in a live run.',
            'sources': [{'id':i+1, **a} for i,a in enumerate(articles)], 'selected_article_count': len(articles)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate one two-page English research dossier per company.')
    parser.add_argument('--companies', type=Path, default=Path('companies.json'))
    parser.add_argument('--tickers', help='Comma-separated ticker subset')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today(), help='News end date; valuations remain current snapshots')
    parser.add_argument('--output', type=Path, default=Path('output'))
    parser.add_argument('--cache', type=Path, default=Path('cache'))
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--model', default=os.getenv('STOCK_OPENAI_MODEL', 'gpt-4.1-mini'))
    parser.add_argument('--min-news', type=int, default=10)
    parser.add_argument('--max-news-pages', type=int, default=20)
    parser.add_argument('--sotp', type=Path, help='Optional sourced analyst assumptions JSON')
    parser.add_argument('--demo', action='store_true', help='Synthetic data; no API calls')
    parser.add_argument('--no-render', action='store_true', help='Save DRAFT DOCX without verified two-page rendering')
    args = parser.parse_args(argv)
    if args.min_news < 1 or args.max_news_pages < 1:
        parser.error('News threshold and max pages must be positive')
    companies = json.loads(args.companies.read_text())
    tickers = {x.strip().upper() for x in args.tickers.split(',')} if args.tickers else None
    if tickers:
        unknown = tickers - {c['ticker'] for c in companies}
        if unknown:
            parser.error('Unknown tickers: '+', '.join(sorted(unknown)))
        companies = [c for c in companies if c['ticker'] in tickers]
    if not companies or any(not re.fullmatch(r'[A-Z0-9_-]+', c['ticker']) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z]+', c['symbol']) for c in companies):
        parser.error('Company list is empty or contains invalid ticker/symbol identifiers')
    token = os.getenv('EODHD_API_TOKEN') or os.getenv('EODHD_API_KEY')
    ai_key = os.getenv('STOCK_OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
    tavily_key = os.getenv('TAVILY_API_KEY')
    if not args.demo:
        missing = [name for name,value in [('EODHD_API_TOKEN',token), ('STOCK_OPENAI_API_KEY',ai_key), ('TAVILY_API_KEY',tavily_key)] if not value]
        if missing:
            parser.error('Configure secret environment bindings: '+', '.join(missing))
    start, end = three_months_before(args.as_of), args.as_of
    out = args.output / f'{end.isoformat()}{"_DEMO" if args.demo else ""}'
    out.mkdir(parents=True, exist_ok=True)
    if not args.no_render:
        import shutil
        try:
            import pypdf  # noqa
        except ImportError:
            parser.error('Install requirements.txt including pypdf')
        if not shutil.which('libreoffice'):
            parser.error('Install LibreOffice for exact two-page validation, or use --no-render for drafts')
    client = None if args.demo else EODHD(token, args.cache, args.refresh)
    assumptions = json.loads(args.sotp.read_text()) if args.sotp else {}
    manifest = {'news_window': {'from': str(start), 'to': str(end)}, 'demo': args.demo, 'companies': []}
    failures = 0
    for company in companies:
        ticker = company['ticker']
        prefix = 'DEMO_' if args.demo else ('DRAFT_' if args.no_render else '')
        path = out / f'{prefix}{ticker}_Latest_News_and_Valuation_Dossier.docx'
        # Known generated outputs for this ticker/run are replaced, never accepted stale.
        for old in [path, path.with_suffix('.pdf'), path.with_suffix('.json'), out/f'{ticker}_failure.json']:
            old.unlink(missing_ok=True)
        entry = {'ticker':ticker}
        warnings, articles, fundamentals, prices = [], [], {}, []
        try:
            if args.demo:
                articles, fundamentals, prices = demo_inputs(company, start, end)
                provider_name = fundamentals['General']['Name']
                warnings.append('SYNTHETIC DEMO. Not investment research.')
            else:
                provider_name = 'Unverified — name search only'
                verified = company.get('verified', False)
                if verified:
                    try:
                        fundamentals = client.get('fundamentals/'+company['symbol'])
                        provider_name = validate_identity(company, fundamentals)
                    except (APIError, ValueError) as exc:
                        # No market metrics until a security identity can be verified.
                        verified = False; fundamentals = {}
                        warnings.append('Security identity or fundamentals unavailable: '+str(exc)+'.')
                else:
                    warnings.append('Ticker identity is unverified; EODHD symbol queries and market valuation omitted.')
                if verified:
                    try:
                        articles, truncated = client.news(company['symbol'], start, end, args.max_news_pages)
                        if truncated:
                            warnings.append('EODHD news pagination cap reached; coverage incomplete.')
                    except APIError as exc:
                        warnings.append('EODHD news unavailable: '+str(exc)+'.')
                    try:
                        prices = client.get('eod/'+company['symbol'], {'from':str(end-timedelta(days=14)), 'to':str(end), 'period':'d'})
                        if not isinstance(prices,list):
                            raise APIError('Unexpected EOD price response')
                    except APIError as exc:
                        prices=[]; warnings.append('Last close unavailable: '+str(exc)+'.')
                if len(articles) < args.min_news:
                    try:
                        articles = merge_news(articles, tavily_news(tavily_key, company, start, end))
                        warnings.append('Tavily fallback used; search results are not exhaustive and company relevance needs review.')
                    except APIError as exc:
                        warnings.append('Tavily fallback failed: '+str(exc)+'.')
                if not articles:
                    raise APIError('No dated news evidence from either provider; research report not generated')
                if len(articles) < args.min_news:
                    warnings.append(f'Only {len(articles)} eligible articles; below requested minimum {args.min_news}.')
            valuation = valuation_snapshot(fundamentals, prices)
            summary = demo_summary(articles) if args.demo else openai_summary(ai_key, args.model, company, articles, valuation)
            metadata = {'generated_at':datetime.now(timezone.utc).isoformat(), 'provider_name':provider_name, 'article_count':len(articles), 'warnings':warnings,
                        'fundamentals_retrieved':client.observations.get('fundamentals/'+company['symbol'],'N/A') if client else 'SYNTHETIC',
                        'price_retrieved':client.observations.get('eod/'+company['symbol'],'N/A') if client else 'SYNTHETIC', 'model':args.model if not args.demo else None}
            sotp = sotp_rows(assumptions.get(ticker), valuation)
            artifact = {'company':company, 'metadata':metadata, 'valuation':valuation, 'news':articles, 'summary':summary, 'sotp':sotp}
            json_path = path.with_suffix('.json')
            json_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
            pages = None
            for size in ([10] if args.no_render else [10, 9.5, 9]):
                build_report(path, company, start, end, valuation, summary, metadata, sotp, size)
                if args.no_render:
                    break
                # Remove only the PDF for this report before conversion, avoiding stale counts.
                path.with_suffix('.pdf').unlink(missing_ok=True)
                pages = render_pdf(path, out)
                if pages == 2:
                    break
            if not args.no_render and pages != 2:
                failed = path.with_name('LAYOUT_FAILED_'+path.name)
                path.replace(failed)
                raise RuntimeError(f'Rendered {pages} pages; report retained as LAYOUT_FAILED for review')
            entry.update(status='demo' if args.demo else ('draft' if args.no_render else ('partial' if warnings else 'complete')), document=str(path), evidence=str(json_path), pages=pages, warnings=warnings)
            print(f'{ticker}: {entry["status"]}; {pages if pages else "unverified"} pages')
        except (APIError, ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            failures += 1
            if path.exists():
                path.replace(path.with_name('FAILED_'+path.name))
            entry.update(status='failed', error=str(exc), warnings=warnings)
            print(f'{ticker}: failed — {exc}', file=sys.stderr)
            (out/f'{ticker}_failure.json').write_text(json.dumps({'company':company,'error':str(exc),'warnings':warnings,'news':articles}, indent=2))
        manifest['companies'].append(entry)
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
