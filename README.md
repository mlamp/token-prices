# token-prices

Public **list-price** catalog for LLM tokens (USD per million tokens), with
aliases so consumers can match short model names.

This is **not** a billing invoice. Rates are transcribed from public pricing
pages and aggregators; they drift. Prefer vendor pages when they disagree.

## Consume

Stable tagged file:

```text
https://raw.githubusercontent.com/mlamp/token-prices/v0.1.0/prices/current.json
```

Or `main` for the moving tip (may change without a tag).

Schema: [`schema/token-prices.schema.json`](schema/token-prices.schema.json).

## Shape

Each model has `id`, `provider`, optional `aliases` / `context_window`, and
`pricing.input` / `pricing.output` (required). Optional cache fields:
`cache_read`, `cache_write`, `cache_5m_write`, `cache_1h_write`.

`status` is `current` | `legacy` | `preview`.

## Validate

```bash
python3 scripts/validate.py
```

Checks catalog shape, unique ids/aliases, and a small PII scan on published
text (no emails, home paths, or token-shaped strings).

## Provenance

See [`prices/sources.md`](prices/sources.md).

## License

MIT
