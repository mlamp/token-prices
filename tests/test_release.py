"""Regression tests for generated documentation and release preparation."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_release import prepare
from scripts.update_readme import render_readme, update, version_tuple


TEMPLATE = '''# Catalog

<!-- generated:consume:start -->
stale release links
<!-- generated:consume:end -->

Keep this paragraph.

<!-- generated:schema-version:start -->
stale schema version
<!-- generated:schema-version:end -->

<!-- generated:freshness:start -->
stale freshness
<!-- generated:freshness:end -->
'''
CATALOG = {'schema_version': 2, 'updated_at': '2026-10-08T06:00:00Z',
           'models': [{'provider': 'openai', 'as_of': '2026-10-07'},
                      {'provider': 'anthropic', 'as_of': '2026-10-08'}]}
METADATA = {
    'repository': 'example/catalog',
    'latest': {'tag': 'v0.1.1', 'schema_version': 1},
    'legacy_v1': {'tag': 'v0.1.1', 'schema_version': 1},
}


class ReadmeTests(unittest.TestCase):
    def test_released_schema_is_distinct_from_moving_schema(self):
        result = render_readme(TEMPLATE, METADATA, CATALOG)
        self.assertIn('Latest stable release: [v0.1.1]', result)
        self.assertIn('(schema v1)', result)
        self.assertIn('moving schema v2', result)
        self.assertIn('`schema_version` is `2`', result)
        self.assertIn('/v0.1.1/prices/current.json', result)
        self.assertIn('/v0.1.1/schema/token-prices.schema.json', result)
        self.assertIn('Keep this paragraph.', result)
        self.assertEqual(render_readme(result, METADATA, CATALOG), result)

    def test_new_release_links_and_old_compatibility_pin(self):
        metadata = copy.deepcopy(METADATA)
        metadata['latest'] = {'tag': 'v0.2.0', 'schema_version': 2}
        result = render_readme(TEMPLATE, metadata, dict(CATALOG, schema_version=3))
        self.assertIn('https://github.com/example/catalog/releases/tag/v0.2.0', result)
        self.assertIn('/v0.2.0/prices/current.json', result)
        self.assertIn('/v0.2.0/schema/token-prices.schema.json', result)
        self.assertIn('(schema v2)', result)
        self.assertIn('moving schema v3', result)
        self.assertIn('`schema_version` is `3`', result)
        self.assertIn('/v0.1.1/prices/current.json', result)

    def test_missing_duplicate_or_reversed_markers_fail(self):
        start = '<!-- generated:consume:start -->'
        end = '<!-- generated:consume:end -->'
        for text in [TEMPLATE.replace(start, ''), TEMPLATE+start,
                     TEMPLATE.replace(start, '<swap>').replace(end, start).replace('<swap>', end)]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    render_readme(text, METADATA, CATALOG)

    def test_freshness_is_derived_without_claiming_all_models_are_fresh(self):
        result = render_readme(TEMPLATE, METADATA, CATALOG)
        self.assertIn(CATALOG['updated_at'], result)
        self.assertIn('2 models across 2 providers', result)
        self.assertIn('`2026-10-07` to `2026-10-08`', result)
        changed = dict(CATALOG, updated_at='2026-10-09T00:00:00Z')
        self.assertNotEqual(render_readme(TEMPLATE, METADATA, changed), result)

    def test_stable_versions_only(self):
        self.assertEqual(version_tuple('v1.20.3'), (1, 20, 3))
        for version in ['1.2.3', 'v01.2.3', 'v1.2', 'v1.2.3-rc.1',
                        'v1.2.3\n', 'v1.2.3; echo injected', '--help']:
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    version_tuple(version)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'prices').mkdir()
        (self.root / 'prices/current.json').write_text(json.dumps(CATALOG))
        (self.root / 'release.json').write_text(json.dumps(METADATA))
        (self.root / 'README.md').write_text(TEMPLATE)
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'Fixture'], cwd=self.root, check=True)

    def test_prepare_updates_metadata_and_generated_urls(self):
        prepare('v0.2.0', self.root)
        metadata = json.loads((self.root / 'release.json').read_text())
        self.assertEqual(metadata['latest'], {'tag': 'v0.2.0', 'schema_version': 2})
        self.assertEqual(metadata['legacy_v1'], METADATA['legacy_v1'])
        self.assertTrue(update(self.root, check=True))
        readme = (self.root / 'README.md').read_text()
        self.assertIn('/v0.2.0/prices/current.json', readme)
        self.assertIn('/v0.2.0/schema/token-prices.schema.json', readme)
        self.assertIn('/v0.1.1/prices/current.json', readme)

    def test_tag_contains_its_own_release_links(self):
        prepare('v0.2.0', self.root)
        subprocess.run(['git', 'add', 'README.md', 'release.json', 'prices/current.json'],
                       cwd=self.root, check=True)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '-qm', 'Release v0.2.0'], cwd=self.root, check=True)
        subprocess.run(['git', 'tag', 'v0.2.0'], cwd=self.root, check=True)
        tagged_readme = subprocess.check_output(['git', 'show', 'v0.2.0:README.md'],
                                                cwd=self.root, text=True)
        tagged_metadata = json.loads(subprocess.check_output(
            ['git', 'show', 'v0.2.0:release.json'], cwd=self.root, text=True))
        self.assertIn('/v0.2.0/prices/current.json', tagged_readme)
        self.assertIn('/v0.2.0/schema/token-prices.schema.json', tagged_readme)
        self.assertEqual(tagged_metadata['latest'],
                         {'tag': 'v0.2.0', 'schema_version': 2})

    def test_no_mutation_for_old_or_existing_tags(self):
        subprocess.run(['git', 'tag', 'v0.3.0'], cwd=self.root, check=True)
        before = {name: (self.root / name).read_text() for name in ['README.md', 'release.json']}
        for version in ['v0.1.0', 'v0.1.1', 'v0.3.0', 'invalid']:
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    prepare(version, self.root)
                self.assertEqual({name: (self.root / name).read_text() for name in before}, before)

    def test_bad_readme_does_not_mutate_release_metadata(self):
        (self.root / 'README.md').write_text('Missing markers')
        before = (self.root / 'release.json').read_text()
        with self.assertRaises(ValueError):
            prepare('v0.2.0', self.root)
        self.assertEqual((self.root / 'release.json').read_text(), before)

    def test_check_detects_stale_metadata_without_rewriting(self):
        path = self.root / 'README.md'
        before = path.read_text()
        self.assertFalse(update(self.root, check=True))
        self.assertEqual(path.read_text(), before)
        update(self.root)
        self.assertTrue(update(self.root, check=True))
        catalog_path = self.root / 'prices/current.json'
        catalog_path.write_text(json.dumps(dict(CATALOG, schema_version=3)))
        self.assertFalse(update(self.root, check=True))


if __name__ == '__main__':
    unittest.main()
