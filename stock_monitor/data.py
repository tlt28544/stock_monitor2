import calendar
import math
from datetime import date


def three_months_before(day):
    month = day.month - 3
    year = day.year
    if month <= 0:
        month += 12
        year -= 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def valuation_snapshot(fundamentals, prices):
    general = fundamentals.get('General', {})
    h = fundamentals.get('Highlights', {})
    v = fundamentals.get('Valuation', {})
    shares = fundamentals.get('SharesStats', {})
    latest = max(prices, key=lambda p: p.get('date', '')) if prices else {}
    # Unadjusted close is comparable to the current share count; adjusted close is not.
    return {'currency': general.get('CurrencyCode', 'N/A'),
            'financial_currency': fundamentals.get('Financials', {}).get('Income_Statement', {}).get('currency_symbol', 'Currency unconfirmed'), 'financial_period': h.get('MostRecentQuarter', 'N/A'),
            'price_date': latest.get('date', 'N/A'), 'price': number(latest.get('close')),
            'market_cap': number(h.get('MarketCapitalization')), 'enterprise_value': number(v.get('EnterpriseValue')),
            'shares_outstanding': number(shares.get('SharesOutstanding')),
            'trailing_pe': number(v.get('TrailingPE', h.get('PERatio'))), 'forward_pe': number(v.get('ForwardPE')),
            'price_sales': number(v.get('PriceSalesTTM')), 'ev_revenue': number(v.get('EnterpriseValueRevenue')),
            'ev_ebitda': number(v.get('EnterpriseValueEbitda')), 'revenue_ttm': number(h.get('RevenueTTM'))}


def validate_identity(company, fundamentals):
    g = fundamentals.get('General', {})
    code = str(g.get('Code', '')).upper()
    if not code or code != company['symbol'].split('.')[0].upper():
        raise ValueError('Fundamentals symbol identity did not match requested symbol')
    if str(g.get('Type', '')).lower() not in ('common stock', 'adr', 'preferred stock'):
        raise ValueError('Requested symbol is not a supported equity; confirm identity')
    # Provider name is retained in the report for human identity review.
    return g.get('Name', 'N/A')


def sotp_rows(config, valuation):
    if not config:
        return [], None
    if config.get('currency') != valuation['currency']:
        raise ValueError('SOTP currency must match valuation currency')
    if not config.get('as_of') or not config.get('source'):
        raise ValueError('SOTP needs an assumption date and source')
    segments = config.get('segments', [])
    if not 1 <= len(segments) <= 5:
        raise ValueError('SOTP requires 1–5 segments')
    rows = []
    for segment in segments:
        base, multiple = number(segment.get('metric_value')), number(segment.get('multiple'))
        if base is None or multiple is None or base < 0 or multiple < 0:
            raise ValueError('SOTP metric values and multiples must be finite and nonnegative')
        rows.append({'name': segment['name'], 'driver': segment['metric'], 'base': base, 'multiple': multiple, 'ev': base * multiple})
    net_debt = number(config.get('net_debt'))
    share_count = number(config.get('diluted_shares'))
    if net_debt is None or share_count is None or share_count <= 0:
        raise ValueError('SOTP requires explicit net debt and positive diluted shares')
    total = sum(r['ev'] for r in rows)
    return rows, {'ev': total, 'net_debt': net_debt, 'equity': total-net_debt, 'per_share': (total-net_debt)/share_count,
                  'as_of': config['as_of'], 'source': config['source']}
