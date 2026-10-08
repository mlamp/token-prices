#!/usr/bin/env python3
"""Prepare release metadata before the release workflow commits and tags it."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

try:
    from .update_readme import ROOT, render_readme, version_tuple
except ImportError:
    from update_readme import ROOT, render_readme, version_tuple


def prepare(version: str, root: Path = ROOT) -> None:
    requested = version_tuple(version)
    path = root / 'release.json'
    metadata = json.loads(path.read_text())
    if requested <= version_tuple(metadata['latest']['tag']):
        raise ValueError('release version must be newer than the latest stable release')
    tags = subprocess.check_output(['git', 'tag', '--list'], cwd=root, text=True).splitlines()
    if version in tags:
        raise ValueError(f'tag {version} already exists; published tags must not move')
    catalog = json.loads((root / 'prices/current.json').read_text())
    metadata['latest'] = {'tag': version, 'schema_version': catalog['schema_version']}
    readme = root / 'README.md'
    rendered = render_readme(readme.read_text(), metadata, catalog)
    # Compute and validate both files before writing either one.
    path.write_text(json.dumps(metadata, indent=2) + '\n')
    readme.write_text(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', help='New stable tag, e.g. v0.2.0')
    args = parser.parse_args()
    try:
        prepare(args.version)
    except (ValueError, KeyError) as exc:
        parser.exit(1, f'Release preparation: {exc}\n')
    print(f'Release metadata prepared for {args.version}')


if __name__ == '__main__':
    main()
