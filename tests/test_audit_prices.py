"""Verify rate normalization and partial-coverage reporting without network access."""
import copy
import unittest

from scripts.audit_prices import compare, hosted_candidate, parse_openai

OPENAI = '''### Standard pricing data
| Model | Short context input | Short context cached input | Short context cache writes | Short context output | Long context input | Long context cached input | Long context cache writes | Long context output |
| gpt-example | $2.00 | $0.10 | $2.50 | $10.00 | $4.00 | $0.20 | $5.00 | $15.00 |
### Batch pricing data
| Model | Short context input | Short context cached input | Short context cache writes | Short context output | Long context input | Long context cached input | Long context cache writes | Long context output |
| gpt-example | $1.00 | - | - | $5.00 | - | - | - | - |
Short context: ≤272K input tokens. Long context: >272K input tokens.
'''
HOST = {'model_name': 'vendor/served', 'max_tokens': 131072, 'replaced_by': None,
        'deprecated': None, 'pricing': {'cents_per_input_token': .00001,
            'cents_per_output_token': .000032, 'rate_per_input_token_cached': .5,
            'rate_per_input_token_cache_write': None,
            'rate_per_service_tier_priority': 1.5, 'rate_per_service_tier_flex': .8}}
PROVENANCE = '| `hosted` | [Pricing](https://api.deepinfra.com/models/list) | DeepInfra |'


class AuditTests(unittest.TestCase):
    def test_openai_boundary_and_missing_cache_are_independent(self):
        ts = parse_openai(OPENAI)['gpt-example']
        self.assertEqual(ts[0]['input_tokens_max'], 272000)
        self.assertEqual(ts[1]['input_tokens_min'], 272001)
        self.assertEqual(ts[1]['pricing']['output'], 15)
        self.assertEqual(ts[2]['input_tokens_max'], 272000)
        self.assertEqual(ts[2]['pricing'], {'input': 1, 'output': 5})
        self.assertEqual(parse_openai(OPENAI.replace('272K', '300K'))['gpt-example'][0]['input_tokens_max'], 300000)

    def test_unknown_or_incomplete_source_layout_fails(self):
        for body in [OPENAI.replace('Short context:', 'Unknown boundary:'),
                     OPENAI.replace('$2.00', 'Free'),
                     OPENAI.replace('$4.00', '-'),
                     OPENAI.replace('Short context cached input', 'Other currency cached input')]:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    parse_openai(body)

    def test_retention_layout_nested_flex_and_repeated_rows(self):
        header = '| Model | ' + ' | '.join(prefix + name
            for prefix in ['Short context ', 'Long context ']
            for name in ['input', 'output', 'cached input', '30m write', '12h write']) + ' |'
        row = '| gpt-example | $1 | $5 | $0.05 | $1.25 | $2.50 | $2 | $7.50 | $0.10 | $2.50 | $5 |'
        body = '### Standard pricing data\n' + header + '\n' + row
        body += '\n### Standard pricing data\n' + header + '\n' + row
        body += '\n### Batch pricing data\n#### Flex\n' + header + '\n' + row
        body += '\nShort context: ≤272K input tokens. Long context: >272K input tokens.'
        tiers = parse_openai(body)['gpt-example']
        self.assertEqual(len(tiers), 4)
        self.assertEqual(tiers[0]['pricing']['cache_write'], 1.25)
        self.assertEqual(tiers[1]['pricing']['cache_12h_write'], 5)
        self.assertEqual(tiers[2]['service_tier'], 'flex')
        with self.assertRaises(ValueError):
            parse_openai(body.replace(row, row.replace('$1 |', '$3 |'), 1))

    def test_unbanded_table_has_no_inferred_cache(self):
        body = OPENAI + '\n### Standard pricing data\n| Model | Input | Output | Cached input |\n| gpt-simple | $1 | $5 | - |\n'
        tier = parse_openai(body)['gpt-simple'][0]
        self.assertIsNone(tier['input_tokens_max'])
        self.assertEqual(tier['pricing'], {'input': 1, 'output': 5})

    def test_hosted_units_cache_and_service_factors(self):
        expected = hosted_candidate(HOST)
        self.assertEqual(expected['pricing'], {'input': .1, 'output': .32, 'cache_read': .05})
        self.assertEqual(expected['context_window'], 131072)
        self.assertEqual(expected['pricing_tiers'][1]['pricing']['input'], .15)
        self.assertEqual(expected['pricing_tiers'][2]['pricing']['output'], .256)
        row = copy.deepcopy(HOST)
        row['pricing']['rate_per_input_token_cached'] = None
        self.assertNotIn('cache_read', hosted_candidate(row)['pricing'])

    def test_invalid_hosted_factors_fail(self):
        for factor in [-1, True, float('nan'), float('inf')]:
            row = copy.deepcopy(HOST)
            row['pricing']['rate_per_input_token_cached'] = factor
            with self.assertRaises(ValueError):
                hosted_candidate(row)

    def test_report_differences_and_partial_coverage_without_mutation(self):
        source = parse_openai(OPENAI)
        model = {'id': 'gpt-example', 'provider': 'openai',
                 'pricing': source['gpt-example'][0]['pricing'],
                 'pricing_tiers': source['gpt-example'], 'as_of': '2026-10-01'}
        model = copy.deepcopy(model)
        model['pricing']['output'] = 9
        other = {'id': 'unsupported', 'provider': 'anthropic'}
        before = copy.deepcopy([model, other])
        report = compare([model, other], source, None, '')
        self.assertEqual(report['compared_models'], 1)
        self.assertEqual(report['uncovered_models'], 1)
        self.assertTrue(report['differences'])
        self.assertEqual([model, other], before)

    def test_retirement_is_reported_for_exact_serving_endpoint(self):
        model = {'id': 'hosted', 'provider': 'meta',
                 'notes': 'Hosted endpoint: vendor/served. Context is the API limit.',
                 **hosted_candidate(HOST)}
        row = copy.deepcopy(HOST)
        row['replaced_by'] = 'vendor/replacement'
        report = compare([model], None, [row], PROVENANCE)
        self.assertEqual(report['differences'][0]['field'], 'serving_endpoint')
        self.assertEqual(report['differences'][0]['source'], 'vendor/replacement')
        missing = compare([model], None, [], PROVENANCE)
        self.assertEqual(missing['compared_models'], 0)
        self.assertEqual(len(missing['skipped']), 1)


if __name__ == '__main__':
    unittest.main()
