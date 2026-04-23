import json

from .common import AITestCommon


class TestAiWindow(AITestCommon):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name, arguments):
        text, _info = self.env['muk_mcp.tool']._call(name, arguments, self.env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_open_view_basic(self):
        result = self._call('open_view', {'model': 'res.partner'})
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'res.partner')
        self.assertEqual(result['view_mode'], 'list')
        self.assertNotIn('context', result)

    def test_open_view_passes_additional_context(self):
        result = self._call('open_view', {
            'model': 'res.partner',
            'view_type': 'pivot',
            'additional_context': {
                'pivot_row_groupby': ['country_id'],
                'pivot_measures': ['__count'],
            },
        })
        self.assertEqual(result['view_mode'], 'pivot')
        self.assertEqual(
            result['context']['pivot_row_groupby'], ['country_id'],
        )
        self.assertEqual(result['context']['pivot_measures'], ['__count'])

    def test_open_view_empty_additional_context_omits_key(self):
        result = self._call('open_view', {
            'model': 'res.partner',
            'additional_context': {},
        })
        self.assertNotIn('context', result)

    def test_open_view_graph_context(self):
        result = self._call('open_view', {
            'model': 'res.partner',
            'view_type': 'graph',
            'additional_context': {
                'graph_mode': 'bar',
                'graph_groupbys': ['country_id'],
                'graph_measure': '__count',
            },
        })
        self.assertEqual(result['context']['graph_mode'], 'bar')
        self.assertEqual(result['context']['graph_groupbys'], ['country_id'])
