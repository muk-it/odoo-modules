from odoo.tests import common

from odoo.addons.muk_mcp.tools import uri


class TestResourceUri(common.TransactionCase):
    """Cover ``odoo://`` resource URI construction and parsing."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_builders_round_trip_through_parse(self):
        self.assertEqual(
            uri.parse_uri(uri.attachment_uri(7)),
            ('attachment', {'attachment_id': 7}),
        )
        self.assertEqual(
            uri.parse_uri(uri.record_field_uri('res.partner', 3, 'image_1920')),
            (
                'record_field',
                {'model': 'res.partner', 'record_id': 3, 'field': 'image_1920'},
            ),
        )

    def test_missing_or_empty_uri_returns_none(self):
        self.assertIsNone(uri.parse_uri(None))
        self.assertIsNone(uri.parse_uri(''))

    def test_foreign_scheme_returns_none(self):
        self.assertIsNone(uri.parse_uri('https://attachment/1'))
        self.assertIsNone(uri.parse_uri('attachment/1'))

    def test_scheme_is_case_insensitive(self):
        self.assertEqual(
            uri.parse_uri('ODOO://attachment/1'),
            ('attachment', {'attachment_id': 1}),
        )

    def test_host_is_case_sensitive(self):
        self.assertIsNone(uri.parse_uri('odoo://Attachment/1'))

    def test_bare_scheme_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://'))

    def test_attachment_without_id_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://attachment/'))

    def test_attachment_with_extra_segment_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://attachment/1/2'))

    def test_attachment_with_non_numeric_id_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://attachment/abc'))

    def test_record_field_with_wrong_arity_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://record/res.partner/1'))
        self.assertIsNone(uri.parse_uri('odoo://record/res.partner/1/name/extra'))

    def test_record_field_with_non_numeric_id_returns_none(self):
        self.assertIsNone(uri.parse_uri('odoo://record/res.partner/abc/name'))

    def test_negative_id_is_accepted(self):
        self.assertEqual(
            uri.parse_uri('odoo://attachment/-1'),
            ('attachment', {'attachment_id': -1}),
        )

    def test_traversal_segments_are_returned_as_the_model_name(self):
        self.assertEqual(
            uri.parse_uri('odoo://record/../1/name'),
            ('record_field', {'model': '..', 'record_id': 1, 'field': 'name'}),
        )

    def test_query_and_fragment_are_ignored(self):
        self.assertEqual(
            uri.parse_uri('odoo://attachment/5?download=1'),
            ('attachment', {'attachment_id': 5}),
        )
        self.assertEqual(
            uri.parse_uri('odoo://attachment/5#part'),
            ('attachment', {'attachment_id': 5}),
        )
