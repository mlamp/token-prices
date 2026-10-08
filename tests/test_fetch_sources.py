"""Source caching must distinguish fresh verification from retained evidence."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_sources import SOURCES, fetch, readable


class Response(io.BytesIO):
    headers = {'Content-Type': 'text/plain', 'ETag': 'fixture-etag'}

    def geturl(self):
        return SOURCES['openai']


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def test_changes_preserve_previous_snapshot(self):
        with patch('scripts.fetch_sources.urllib.request.urlopen', return_value=Response(b'price: 2')):
            self.assertEqual(fetch('openai', self.cache)['status'], 'new')
        with patch('scripts.fetch_sources.urllib.request.urlopen', return_value=Response(b'price: 4')):
            report = fetch('openai', self.cache)
        self.assertEqual(report['status'], 'changed')
        self.assertEqual(Path(report['previous']).read_text(), 'price: 2')
        self.assertEqual(Path(report['snapshot']).read_text(), 'price: 4')

    def test_failed_fetch_keeps_previous_verified_snapshot(self):
        with patch('scripts.fetch_sources.urllib.request.urlopen', return_value=Response(b'price: 2')):
            fetch('openai', self.cache)
        paths = [self.cache/'openai'/name for name in ['source.raw', 'source.txt', 'metadata.json']]
        before = [path.read_bytes() for path in paths]
        error = urllib.error.HTTPError(SOURCES['openai'], 403, 'Blocked', {}, None)
        with patch('scripts.fetch_sources.urllib.request.urlopen', side_effect=error):
            self.assertEqual(fetch('openai', self.cache)['status'], 'failed')
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_304_is_fresh_verification_of_cached_body(self):
        with patch('scripts.fetch_sources.urllib.request.urlopen', return_value=Response(b'price: 2')):
            fetch('openai', self.cache)
        error = urllib.error.HTTPError(SOURCES['openai'], 304, 'Not Modified', {}, None)
        with patch('scripts.fetch_sources.urllib.request.urlopen', side_effect=error) as request:
            report = fetch('openai', self.cache)
        self.assertEqual(report['status'], 'unchanged')
        self.assertEqual(request.call_args.args[0].get_header('If-none-match'), 'fixture-etag')
        self.assertEqual(Path(report['snapshot']).read_text(), 'price: 2')
        self.assertEqual(json.loads((self.cache/'openai/metadata.json').read_text())['checked_at'],
                         report['checked_at'])

    def test_readable_sources_preserve_prices_and_discard_scripts(self):
        page = '<style>discard</style><table><tr><td>Model</td><td>$2</td></tr></table><script>discard</script>'
        text = readable(page, 'text/html')
        self.assertIn('Model | $2', text)
        self.assertNotIn('discard', text)
        self.assertEqual(json.loads(readable('{"input":2}', 'application/json')), {'input': 2})


if __name__ == '__main__':
    unittest.main()
