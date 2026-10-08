"""Catalog contract and source-backed pricing regression tests (stdlib only)."""
import copy
import contextlib
import io
import json
import unittest

from scripts.validate import CATALOG, check_shape


def band(service='standard', lower=0, upper=None, pricing=None):
    return {'service_tier': service, 'input_tokens_min': lower,
            'input_tokens_max': upper,
            'pricing': pricing if pricing is not None else {'input': 2, 'output': 10}}


def document():
    return {'schema_version': 2, 'currency': 'USD', 'unit': 'usd_per_million_tokens',
            'updated_at': '2026-10-07T00:00:00Z',
            'models': [{'id': 'example', 'provider': 'openai',
                        'pricing': {'input': 2, 'output': 10},
                        'pricing_tiers': [band()], 'as_of': '2026-10-07'}]}


class ValidationTests(unittest.TestCase):
    def reject(self, doc, message=None):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as exc:
                check_shape(doc)
        self.assertEqual(exc.exception.code, 1)
        if message:
            self.assertIn(message, stderr.getvalue())

    def test_flat_catalog_without_tiers(self):
        doc = document()
        del doc['models'][0]['pricing_tiers']
        check_shape(doc)

    def test_adjacent_inclusive_bands_and_independent_services(self):
        doc = document()
        doc['models'][0]['pricing_tiers'] = [band(upper=272000),
            band(lower=272001), band('batch', pricing={'input': 1, 'output': 5})]
        check_shape(doc)

    def test_overlapping_and_duplicate_bands(self):
        for ranges in [[band(upper=272000), band(lower=272000)],
                       [band(), band(lower=272001)], [band(), band('batch'), band('batch')],
                       [band(), band('batch', upper=100), band('batch', lower=50)]]:
            with self.subTest(ranges=ranges):
                doc = document()
                doc['models'][0]['pricing_tiers'] = ranges
                self.reject(doc, 'overlapping')

    def test_unsorted_bands(self):
        doc = document()
        doc['models'][0]['pricing_tiers'] = [band(lower=11), band(upper=10)]
        check_shape(doc)
        doc['models'][0]['pricing_tiers'][1]['input_tokens_max'] = 11
        self.reject(doc, 'overlapping')

    def test_reversed_band(self):
        doc = document()
        doc['models'][0]['pricing_tiers'].append(band('batch', 10, 9))
        self.reject(doc, 'reversed')

    def test_missing_standard_zero_band(self):
        for bands in [[band('batch')], [band(lower=1)], []]:
            doc = document()
            doc['models'][0]['pricing_tiers'] = bands
            self.reject(doc)

    def test_flat_tier_mismatch_including_cache_fields(self):
        for pricing in [{'input': 3, 'output': 10},
                        {'input': 2, 'output': 10, 'cache_read': .1}]:
            doc = document()
            doc['models'][0]['pricing'] = pricing
            self.reject(doc, 'flat pricing must equal')

    def test_bad_prices_on_flat_and_tier(self):
        for field in ['input', 'output', 'cache_read', 'cache_write',
                      'cache_5m_write', 'cache_1h_write']:
            for bad in [-1, True, None, '2', float('nan'), float('inf'), -float('inf')]:
                for tier in [False, True]:
                    with self.subTest(field=field, bad=bad, tier=tier):
                        doc = document()
                        target = doc['models'][0]['pricing_tiers'][0]['pricing'] if tier else doc['models'][0]['pricing']
                        target[field] = bad
                        self.reject(doc)

    def test_tiers_require_complete_input_output_without_inheritance(self):
        for missing in ['input', 'output']:
            doc = document()
            extra = band('batch', pricing={'input': 1, 'output': 5})
            del extra['pricing'][missing]
            doc['models'][0]['pricing_tiers'].append(extra)
            self.reject(doc, 'missing '+missing)
        doc = document()
        doc['models'][0]['pricing']['cache_read'] = .1
        doc['models'][0]['pricing_tiers'][0]['pricing']['cache_read'] = .1
        doc['models'][0]['pricing_tiers'].append(band('batch'))
        check_shape(doc)
        self.assertNotIn('cache_read', doc['models'][0]['pricing_tiers'][1]['pricing'])

    def test_invalid_range_types_and_service(self):
        for field, bad_values in [('input_tokens_min', [True, .5, -1, None]),
                                  ('input_tokens_max', [False, 1.5, -1, '100']),
                                  ('service_tier', ['default', None, 1])]:
            for value in bad_values:
                doc = document()
                doc['models'][0]['pricing_tiers'][0][field] = value
                self.reject(doc)

    def test_alias_collision_with_later_id_in_either_order(self):
        doc = document()
        second = copy.deepcopy(doc['models'][0])
        second['id'] = 'later'
        doc['models'][0]['aliases'] = ['LATER']
        doc['models'].append(second)
        self.reject(doc, 'collides with id')
        doc['models'].reverse()
        self.reject(doc, 'collides with id')

    def test_alias_and_id_duplicates(self):
        doc = document()
        doc['models'].append(copy.deepcopy(doc['models'][0]))
        self.reject(doc, 'duplicate id')
        doc['models'][1]['id'] = 'second'
        for m in doc['models']:
            m['aliases'] = ['shared']
        self.reject(doc, 'claimed by')
        doc = document()
        doc['models'][0]['aliases'] = ['Same', 'same']
        self.reject(doc, 'duplicate alias')

    def test_schema_shape_and_dates(self):
        for field, value in [('aliases', 'abc'), ('aliases', None),
                             ('context_window', True), ('as_of', '2026-02-30'),
                             ('id', 'example\n'), ('pricing', {'input': 1}),
                             ('unexpected', 1)]:
            doc = document()
            doc['models'][0][field] = value
            self.reject(doc)
        for field, value in [('schema_version', 1), ('schema_version', True),
                             ('updated_at', '2026-10-07'), ('models', []),
                             ('models', None), ('unexpected', 1)]:
            doc = document()
            doc[field] = value
            self.reject(doc)
        self.reject([])


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(CATALOG.read_text())
        cls.models = {m['id']: m for m in cls.doc['models']}

    def select(self, mid, service, input_tokens):
        return next(t['pricing'] for t in self.models[mid]['pricing_tiers']
                    if t['service_tier'] == service
                    and input_tokens >= t['input_tokens_min']
                    and (t['input_tokens_max'] is None or input_tokens <= t['input_tokens_max']))

    def test_catalog_valid(self):
        check_shape(self.doc)

    def test_gpt_sol_standard_boundary_and_services(self):
        short = {'input': 2, 'output': 10, 'cache_read': .1, 'cache_write': 2.5}
        long = {'input': 4, 'output': 15, 'cache_read': .2, 'cache_write': 5}
        for count, expected in [(0, short), (272000, short), (272001, long), (1050000, long)]:
            self.assertEqual(self.select('gpt-6.1-sol', 'standard', count), expected)
        self.assertEqual(self.select('gpt-6.1-sol', 'batch', 272000),
                         {'input': 1, 'output': 5, 'cache_read': .05, 'cache_write': 1.25})
        self.assertEqual(self.select('gpt-6.1-sol', 'batch', 272001)['output'], 7.5)
        self.assertEqual(self.select('gpt-6.1-sol', 'fast', 272000)['input'], 4)
        with self.assertRaises(StopIteration):
            self.select('gpt-6.1-sol', 'ultrafast', 100)

    def test_missing_long_context_service_is_not_standard(self):
        self.assertEqual(self.select('gpt-5.5-pro', 'batch', 272000)['input'], 15)
        with self.assertRaises(StopIteration):
            self.select('gpt-5.5-pro', 'batch', 272001)

    def test_grok_boundary(self):
        self.assertEqual(self.select('grok-4.7', 'standard', 199999)['input'], 2)
        self.assertEqual(self.select('grok-4.7', 'standard', 200000),
                         {'input': 4, 'output': 12, 'cache_read': 1})

    def test_google_batch_cache_is_independent(self):
        self.assertEqual(self.select('gemini-3.1-pro-preview', 'batch', 200000),
                         {'input': 1, 'output': 6, 'cache_read': .2})
        self.assertEqual(self.select('gemini-3.1-pro-preview', 'standard', 200001)['output'], 18)
        self.assertEqual(self.select('gemini-3.5-flash', 'flex', 100)['cache_read'], .08)

    def test_provider_coverage_and_verified_rates(self):
        self.assertEqual({m['provider'] for m in self.doc['models']},
                         {'openai', 'anthropic', 'google', 'xai', 'meta', 'moonshot',
                          'deepseek', 'qwen', 'zhipu', 'mistral', 'cohere'})
        expected = {'deepseek-v4.1-flash': (.3, 1.2, .006),
                    'claude-opus-5-5': (4, 20, .2),
                    'mistral-large-4': (1.36, 4.18, .14),
                    'glm-5.3': (1.4, 4.4, .26)}
        for mid, rates in expected.items():
            actual = self.models[mid]['pricing']
            self.assertEqual(tuple(actual[k] for k in ['input', 'output', 'cache_read']), rates)
        self.assertNotIn('cache_read', self.models['qwen3.8-flash']['pricing'])
        self.assertNotIn('cache_read', self.models['command-a-03-2025']['pricing'])

    def test_redirects_and_generic_aliases(self):
        aliases = {a.lower(): m['id'] for m in self.doc['models'] for a in m.get('aliases', [])}
        expected = {'sol': 'gpt-6.1-sol', 'opus': 'claude-opus-5-5',
                    'sonnet': 'claude-sonnet-5-5', 'fable': 'claude-fable-5-1',
                    'deepseek-v4-flash-vision-exp': 'deepseek-v4.1-flash',
                    'grok-code-fast-1': 'grok-build-0.1', 'grok-4-fast': 'grok-4.3',
                    'llama-4-maverick': 'gemma-4-31b-it'}
        for alias, mid in expected.items():
            self.assertEqual(aliases[alias], mid)
            self.assertNotIn(alias, self.models)
        self.assertEqual(aliases['5.6-sol'], 'gpt-5.6-sol')

    def test_anthropic_api_ids_and_legacy_alias_compatibility(self):
        expected = {
            'claude-opus-5', 'claude-opus-4-8', 'claude-sonnet-5',
            'claude-sonnet-4-6', 'claude-haiku-4-5-20251001',
            'claude-fable-5', 'claude-fable-5-1',
            'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5',
        }
        self.assertEqual({m['id'] for m in self.doc['models']
                          if m['provider'] == 'anthropic'}, expected)
        names = {name.lower(): m['id'] for m in self.doc['models']
                 for name in [m['id']] + m.get('aliases', [])}
        legacy = {
            'claude-opus-4.8': 'claude-opus-4-8',
            'claude-sonnet-4.6': 'claude-sonnet-4-6',
            'claude-haiku-4.5': 'claude-haiku-4-5-20251001',
            'claude-haiku-4-5': 'claude-haiku-4-5-20251001',
            'claude-fable-5.1': 'claude-fable-5-1',
            'claude-opus-5.5': 'claude-opus-5-5',
            'claude-sonnet-5.5': 'claude-sonnet-5-5',
            'opus-5-5': 'claude-opus-5-5',
            'fable-5-1': 'claude-fable-5-1',
        }
        for alias, mid in legacy.items():
            with self.subTest(alias=alias):
                self.assertEqual(names[alias], mid)
        self.assertEqual(names['gpt-6.1-sol'], 'gpt-6.1-sol')

    def test_first_party_kimi_refresh(self):
        self.assertEqual(self.models['kimi-k3']['pricing'],
                         {'input': 3, 'output': 15, 'cache_read': .3,
                          'cache_5m_write': 3, 'cache_1h_write': 6})
        self.assertEqual(self.models['kimi-k3']['context_window'], 1048576)
        self.assertEqual(self.models['kimi-k2.7-code']['pricing'],
                         {'input': .95, 'output': 4, 'cache_read': .19})
        self.assertEqual(self.models['kimi-k2.7-code']['context_window'], 262144)

    def test_haiku_boundary_and_sonnet_cache_refresh(self):
        self.assertEqual(self.select('claude-haiku-5-5', 'standard', 100000),
                         {'input': .1, 'output': .5, 'cache_read': .01,
                          'cache_5m_write': .125, 'cache_1h_write': .2})
        self.assertEqual(self.select('claude-haiku-5-5', 'standard', 100001),
                         {'input': .5, 'output': 2.5, 'cache_read': .05,
                          'cache_5m_write': .625, 'cache_1h_write': 1})
        self.assertEqual(self.select('claude-haiku-5-5', 'batch', 100001)['output'], 1.25)
        self.assertEqual(self.select('claude-sonnet-5-5', 'standard', 0)['cache_read'], .1)
        self.assertEqual(self.select('claude-sonnet-5-5', 'batch', 0)['cache_read'], .05)
        aliases = {a: m['id'] for m in self.doc['models'] for a in m.get('aliases', [])}
        self.assertEqual(aliases['haiku'], 'claude-haiku-5-5')
        self.assertEqual(aliases['haiku-4.5'], 'claude-haiku-4-5-20251001')

    def test_failed_verification_keeps_dates_and_notes(self):
        for mid in ['kimi-k2.5',
                    'chat-latest-07012026', 'gemini-3-pro-preview']:
            self.assertEqual(self.models[mid]['as_of'], '2026-09-01')
            self.assertIn('2026-10-07', self.models[mid]['notes'])


if __name__ == '__main__':
    unittest.main()
