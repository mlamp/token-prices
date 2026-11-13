#!/usr/bin/env python3
"""Compare supported provider snapshots with the catalog; never apply changes."""
from __future__ import annotations

import argparse
import json
import math
import re
from decimal import Decimal
from pathlib import Path

try:
    from .fetch_sources import SOURCES, fetch
except ImportError:
    from fetch_sources import SOURCES, fetch

ROOT = Path(__file__).resolve().parents[1]


def rate(value: str) -> float | None:
    if value == '-':
        return None
    if not re.fullmatch(r'\$[0-9]+(?:\.[0-9]+)?', value):
        raise ValueError(f'unrecognized price cell {value!r}')
    number = float(value[1:])
    if not math.isfinite(number):
        raise ValueError('non-finite source price')
    return number


def parse_openai(body: str) -> dict:
    # Only this complete table layout is supported; never guess a new layout.
    match = re.search(r'Short context:\s*≤([0-9]+)K input tokens\.\s*Long context:\s*>\1K input tokens\.', body)
    if not match:
        raise ValueError('OpenAI short/long pricing boundary is missing or changed format')
    boundary = int(match[1]) * 1000
    result = {}
    service = None
    header = None
    old = ['Short context input', 'Short context cached input', 'Short context cache writes', 'Short context output', 'Long context input', 'Long context cached input', 'Long context cache writes', 'Long context output']
    new = [prefix + field for prefix in ['Short context ', 'Long context ']
           for field in ['input', 'output', 'cached input', '30m write', '12h write']]
    simple = ['Input', 'Output', 'Cached input']
    for line in body.splitlines():
        if line.startswith('### '):
            match_service = re.fullmatch(r'### (Standard|Batch|Flex|Fast|Ultrafast) pricing data', line)
            service = match_service[1].lower() if match_service else None
            header = None
        if line in ['#### Batch', '#### Flex'] and service in ['batch', 'flex']:
            service = line[5:].lower()
            header = None
        if not service or not line.startswith('| '):
            continue
        cells = [part.strip() for part in line.split('|')[1:-1]]
        if cells[0] == 'Model':
            header = cells[1:]
            if header not in [old, new, simple]:
                raise ValueError('OpenAI pricing column layout changed')
            continue
        if not re.match(r'^(?:gpt-|o[0-9]|chat-)', cells[0]):
            continue
        if header is None or len(cells) != len(header) + 1:
            raise ValueError('OpenAI pricing table column count changed')
        mid = cells[0].split(' ')[0]
        values = dict(zip(header, [rate(cell) for cell in cells[1:]]))
        long_priced = values.get('Long context input') is not None
        if header == simple:
            bands = [('', 0, None)]
        else:
            bands = [('Short context ', 0, boundary), ('Long context ', boundary + 1, None)]
        for prefix, lower, upper in bands:
            names = [('input', 'input'), ('output', 'output'), ('cached input', 'cache_read'),
                     ('cache writes', 'cache_write'), ('30m write', 'cache_30m_write'),
                     ('12h write', 'cache_12h_write')]
            if not prefix:
                names = [('Input', 'input'), ('Output', 'output'), ('Cached input', 'cache_read')]
            pricing = {field: values[prefix + name] for name, field in names
                       if values.get(prefix + name) is not None}
            if not pricing:
                continue
            if 'input' not in pricing or 'output' not in pricing:
                raise ValueError(f'{mid}: incomplete context pricing band')
            if 'cache_30m_write' in pricing:
                pricing['cache_write'] = pricing['cache_30m_write']
            if prefix and lower == 0 and not long_priced:
                upper = None
            tier = {'service_tier': service, 'input_tokens_min': lower,
                    'input_tokens_max': upper, 'pricing': pricing}
            existing = result.setdefault(mid, [])
            same = [t for t in existing if t['service_tier'] == service
                    and t['input_tokens_min'] == lower]
            if same and same != [tier]:
                raise ValueError(f'{mid}: conflicting repeated pricing row')
            if not same:
                existing.append(tier)
    # Services without a long band stop at the model's documented pricing boundary.
    for tiers in result.values():
        if any(t['input_tokens_min'] > 0 for t in tiers):
            for tier in tiers:
                if tier['input_tokens_min'] == 0:
                    tier['input_tokens_max'] = boundary
    if not result:
        raise ValueError('OpenAI tables contain no recognized models')
    return result


