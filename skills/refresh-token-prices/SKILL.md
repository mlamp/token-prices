---
name: refresh-token-prices
description: Refresh this token-prices catalog from provider pricing sources, reconcile API IDs and service/context tiers, and verify release readiness. Use for catalog upkeep in mlamp/token-prices, not general model recommendations or billing estimates.
---

Work in the token-prices checkout. Read its README, schema and `prices/sources.md` for the current contract and serving arrangements; do not assume rates from this skill are current.

## Find changes cheaply

Run `python3 scripts/fetch_sources.py` for all sources, or `--sources anthropic openai` for a requested subset. The helper downloads in parallel, keeps raw/readable snapshots in `~/.cache/token-prices/sources`, and uses conditional HTTP requests. Its JSON output identifies new, changed, unchanged and failed sources without loading whole pages into context.

For OpenAI and tracked DeepInfra rows, run `python3 scripts/audit_prices.py` first. It normalizes service/context bands and hosting rate factors, reports only differences with explicit coverage, and never edits rates or `as_of`. Exit 0 means compared records match, 1 means differences, and 2 means fetch/parse failure. `--cached` is an explicitly offline comparison with snapshot timestamps, not fresh verification. Other providers still need model-specific review.

Use `rg` for model IDs, pricing tables, cache columns, retirement text and context boundaries inside changed snapshots. Compare `previous.txt` with `source.txt` for changed sources. Unchanged snapshots narrow the review; they do not prove every catalog row is correct. For newly tracked models, ambiguous tiers, region changes or redirects, open the relevant model documentation even if the general pricing source is unchanged.

Use provider markdown or structured metadata before scraping rendered navigation. OpenAI’s `/api/docs/pricing.md` contains the complete service tables that HTML “All models” controls can hide. Kimi’s current `platform.kimi.ai/docs/pricing/chat.md` contains JSX table literals that can disappear from HTML extraction; inspect those literals as data, never execute page code. DeepInfra’s public `/models/list` returns rate factors, served limits and `replaced_by` targets. Match exact serving endpoints in aliases/provenance; do not substitute advertised weight context for the hosted API limit.

A failed fetch exits 1 and leaves the previous snapshot/date intact. Try official browser retrieval when direct HTTP is blocked. Cohere’s model overview is discovery, not a complete price table: fetch the individual paid model pages and its pricing page. xAI’s model index likewise needs per-model markdown pricing tables. Never use an old cache as fresh verification. Document inaccessible sources and retain the affected model’s `as_of`.

## Reconcile the catalog

Use first-party global/international USD list prices for text/code models; hosted-only models prefer DeepInfra, then OpenRouter, with the exact arrangement recorded. Separate regular list prices from promotions/off-peak discounts in notes. If no undiscounted rate is published, explicitly record the exception instead of inventing a baseline.

Preserve provider punctuation in primary API IDs and move former catalog IDs to aliases. Do not globally replace dots: Claude uses hyphenated versions while GPT versions can contain dots. Generic family aliases follow the current model; version-specific names stay with that version. Confirm redirected endpoints’ actual target and billed rates before consolidating them.

Transcribe each service/context band independently. All bounds are inclusive; convert a strict threshold to the next integer. A standard band starting at zero must exactly equal flat pricing. Bands apply to the full request unless documented otherwise. Missing service/cache fields remain unknown or unavailable; they never inherit rates or become zero. Storage fees are not cache-write token prices.

For changed rows, record source URL, serving provider, region, conditions and verification date in `prices/sources.md`. Advance `as_of` only after verifying that row. Review cache columns and model lifecycle as well as input/output rates. Keep the snapshot files out of Git.

## Verify and deliver

README freshness (catalog edit time, model/provider counts and per-model date range) is generated from the catalog. `current.json` is the moving file, not a guarantee that all rows were checked today. Do not stamp the schema or bulk-update `as_of` after an HTTP fetch. Run `python3 scripts/update_readme.py` after catalog changes so generated metadata remains consistent.

Run `python3 scripts/validate.py`, `python3 scripts/update_readme.py --check`, and `python3 -m unittest discover -s tests`. Add source-backed regression coverage for newly introduced thresholds, changed aliases or cache/service differences. Report substantive changes and unresolved verification gaps briefly.

Commit/PR/merge or release only within the user's requested scope. For an authorized release, merge validated changes first, then dispatch `.github/workflows/release.yml` on `main` with the chosen next stable version. Watch the run and verify the published tag’s catalog/schema/README plus generated links on main. If publishing fails after a tag was pushed, inspect the actual state and publish the existing tag when still authorized; do not move tags or repeatedly retry failures blindly.
