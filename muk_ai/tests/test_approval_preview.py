from odoo.addons.muk_ai.tests.common import AITestCommon


class TestApprovalPreview(AITestCommon):
    """Verify the structured approval preview rendering."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_update_preview_shows_field_label_and_from_to(self):
        partner = self.env['res.partner'].create({'name': 'Preview Target'})
        preview = self.env['muk_ai.approval']._build_preview(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'values': {'name': 'New Name'},
            },
        )
        self.assertEqual(preview['kind'], 'update')
        self.assertEqual(len(preview['changes']), 1)
        change = preview['changes'][0]
        self.assertEqual(change['field'], 'name')
        self.assertEqual(change['from'], 'Preview Target')
        self.assertEqual(change['to'], 'New Name')
        targets = preview['targets']
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]['id'], partner.id)

    def test_update_preview_resolves_many2one_id_to_display_name(self):
        partner = self.env['res.partner'].create({'name': 'M2o Target'})
        user = self.env.ref('base.user_admin')
        preview = self.env['muk_ai.approval']._build_preview(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'values': {'user_id': user.id},
            },
        )
        change = preview['changes'][0]
        self.assertEqual(change['to'], user.display_name)

    def test_delete_preview_lists_display_names(self):
        p1 = self.env['res.partner'].create({'name': 'Del1'})
        p2 = self.env['res.partner'].create({'name': 'Del2'})
        preview = self.env['muk_ai.approval']._build_preview(
            'delete_records',
            {
                'model': 'res.partner',
                'ids': [p1.id, p2.id],
            },
        )
        self.assertEqual(preview['kind'], 'delete')
        names = sorted(t['display_name'] for t in preview['targets'])
        self.assertEqual(names, ['Del1', 'Del2'])

    def test_call_method_preview_shows_method_and_targets(self):
        partner = self.env['res.partner'].create({'name': 'CallTarget'})
        preview = self.env['muk_ai.approval']._build_preview(
            'call_method',
            {
                'model': 'res.partner',
                'method': 'action_archive',
                'ids': [partner.id],
            },
        )
        self.assertEqual(preview['kind'], 'call')
        self.assertEqual(preview['method'], 'action_archive')
        self.assertEqual(len(preview['targets']), 1)
        self.assertEqual(preview['targets'][0]['id'], partner.id)

    def test_create_preview_lists_property_labels(self):
        preview = self.env['muk_ai.approval']._build_preview(
            'create_records',
            {
                'model': 'res.partner',
                'values': {'name': 'New Guy', 'email': 'new@x.test'},
            },
        )
        self.assertEqual(preview['kind'], 'create')
        fields_seen = {p['field'] for p in preview['properties']}
        self.assertEqual(fields_seen, {'name', 'email'})
        name_prop = next(p for p in preview['properties'] if p['field'] == 'name')
        self.assertTrue(name_prop['label'])
        self.assertEqual(name_prop['value'], 'New Guy')

    def test_preview_survives_missing_model_gracefully(self):
        preview = self.env['muk_ai.approval']._build_preview(
            'delete_records',
            {
                'model': 'nonexistent.model',
                'ids': [1, 2],
            },
        )
        self.assertEqual(preview['kind'], 'delete')
        self.assertEqual(preview['targets'], [])
