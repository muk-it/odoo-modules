import json

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools.sources import (
    MAX_RECORD_SOURCES_PER_CALL,
    SOURCE_EXTRACTORS,
    extract_sources,
)


class TestSourceExtractors(AITestCommon):
    """Verify the per-tool source-extractor registry that feeds the sources rail."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_web_fetch_descriptor_becomes_web_source(self):
        result = {
            'type': 'web',
            'url': 'https://www.example.com/page',
            'title': 'Example',
            'content': 'x' * 10_000,
            'content_type': 'text/html',
        }
        sources = extract_sources('web_fetch', {'url': 'https://example.com'}, result)
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source['type'], 'web')
        self.assertEqual(source['id'], 'web:https://www.example.com/page')
        self.assertEqual(source['url'], 'https://www.example.com/page')
        self.assertEqual(source['title'], 'Example')
        self.assertEqual(source['domain'], 'example.com')
        self.assertNotIn('content', source)

    def test_web_fetch_falls_back_to_domain_title(self):
        result = {'type': 'web', 'url': 'https://docs.example.org/x', 'title': None}
        sources = extract_sources('web_fetch', {}, result)
        self.assertEqual(sources[0]['title'], 'docs.example.org')
        self.assertEqual(sources[0]['domain'], 'docs.example.org')

    def test_web_fetch_error_result_yields_no_source(self):
        result = {'url': 'https://example.com/x', 'error': 'HTTP 404'}
        self.assertEqual(extract_sources('web_fetch', {}, result), [])

    def test_web_fetch_without_url_yields_no_source(self):
        self.assertEqual(extract_sources('web_fetch', {}, {'type': 'web'}), [])

    def test_read_records_rows_become_record_sources(self):
        result = [
            {'id': 7, 'display_name': 'Acme Inc'},
            {'id': 9, 'name': 'Beta LLC'},
            {'id': 11},
        ]
        sources = extract_sources('read_records', {'model': 'res.partner'}, result)
        self.assertEqual(len(sources), 3)
        self.assertEqual(sources[0]['id'], 'record:res.partner,7')
        self.assertEqual(sources[0]['type'], 'record')
        self.assertEqual(sources[0]['res_model'], 'res.partner')
        self.assertEqual(sources[0]['res_id'], 7)
        self.assertEqual(sources[0]['display_name'], 'Acme Inc')
        self.assertEqual(sources[0]['href'], '/odoo/res.partner/7')
        self.assertEqual(sources[1]['display_name'], 'Beta LLC')
        self.assertEqual(sources[2]['display_name'], 'res.partner,11')

    def test_read_records_without_model_yields_no_source(self):
        self.assertEqual(extract_sources('read_records', {}, [{'id': 1}]), [])

    def test_json_string_result_is_parsed_before_extraction(self):
        web = json.dumps(
            {'type': 'web', 'url': 'https://example.com/x', 'title': 'X'}, indent=2
        )
        sources = extract_sources('web_fetch', {}, web)
        self.assertEqual(sources[0]['id'], 'web:https://example.com/x')
        records = json.dumps([{'id': 3, 'display_name': 'Gamma'}])
        sources = extract_sources('read_records', {'model': 'res.partner'}, records)
        self.assertEqual(sources[0]['id'], 'record:res.partner,3')

    def test_unparseable_string_result_yields_no_source(self):
        self.assertEqual(extract_sources('web_fetch', {}, 'not json'), [])

    def test_search_read_rows_become_record_sources(self):
        rows = [{'id': 1, 'name': 'a'}, {'id': 2, 'display_name': 'B'}]
        sources = extract_sources('search_read', {'model': 'res.partner'}, rows)
        self.assertEqual(
            [s['id'] for s in sources],
            ['record:res.partner,1', 'record:res.partner,2'],
        )
        self.assertEqual(sources[0]['display_name'], 'a')

    def test_search_read_caps_bulk_result(self):
        rows = [{'id': i} for i in range(1, MAX_RECORD_SOURCES_PER_CALL + 50)]
        sources = extract_sources('search_read', {'model': 'res.partner'}, rows)
        self.assertEqual(len(sources), MAX_RECORD_SOURCES_PER_CALL)

    def test_read_records_is_capped(self):
        rows = [{'id': i} for i in range(1, MAX_RECORD_SOURCES_PER_CALL + 50)]
        sources = extract_sources('read_records', {'model': 'res.partner'}, rows)
        self.assertEqual(len(sources), MAX_RECORD_SOURCES_PER_CALL)

    def test_unknown_tool_yields_no_source(self):
        self.assertEqual(extract_sources('adjust_search', {}, {'anything': 1}), [])

    def test_registry_only_opts_in_citable_tools(self):
        self.assertIn('web_fetch', SOURCE_EXTRACTORS)
        self.assertIn('read_records', SOURCE_EXTRACTORS)
        self.assertIn('search_read', SOURCE_EXTRACTORS)
        for excluded in (
            'read_group',
            'search_count',
            'export_records',
            'print_report',
            'read_resource',
            'adjust_search',
            'open_record',
            'create_records',
        ):
            self.assertNotIn(excluded, SOURCE_EXTRACTORS)
