# token-prices

A small public catalog of LLM token list prices in USD per million tokens, published as
JSON with aliases so you can match short model names like `opus` or `opus-5.5`.

Prices are transcribed from public pricing pages and aggregators, so treat them as
estimates. Each model carries its own verification date, and vendor pages win when they
disagree.

## Get the JSON

<!-- generated:consume:start -->
Latest stable release: [v0.2.0](https://github.com/mlamp/token-prices/releases/tag/v0.2.0) (schema v2).

Pinned catalog:

```text
https://raw.githubusercontent.com/mlamp/token-prices/v0.2.0/prices/current.json
```

[Schema for v0.2.0](https://raw.githubusercontent.com/mlamp/token-prices/v0.2.0/schema/token-prices.schema.json).

Moving catalog on `main` (schema v2, may change without a tag):

```text
https://raw.githubusercontent.com/mlamp/token-prices/main/prices/current.json
```

[Current schema](schema/token-prices.schema.json).

For schema v1, use the [v0.1.1 catalog](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/prices/current.json)
and its [schema](https://raw.githubusercontent.com/mlamp/token-prices/v0.1.1/schema/token-prices.schema.json).
Historical catalogs are not updated.
<!-- generated:consume:end -->

## Freshness

<!-- generated:freshness:start -->
Catalog edited: `2026-10-08T06:27:55Z`.

74 models across 11 providers. Model `as_of` dates range from `2026-09-01` to `2026-10-08`.

`current.json` is the moving catalog, not a promise that every price was verified today.
Check each model's `as_of` date, `status`, notes and [source provenance](prices/sources.md).
<!-- generated:freshness:end -->

## Reading an entry

Each model has an `id`, a `provider`, and `pricing.input` / `pricing.output`. Optional
fields add `aliases`, `context_window`, cache rates (`cache_read`, `cache_write`,
`cache_5m_write`, `cache_1h_write`) and `pricing_tiers`. The
[schema](schema/token-prices.schema.json) has the full definition.

<!-- generated:schema-version:start -->
`schema_version` is `2`. `status` is `current` | `legacy` | `preview`.
<!-- generated:schema-version:end -->

- Prices use regular list rates where available. Notes explain promotions, regional
  premiums, off-peak discounts and additional charges.
- `provider` names the model developer. For hosted models, [sources](prices/sources.md)
  identify the serving provider whose prices and context limits are listed.
- `as_of` records verification per model; `updated_at` records a catalog edit. Rows
  with failed verification retain their earlier dates and explain the gap in notes.
- A missing cache rate means unknown or unavailable, never free. Cache rates do
  not inherit from flat pricing or another tier.

### Tiered pricing

Some models price by service tier (`standard`, `batch`, `flex`, `priority`, `fast`,
`ultrafast`) and by input size. Each entry in `pricing_tiers` is a complete rate object
with inclusive `input_tokens_min` / `input_tokens_max` bounds. A `null` upper bound
means no pricing boundary, not unlimited context. Only documented rates appear.

To price a request, pick the service tier and the band that contains the full
input-token count, cached input included, then apply that band's rates to the whole
request. Bands are not graduated. For example, GPT-6.1 Sol standard input/output costs
$2/$10 up to 272,000 input tokens and $4/$15 from 272,001. If no band or service
matches, the price is unknown. Do not fall back to standard. Flat `pricing` equals the
standard band that starts at zero, cache fields included. If a model has no
`pricing_tiers`, flat pricing covers standard service only.

## Match a model name

Match `id` and `aliases` case-insensitively. For example, `claude-opus-5.5`, `opus-5.5`,
`opus-5-5` and `opus` all resolve to `claude-opus-5-5`. An alias is a catalog lookup
name; it may not be accepted in a provider API request.

Primary IDs follow provider spelling where available: `claude-opus-5-5`, `gpt-6.1-sol`,
or a dated snapshot such as `claude-haiku-4-5-20251001`. Generic names follow the
current model; version names stay with that version. Redirected endpoints follow the
model actually served. For hosted models, use the serving endpoint recorded in
[sources](prices/sources.md).

## Sources

The [source records](prices/sources.md) identify each model's pricing source and serving
arrangement. They distinguish first-party API documentation, hosting providers and
retained historical aggregator entries. An aggregator price does not establish the price
charged by the model's own provider.

## Contributing

Validate the catalog and generated README metadata:

```bash
python3 scripts/validate.py
python3 scripts/update_readme.py --check
python3 -m unittest discover -s tests
```

To refresh prices, follow the [refresh-token-prices skill](skills/refresh-token-prices/SKILL.md). Two helpers support it. `python3 scripts/fetch_sources.py` snapshots provider pages and reports which changed or failed.
`python3 scripts/audit_prices.py` diffs documented OpenAI service tables and tracked
DeepInfra endpoints against the catalog. Neither edits the catalog or advances `as_of`;
that happens only after per-model verification.

Regenerate the README blocks with `python3 scripts/update_readme.py`. CI rejects stale
metadata.

## Release

Run the [Release workflow](https://github.com/mlamp/token-prices/actions/workflows/release.yml) from
`main` with the next stable `vMAJOR.MINOR.PATCH` version. It validates, tests, updates
`release.json` and the README, pushes the tag and publishes a GitHub release. Do not
create tags or releases by hand.

If publishing fails after the tag was pushed, publish that tag instead of moving it:

```bash
gh release create <tag> --verify-tag --generate-notes --latest
```

## License

MIT
