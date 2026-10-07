#!/usr/bin/env python3
"""Validate prices/current.json: schema shape, alias uniqueness, PII scan."""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "prices" / "current.json"
SCHEMA = ROOT / "schema" / "token-prices.schema.json"
SCAN_PATHS = [
    ROOT / "prices",
    ROOT / "README.md",
    ROOT / "prices" / "sources.md",
]

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


def check_schema(value, spec: dict, schema: dict, path: str) -> None:
    """Apply the JSON Schema keywords used by this catalog, without dependencies."""
    if "$ref" in spec:
        check_schema(value, schema["$defs"][spec["$ref"].split("/")[-1]], schema, path)
        return
    types = spec.get("type", [])
    if isinstance(types, str):
        types = [types]
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float) and (type(value) is int or math.isfinite(value)),
        "null": value is None,
    }
    if types and not any(matches[t] for t in types):
        fail(f"{path}: expected {' or '.join(types)}")
    if "const" in spec and (type(value) is not type(spec["const"]) or value != spec["const"]):
        fail(f"{path}: must be {spec['const']!r}")
    if "enum" in spec and value not in spec["enum"]:
        fail(f"{path}: invalid value {value!r}")
    if type(value) in (int, float) and value < spec.get("minimum", -math.inf):
        fail(f"{path}: below minimum {spec['minimum']}")
    if isinstance(value, str):
        if len(value) < spec.get("minLength", 0):
            fail(f"{path}: empty string")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            fail(f"{path}: invalid format")
        if spec.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if "T" not in value or parsed.tzinfo is None:
                    raise ValueError
            except ValueError:
                fail(f"{path}: expected date-time with timezone")
    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                fail(f"{path}: missing {key}")
        props = spec.get("properties", {})
        for key, item in value.items():
            if key in props:
                check_schema(item, props[key], schema, f"{path}.{key}")
            elif spec.get("additionalProperties") is False:
                fail(f"{path}: unknown field {key}")
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            fail(f"{path}: too few items")
        if spec.get("uniqueItems") and any(item in value[:i] for i, item in enumerate(value)):
            fail(f"{path}: duplicate items")
        for i, item in enumerate(value):
            check_schema(item, spec["items"], schema, f"{path}[{i}]")


def check_shape(doc: dict) -> None:
    if not SCHEMA.is_file():
        fail(f"missing schema {SCHEMA}")
    schema = json.loads(SCHEMA.read_text())
    check_schema(doc, schema, schema, "catalog")
    # Register all IDs first so collisions are independent of model order.
    ids: set[str] = set()
    for model in doc["models"]:
        mid = model["id"]
        if mid in ids:
            fail(f"duplicate id {mid}")
        ids.add(mid)
    aliases: dict[str, str] = {}
    for model in doc["models"]:
        mid = model["id"]
        try:
            date.fromisoformat(model["as_of"])
        except ValueError:
            fail(f"{mid}: as_of must be a valid date")
        local_aliases: set[str] = set()
        for alias in model.get("aliases", []):
            key = alias.lower()
            if key in local_aliases:
                fail(f"{mid}: duplicate alias {alias!r}")
            local_aliases.add(key)
            if key in ids and key != mid:
                fail(f"alias {alias!r} collides with id {key}")
            if key in aliases and aliases[key] != mid:
                fail(f"alias {alias!r} claimed by {aliases[key]} and {mid}")
            aliases[key] = mid
        if "pricing_tiers" not in model:
            continue
        standard = [t for t in model["pricing_tiers"]
                    if t["service_tier"] == "standard" and t["input_tokens_min"] == 0]
        if len(standard) != 1:
            fail(f"{mid}: tiers require exactly one standard band starting at zero")
        if model["pricing"] != standard[0]["pricing"]:
            fail(f"{mid}: flat pricing must equal the standard band starting at zero")
        bands: dict[str, list] = {}
        for tier in model["pricing_tiers"]:
            lower, upper = tier["input_tokens_min"], tier["input_tokens_max"]
            if upper is not None and upper < lower:
                fail(f"{mid}: reversed pricing band")
            bands.setdefault(tier["service_tier"], []).append((lower, upper))
        for service, ranges in bands.items():
            ranges.sort(key=lambda r: r[0])
            for (_, upper), (lower, _) in zip(ranges, ranges[1:]):
                if upper is None or lower <= upper:
                    fail(f"{mid}: overlapping {service} pricing bands")


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