def hosted_candidate(row: dict) -> dict:
    p = row['pricing']
    pricing = {}
    for field in ['input', 'output']:
        raw = p['cents_per_'+field+'_token']
        if type(raw) not in (int, float) or not math.isfinite(raw) or raw < 0:
            raise ValueError('invalid hosted input/output price')
        pricing[field] = float(Decimal(str(raw)) * 10000)
    def factor_value(value):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid hosted rate factor')
        return value

    if type(row['max_tokens']) is not int or row['max_tokens'] < 1:
        raise ValueError('invalid hosted context limit')
    for key, field in [('rate_per_input_token_cached', 'cache_read'),
                       ('rate_per_input_token_cache_write', 'cache_write')]:
        if p.get(key) is not None:
            pricing[field] = round(pricing['input'] * factor_value(p[key]), 8)
    explicit = p.get('rate_per_explicit_cache_write_token') or {}
    for ttl, field in [('5m', 'cache_5m_write'), ('1h', 'cache_1h_write')]:
        if ttl in explicit:
            pricing[field] = round(pricing['input'] * factor_value(explicit[ttl]), 8)
    tiers = [{'service_tier': 'standard', 'input_tokens_min': 0,
              'input_tokens_max': None, 'pricing': pricing.copy()}]
    for service in ['priority', 'flex']:
        factor = p.get('rate_per_service_tier_'+service)
        if factor is not None:
            factor_value(factor)
            tiers.append({'service_tier': service, 'input_tokens_min': 0, 'input_tokens_max': None,
                          'pricing': {k: float(Decimal(str(v))*Decimal(str(factor))) for k,v in pricing.items()}})
    return {'pricing': pricing, 'pricing_tiers': tiers, 'context_window': row['max_tokens']}


def normalized_tiers(model: dict) -> list:
    tiers = model.get('pricing_tiers', [{'service_tier': 'standard', 'input_tokens_min': 0,
        'input_tokens_max': None, 'pricing': model['pricing']}])
    return sorted(tiers, key=lambda t: (t['service_tier'], t['input_tokens_min']))


def compare(models: list, openai: dict | None, hosted: list | None, provenance: str) -> dict:
    differences, skipped = [], []
    compared = 0
    hosts = {row['model_name']: row for row in hosted} if hosted is not None else {}
    hosted_ids = set(re.findall(r'^\| `([^`]+)` \| \[Pricing\]\(https://api\.deepinfra\.com/models/list\)',
                                provenance, re.M))
    for model in models:
        mid = model['id']
        expected = None
        if model['provider'] == 'openai' and openai is not None:
            if mid not in openai:
                skipped.append({'id': mid, 'reason': 'not present in supported OpenAI service tables'})
                continue
            ts = openai[mid]
            expected = {'pricing': next(t['pricing'] for t in ts if t['service_tier']=='standard'
                                       and t['input_tokens_min']==0), 'pricing_tiers': ts}
        elif mid in hosted_ids and hosted is not None:
            endpoint = re.search(r'Hosted endpoint: ([^ ]+)\.', model.get('notes',''))
            endpoint = endpoint[1] if endpoint else None
            if endpoint not in hosts:
                skipped.append({'id': mid, 'reason': 'exact serving endpoint missing from metadata'})
                continue
            row = hosts[endpoint]
            if row.get('replaced_by') or row.get('deprecated'):
                differences.append({'id': mid, 'field': 'serving_endpoint', 'catalog': endpoint,
                                    'source': row.get('replaced_by'), 'reason': 'provider marks endpoint retired'})
            expected = hosted_candidate(row)
        if expected is None:
            continue
        compared += 1
        for field, value in expected.items():
            actual = normalized_tiers(model) if field=='pricing_tiers' else model.get(field)
            candidate = normalized_tiers(expected) if field=='pricing_tiers' else value
            if actual != candidate:
                differences.append({'id': mid, 'field': field, 'catalog': actual, 'source': candidate})
    return {'compared_models': compared, 'catalog_models': len(models),
            'uncovered_models': len(models)-compared, 'skipped': skipped, 'differences': differences}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path.home()/'.cache/token-prices/sources')
    parser.add_argument('--cached', action='store_true', help='Audit saved evidence without a fresh HTTP check')
    parser.add_argument('--sources', nargs='+', choices=['openai','deepinfra'], default=['openai','deepinfra'])
    args = parser.parse_args()
    snapshots, errors, evidence = {}, [], []
    for name in args.sources:
        if not args.cached:
            report = fetch(name, args.cache_dir)
            if report['status']=='failed':
                errors.append(report)
                continue
        try:
            folder = args.cache_dir/name
            meta = json.loads((folder/'metadata.json').read_text())
            if meta['url'] != SOURCES[name]:
                raise ValueError('cached source URL does not match configured provider')
            body = (folder/'source.txt').read_text()
            snapshots[name] = parse_openai(body) if name=='openai' else json.loads(body)
            evidence.append({'source': name, 'url': meta['url'], 'http_checked_at': meta['checked_at']})
        except (OSError, ValueError, KeyError) as exc:
            errors.append({'source': name, 'error': str(exc)})
    catalog = json.loads((ROOT/'prices/current.json').read_text())
    try:
        result = compare(catalog['models'], snapshots.get('openai'), snapshots.get('deepinfra'),
                         (ROOT/'prices/sources.md').read_text())
    except (ValueError, KeyError, TypeError) as exc:
        errors.append({'stage': 'comparison', 'error': str(exc)})
        result = {'compared_models': 0, 'catalog_models': len(catalog['models']),
                  'uncovered_models': len(catalog['models']), 'skipped': [], 'differences': []}
    result.update({'mode': 'cached evidence' if args.cached else 'fresh source checks',
                   'evidence': evidence, 'errors': errors})
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if errors else 1 if result['differences'] else 0)


if __name__ == '__main__':
    main()
