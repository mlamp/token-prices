# token-prices

Public **list-price** catalog for LLM tokens (USD per million tokens), with
aliases so consumers can match short model names.

This is **not** a billing invoice. Rates are transcribed from public pricing
pages and aggregators; they drift. Prefer vendor pages when they disagree.

## Consume

Historical schema v1 catalog (pinned, no further updates):

```text
https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/prices/current.json
```

Use `main` for the moving schema v2 catalog (may change without a tag):

```text
https://raw.githubusercontent.com/mlamp/token-prices/main/prices/current.json
```

The [pinned v1 schema](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/schema/token-prices.schema.json)
is available under the same `v0.1.1` tag. Consumers that
require v1 should stay pinned; v2 retains flat fields but changes the version
and adds providers and optional tiers.

Schema: [`schema/token-prices.schema.json`](schema/token-prices.schema.json).

## Shape

Each model has `id`, `provider`, optional `aliases` / `context_window`, and
`pricing.input` / `pricing.output` (required). Optional cache fields:
`cache_read`, `cache_write`, `cache_5m_write`, `cache_1h_write`.

`schema_version` is `2`. `status` is `current` | `legacy` | `preview`.
`provider` supports OpenAI, Anthropic, Google, xAI, Meta, Moonshot, DeepSeek,
Qwen, Zhipu, Mistral, Cohere, and `other`. Catalog IDs can be normalized names;
use the documented endpoint names in aliases or provenance for API requests.
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

## Validate

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests
```

Checks the v2 schema, finite nonnegative prices, tier bounds/overlap, flat/tier
equality, unique ids/aliases (case-insensitive aliases), and a small PII scan
on published text (no emails, home paths, or token-shaped strings).

## Provenance

See [`prices/sources.md`](prices/sources.md).

## License

MIT
