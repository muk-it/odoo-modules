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
