from odoo.tests import TransactionCase


class TestContactsTree(TransactionCase):
    """Cover the contact tree of the contacts app."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contacts_action_orders_tree_kanban_list(self):
        action = self.env.ref('contacts.action_contacts')
        view = self.env.ref('muk_contacts.view_partner_treelist')
        self.assertEqual(action.views[0], [view.id, 'treelist'])
        self.assertEqual([mode for _id, mode in action.views[1:3]], ['kanban', 'list'])

    def test_contact_tree_nests_contacts_under_their_company(self):
        partner = self.env['res.partner']
        company = partner.create({'name': 'Tree Company'})
        contact = partner.create({'name': 'Tree Contact', 'parent_id': company.id})
        partner.create(
            {'name': 'Tree Delivery', 'parent_id': contact.id, 'type': 'delivery'}
        )
        result = partner.web_tree_read(
            [('id', 'child_of', company.id)],
            {'name': {}, 'contact_number': {}},
            'parent_id',
            expanded_ids=[company.id],
        )
        rows = [(row['name'], row['__tree__']['level']) for row in result['records']]
        self.assertEqual(rows, [('Tree Company', 0), ('Tree Contact', 1)])
        self.assertEqual(result['records'][1]['__tree__']['count'], 1)
        self.assertEqual(result['records'][1]['contact_number'], company.contact_number)
