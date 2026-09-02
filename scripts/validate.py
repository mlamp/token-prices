#!/usr/bin/env python3
"""Validate prices/current.json: schema shape, alias uniqueness, PII scan."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "prices" / "current.json"
SCHEMA = ROOT / "schema" / "token-prices.schema.json"
SCAN_PATHS = [
    ROOT / "prices",
    ROOT / "README.md",
    ROOT / "prices" / "sources.md",
]

PROVIDERS = {
    "anthropic",
    "openai",
    "google",
    "xai",
    "meta",
    "moonshot",
    "deepseek",
    "qwen",
    "zhipu",
    "other",
}
STATUSES = {"current", "legacy", "preview"}

# Public-repo PII / secret residue. Fail closed on hits in scanned text files.
PII_PATTERNS = [
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "email"),
    (re.compile(r"/Users/"), "home path"),
    (re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}"), "api key fragment"),
    (re.compile(r"(?i)\bcp_[A-Za-z0-9_-]{16,}"), "consumer token"),
    (re.compile(r"(?i)\breq_[A-Za-z0-9_-]{8,}"), "request id"),
    (re.compile(r"(?i)\bwrkspc_[A-Za-z0-9_-]+"), "workspace id"),
]


def fail(msg: str) -> None:
    print(f"validate: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_catalog() -> dict:
    if not CATALOG.is_file():
        fail(f"missing {CATALOG}")
    try:
        return json.loads(CATALOG.read_text())
    except json.JSONDecodeError as e:
        fail(f"catalog JSON: {e}")


def check_shape(doc: dict) -> None:
    if doc.get("schema_version") != 1:
        fail("schema_version must be 1")
    if doc.get("currency") != "USD":
        fail("currency must be USD")
    if doc.get("unit") != "usd_per_million_tokens":
        fail("unit must be usd_per_million_tokens")
    if not isinstance(doc.get("updated_at"), str) or not doc["updated_at"]:
        fail("updated_at required")
    models = doc.get("models")
    if not isinstance(models, list) or not models:
        fail("models must be a non-empty array")

    ids: set[str] = set()
    aliases: dict[str, str] = {}
    for i, m in enumerate(models):
        if not isinstance(m, dict):
            fail(f"models[{i}] not an object")
        mid = m.get("id")
        if not isinstance(mid, str) or not re.match(r"^[a-z0-9][a-z0-9._-]*$", mid):
            fail(f"models[{i}].id invalid: {mid!r}")
        if mid in ids:
            fail(f"duplicate id {mid}")
        ids.add(mid)
        if m.get("provider") not in PROVIDERS:
            fail(f"{mid}: bad provider {m.get('provider')!r}")
        pricing = m.get("pricing")
        if not isinstance(pricing, dict):
            fail(f"{mid}: pricing required")
        for k in ("input", "output"):
            if not isinstance(pricing.get(k), (int, float)) or pricing[k] < 0:
                fail(f"{mid}: pricing.{k} must be number >= 0")
        for k in ("cache_read", "cache_write", "cache_5m_write", "cache_1h_write"):
            if k in pricing and (not isinstance(pricing[k], (int, float)) or pricing[k] < 0):
                fail(f"{mid}: pricing.{k} must be number >= 0")
        if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", str(m.get("as_of", ""))):
            fail(f"{mid}: as_of must be YYYY-MM-DD")
        status = m.get("status", "current")
        if status not in STATUSES:
            fail(f"{mid}: bad status {status!r}")
        if "context_window" in m:
            cw = m["context_window"]
            if not isinstance(cw, int) or cw < 1:
                fail(f"{mid}: context_window must be integer >= 1")
        for a in m.get("aliases") or []:
            if not isinstance(a, str) or not a:
                fail(f"{mid}: empty alias")
            key = a.lower()
            if key in aliases and aliases[key] != mid:
                fail(f"alias {a!r} claimed by {aliases[key]} and {mid}")
            if key in ids and key != mid:
                fail(f"alias {a!r} collides with id {key}")
            aliases[key] = mid
            if key == mid:
                continue
            # id itself need not be listed as alias
    if not SCHEMA.is_file():
        fail(f"missing schema {SCHEMA}")


def scan_pii() -> None:
    files: list[Path] = []
    for p in SCAN_PATHS:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*")))
    for path in files:
        if not path.is_file() or path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            continue
        text = path.read_text(errors="replace")
        for pat, label in PII_PATTERNS:
            m = pat.search(text)
            if m:
                fail(f"PII scan hit ({label}) in {path.relative_to(ROOT)}: {m.group(0)!r}")


def main() -> None:
    doc = load_catalog()
    check_shape(doc)
    scan_pii()
    print(f"validate: OK ({len(doc['models'])} models)")


if __name__ == "__main__":
    main()
