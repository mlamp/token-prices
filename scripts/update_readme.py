#!/usr/bin/env python3
"""Generate release links and the current schema version in README.md."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version_tuple(tag: str) -> tuple[int, ...]:
    match = VERSION.fullmatch(tag)
    if not match:
        raise ValueError("release version must be a stable vMAJOR.MINOR.PATCH tag")
    return tuple(map(int, match.groups()))


def replace_block(text: str, name: str, content: str) -> str:
    start, end = f"<!-- generated:{name}:start -->", f"<!-- generated:{name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"README must contain exactly one {name} marker pair")
    lower, upper = text.index(start), text.index(end)
    if upper < lower:
        raise ValueError(f"README {name} markers are reversed")
    return text[:lower] + start + "\n" + content.rstrip() + "\n" + text[upper:]


def render_readme(text: str, metadata: dict, catalog: dict) -> str:
    repository = metadata['repository']
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    latest, legacy = metadata['latest'], metadata['legacy_v1']
    for entry in (latest, legacy):
        version_tuple(entry['tag'])
        if type(entry['schema_version']) is not int or entry['schema_version'] < 1:
            raise ValueError("release schema_version must be a positive integer")
    if legacy['schema_version'] != 1:
        raise ValueError("legacy_v1 must pin schema v1")
    raw = f"https://raw.githubusercontent.com/{repository}"
    tag, schema = latest['tag'], latest['schema_version']
    legacy_tag = legacy['tag']
    current_schema = catalog['schema_version']
    content = f'''Latest stable release: [{tag}](https://github.com/{repository}/releases/tag/{tag})
(schema v{schema}).

Pinned catalog:

```text
{raw}/{tag}/prices/current.json
```

[Schema for {tag}]({raw}/{tag}/schema/token-prices.schema.json).

Use `main` for the moving schema v{current_schema} catalog (may change without a tag):

```text
{raw}/main/prices/current.json
```

[Current schema](schema/token-prices.schema.json).

Historical schema v1 compatibility: [{legacy_tag} catalog]({raw}/{legacy_tag}/prices/current.json)
and [schema]({raw}/{legacy_tag}/schema/token-prices.schema.json).
Consumers that require v1 should stay pinned. Historical catalogs are not updated.
'''
    text = replace_block(text, 'consume', content)
    return replace_block(text, 'schema-version',
                         f"`schema_version` is `{current_schema}`. `status` is `current` | `legacy` | `preview`.")


def update(root: Path = ROOT, check: bool = False) -> bool:
    path = root / 'README.md'
    original = path.read_text()
    rendered = render_readme(original, json.loads((root / 'release.json').read_text()),
                             json.loads((root / 'prices/current.json').read_text()))
    if check:
        return original == rendered
    if original != rendered:
        path.write_text(rendered)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated README metadata is stale')
    args = parser.parse_args()
    try:
        if not update(check=args.check):
            parser.exit(1, 'README metadata is stale; run python3 scripts/update_readme.py\n')
    except (ValueError, KeyError) as exc:
        parser.exit(1, f'README metadata: {exc}\n')
    print('README metadata: OK')


if __name__ == '__main__':
    main()
