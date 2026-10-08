# token-prices

Public **list-price** catalog for LLM tokens (USD per million tokens), with
aliases so consumers can match short model names.

This is **not** a billing invoice. Rates are transcribed from public pricing
pages and aggregators; they drift. Prefer vendor pages when they disagree.

## Consume

<!-- generated:consume:start -->
Latest stable release: [v0.1.1](https://github.com/mlamp/token-prices/releases/tag/v0.1.1)
(schema v1).

Pinned catalog:

```text
https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/prices/current.json
```

[Schema for v0.1.1](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/schema/token-prices.schema.json).

Use `main` for the moving schema v2 catalog (may change without a tag):

```text
https://raw.githubusercontent.com/mlamp/token-prices/main/prices/current.json
```

[Current schema](schema/token-prices.schema.json).

Historical schema v1 compatibility: [v0.1.1 catalog](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/prices/current.json)
and [schema](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/schema/token-prices.schema.json).
Consumers that require v1 should stay pinned. Historical catalogs are not updated.
<!-- generated:consume:end -->

## Shape

Each model has `id`, `provider`, optional `aliases` / `context_window`, and
`pricing.input` / `pricing.output` (required). Optional cache fields:
`cache_read`, `cache_write`, `cache_5m_write`, `cache_1h_write`.

<!-- generated:schema-version:start -->
`schema_version` is `2`. `status` is `current` | `legacy` | `preview`.
<!-- generated:schema-version:end -->
`provider` supports OpenAI, Anthropic, Google, xAI, Meta, Moonshot, DeepSeek,
Qwen, Zhipu, Mistral, Cohere, and `other`. See the
[ID and alias convention](#model-ids-and-aliases) when matching model names.
`provider` identifies the model developer; hosted prices and served context
limits are attributed to the serving provider in [provenance](prices/sources.md).
`as_of` is per-model verification, while `updated_at` records the catalog edit.
Dated rows with failed verification remain explicitly noted and may be stale.

Optional `pricing_tiers` contains complete rate objects with `service_tier`,
`input_tokens_min`, `input_tokens_max`, and `pricing`. Services are `standard`,
`batch`, `flex`, `priority`, `fast`, and `ultrafast`; only documented rates appear.
Bounds are inclusive integers. `null` means no upper pricing boundary, not an
unlimited model context. A model’s `context_window` remains a separate limit.
Every tiered model has a standard band starting at zero, and flat `pricing`
exactly equals that band, including cache fields.

Select the requested service and the band containing the full input-token
count, including cached input. Apply its rates to the full request; the bands
are not graduated charges. For example, GPT-6.1 Sol standard input/output costs
$2/$10 through 272,000 input tokens and $4/$15 at 272,001. Its short-context batch
rates are $1/$5. xAI’s higher band starts at exactly 200,000 tokens.

```python
def select_pricing(model, service_tier, input_tokens):
    if type(input_tokens) is not int or input_tokens < 0:
        raise ValueError("input_tokens must be a nonnegative integer")
    if input_tokens > model.get("context_window", float("inf")):
        raise ValueError("input exceeds the catalog context limit")
    if "pricing_tiers" not in model:
        if service_tier == "standard":
            return model["pricing"]
    else:
        for tier in model["pricing_tiers"]:
            upper = tier["input_tokens_max"]
            if (tier["service_tier"] == service_tier
                    and input_tokens >= tier["input_tokens_min"]
                    and (upper is None or input_tokens <= upper)):
                return tier["pricing"]
    raise LookupError("No documented pricing for this service and input count")
```

No matching band or service means unknown or unavailable; do not fall back to
standard pricing. Each tier requires input/output rates. Cache fields never
inherit from flat pricing or another tier. Missing cache rates mean unknown or
unavailable, not free. Regular list prices are the baseline; promotions,
off-peak discounts, regional premiums, cache storage and tool charges are
explained in notes/provenance rather than silently applied. GPT-5.6 Sol uses
the published promotional table rates because its source supplies no separate
undiscounted rate; that exception is recorded in its notes.

## Model IDs and aliases

Use a provider’s documented first-party API model ID as the primary `id` when
available, preserving its punctuation. Anthropic uses `claude-opus-5-5` and
`claude-fable-5-1`; OpenAI uses `gpt-6.1-sol`. Do not convert every period to a
hyphen. When an entry represents a documented dated snapshot, use that full
snapshot ID, such as `claude-haiku-4-5-20251001`.

`aliases` includes provider endpoint aliases, short names, and former catalog
IDs for compatibility. Resolve a name against `id` and `aliases`
case-insensitively. For example, `claude-opus-5.5`, `opus-5.5`, `opus-5-5`, and
`opus` resolve to `claude-opus-5-5`. Aliases are catalog lookup names; some short
or historical spellings are not accepted in provider API requests.

Generic family aliases follow the current model. Version-specific aliases
remain attached to that version. After a documented endpoint redirect, its
old name resolves to the model actually served, with the arrangement recorded
in [provenance](prices/sources.md).

Hosted entries can use a developer-scoped catalog ID when the serving endpoint
is host-specific or contains characters outside the schema’s ID pattern. Use
the exact endpoint name documented in aliases/provenance for those requests.
Unverified historical entries retain their prior IDs and explicit notes.

## Validate

```bash
python3 scripts/validate.py
python3 scripts/update_readme.py --check
python3 -m unittest discover -s tests
```

Checks the catalog schema, finite nonnegative prices, tier bounds/overlap, flat/tier
equality, unique ids/aliases (case-insensitive aliases), and a small PII scan
on published text (no emails, home paths, or token-shaped strings).

## Refresh prices

Use the [refresh-token-prices skill](skills/refresh-token-prices/SKILL.md) for
provider-source checks, price/tier updates, provenance and verification.
`python3 scripts/fetch_sources.py` caches readable snapshots, fetches sources
in parallel and reports changed/unchanged/failed pages. Use `--sources openai
anthropic` for a targeted check. It does not edit the catalog or treat a failed
fetch as fresh verification. Follow model-specific sources where the provider
index omits prices or alternate service tables.

## Release

Run the [Release workflow](https://github.com/mlamp/token-prices/actions/workflows/release.yml)
from `main`, supplying the next stable `vMAJOR.MINOR.PATCH` version. It validates
the catalog, runs tests, updates `release.json` and the generated README blocks,
commits them, then pushes `main` and the tag together and publishes a GitHub release.
The tag therefore includes its own correct version, catalog URL and schema URL.

`release.json` records the latest stable release and the historical v1 pin.
The moving schema version comes from `prices/current.json`. To regenerate the
README locally, run `python3 scripts/update_readme.py`. CI rejects stale
metadata on pull requests and pushes to `main`; leave generated blocks to the script.
Use the workflow for releases instead of creating tags or releases manually.

If publishing fails after the tag was pushed, publish that existing tag with
`gh release create <tag> --verify-tag --generate-notes --latest`; do not move it.

## Provenance

See [`prices/sources.md`](prices/sources.md).

## License

MIT
