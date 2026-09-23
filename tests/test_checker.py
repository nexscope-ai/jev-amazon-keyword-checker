import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import checker as c

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ['--listing', str(ROOT / 'examples/listing.json'), '--keywords', str(ROOT / 'examples/keywords.json')]

class Tests(unittest.TestCase):
    def test_envelopes(self):
        for e in ({'code': 1}, {'code': False, 'data': {}}, {'code': 0, 'data': None}, {'code': 0, 'data': {'status': 'processing'}}):
            with self.subTest(e=e), self.assertRaises(c.CheckError): c.unpack(e)

    def test_dedup_missing_volume(self):
        self.assertEqual(c.keywords_from([' Kids ', 'kids']), [{'name': 'Kids', 'monthlySearchVolumeExact': None}])

    def test_limits(self):
        with self.assertRaises(c.CheckError): c.listing_fields({'title': 'x' * 301})
        with self.assertRaises(c.CheckError): c.request_for({'name': 'x' * 500}, {'title': '😀' * 300, 'contentExcerpt': '😀' * 4000})

    def test_product_identity(self):
        data = {'products': [{'asin': 'OTHER', 'title': 'Wrong'}, {'asin': 'B000000001', 'title': 'Right', 'aboutItem': ['School use']}]}
        self.assertEqual(c.product_listing(data, 'B000000001'), {'title': 'Right', 'contentExcerpt': 'School use'})
        with self.assertRaises(c.CheckError): c.product_listing(data, 'B000000002')

    def test_dry_run(self):
        with patch.object(c.Client, 'post', side_effect=AssertionError('Network')), contextlib.redirect_stdout(io.StringIO()) as out:
            c.main(LOCAL + ['--dry-run'])
        result = json.loads(out.getvalue())
        self.assertFalse(result['evaluated'])
        self.assertEqual(result['requests'][0]['useCase'], 'seo_relevance')
        with self.assertRaises(c.CheckError): c.main(['--asin', 'B000000001', '--seed', 'cup', '--dry-run'])

    def test_missing_decision(self):
        with patch.object(c.Client, 'post', return_value={'useCase': 'seo_relevance'}), self.assertRaises(c.CheckError):
            c.evaluate(c.Client('test-only'), {'name': 'cup'}, {'title': 'Cup'})

    def test_csv(self):
        for v in ('=1+1', ' +SUM(A1)', '@formula', '\tformula'): self.assertTrue(c.csv_safe(v).startswith("'"))
        self.assertEqual(c.csv_safe(None), '')

    def test_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'NEXSCOPE_API_KEY': 'test-only'}):
            dest = Path(tmp) / 'out'
            with patch.object(c.Client, 'post', side_effect=[{'useCase': 'seo_relevance', 'decision': 'review'}, c.CheckError('HTTP 429')]), self.assertRaises(c.CheckError):
                c.main(LOCAL + ['--output', str(dest)])
            r = json.loads((dest / 'results.json').read_text())
            self.assertFalse(r['complete'])
            self.assertEqual(len(r['results']), 1)
            self.assertIn('429', r['error'])
            self.assertFalse((dest / 'results.csv').exists())

    def test_full_pipeline(self):
        responses = [{'products': [{'asin': 'B000000001', 'title': 'Cup'}]}, {'keywordInfoList': [{'name': 'cup', 'monthlySearchVolumeExact': 0}]}, {'useCase': 'seo_relevance', 'decision': 'review'}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'NEXSCOPE_API_KEY': 'test-only'}):
            dest = Path(tmp) / 'out'
            with patch.object(c.Client, 'post', side_effect=responses) as post, contextlib.redirect_stdout(io.StringIO()):
                c.main(['--asin', 'B000000001', '--seed', 'cup', '--output', str(dest)])
            self.assertEqual([call.args[0] for call in post.call_args_list], [c.PRODUCT, c.EXPAND, c.EVALUATE])
            r = json.loads((dest / 'results.json').read_text())
            self.assertTrue(r['complete'])
            self.assertEqual(r['results'][0]['monthlySearchVolumeExact'], 0)
            self.assertTrue((dest / 'results.csv').exists())

if __name__ == '__main__': unittest.main()
