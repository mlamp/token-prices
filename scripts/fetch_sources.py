#!/usr/bin/env python3
"""Cache provider source snapshots and report changes without editing prices."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SOURCES = {
    'openai': 'https://developers.openai.com/api/docs/pricing.md',
    'anthropic': 'https://platform.claude.com/docs/en/about-claude/pricing',
    'google': 'https://ai.google.dev/gemini-api/docs/pricing',
    'xai': 'https://docs.x.ai/developers/models',
    'moonshot': 'https://platform.kimi.ai/docs/pricing/chat.md',
    'deepseek': 'https://api-docs.deepseek.com/quick_start/pricing/',
    'qwen': 'https://www.alibabacloud.com/help/en/model-studio/model-pricing',
    'zhipu': 'https://docs.z.ai/guides/overview/pricing.md',
    'mistral': 'https://docs.mistral.ai/inference/pricing',
    'cohere': 'https://docs.cohere.com/docs/models',
    'deepinfra': 'https://api.deepinfra.com/models/list',
}


class PageText(HTMLParser):
    """Remove executable/style content while retaining table and paragraph breaks."""
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1
        elif not self.hidden and tag in {'p', 'tr', 'h1', 'h2', 'h3', 'li', 'br'}:
            self.parts.append('\n')
        elif not self.hidden and tag in {'td', 'th'}:
            self.parts.append(' | ')

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {'p', 'tr', 'h1', 'h2', 'h3', 'li'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def readable(body: str, content_type: str) -> str:
    if 'json' in content_type:
        return json.dumps(json.loads(body), indent=2, ensure_ascii=False) + '\n'
    if 'html' in content_type:
        parser = PageText()
        parser.feed(body)
        lines = [re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.parts).splitlines()]
        return '\n'.join(line for line in lines if line) + '\n'
    return body


def fetch(name: str, cache: Path, force: bool = False) -> dict:
    url = SOURCES[name]
    folder = cache / name
    metadata_path = folder / 'metadata.json'
    raw_path, text_path = folder / 'source.raw', folder / 'source.txt'
    previous = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    if previous.get('url') != url:
        previous = {}
    headers = {'User-Agent': 'token-prices-source-check/1.0'}
    if previous and not force and raw_path.exists() and text_path.exists():
        for key, header in [('etag', 'If-None-Match'), ('last_modified', 'If-Modified-Since')]:
            if previous.get(key):
                headers[header] = previous[key]
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
            body = response.read().decode('utf-8')
            content_type = response.headers.get('Content-Type', '')
            text = readable(body, content_type)
            digest = hashlib.sha256(text.encode()).hexdigest()
            metadata = {'url': url, 'resolved_url': response.geturl(), 'checked_at': checked_at,
                        'sha256': digest, 'etag': response.headers.get('ETag'),
                        'last_modified': response.headers.get('Last-Modified')}
        folder.mkdir(parents=True, exist_ok=True)
        changed = digest != previous.get('sha256')
        if changed and text_path.exists():
            (folder / 'previous.txt').write_text(text_path.read_text())
        raw_path.write_text(body)
        text_path.write_text(text)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        status = 'new' if not previous else 'changed' if changed else 'unchanged'
        return {'source': name, 'url': url, 'status': status, 'checked_at': checked_at,
                'snapshot': str(text_path), 'previous': str(folder / 'previous.txt') if changed and previous else None}
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and previous and raw_path.exists() and text_path.exists():
            previous['checked_at'] = checked_at
            metadata_path.write_text(json.dumps(previous, indent=2) + '\n')
            return {'source': name, 'url': url, 'status': 'unchanged',
                    'checked_at': checked_at, 'snapshot': str(text_path)}
        return {'source': name, 'url': url, 'status': 'failed', 'error': f'HTTP {exc.code}'}
    except (OSError, ValueError) as exc:
        return {'source': name, 'url': url, 'status': 'failed', 'error': str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', nargs='+', choices=sorted(SOURCES), default=list(SOURCES))
    parser.add_argument('--cache-dir', type=Path, default=Path.home() / '.cache/token-prices/sources')
    parser.add_argument('--force', action='store_true', help='Fetch fresh bodies instead of conditional requests')
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda name: fetch(name, args.cache_dir, args.force), args.sources))
    print(json.dumps(reports, indent=2))
    # Failed downloads are explicit and do not advance cached verification dates.
    if any(report['status'] == 'failed' for report in reports):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
