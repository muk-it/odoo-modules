from odoo.tests import TransactionCase


class TestProductCategory(TransactionCase):
    """Cover the product category tree of the product menu."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_menu_opens_the_category_tree(self):
        menu = self.env.ref('muk_product.menu_product_category')
        action = self.env.ref('muk_product.action_product_category')
        self.assertEqual(menu.action, action)
        self.assertEqual(action.views[0][1], 'treelist')

    def test_category_tree_nests_subcategories(self):
        category = self.env['product.category']
        root = category.create({'name': 'Tree Root'})
        child = category.create({'name': 'Tree Child', 'parent_id': root.id})
        category.create({'name': 'Tree Leaf', 'parent_id': child.id})
        result = category.web_tree_read(
            [('id', 'child_of', root.id)],
            {'name': {}, 'product_count': {}},
            'parent_id',
            expanded_ids=[root.id],
        )
        rows = [(row['name'], row['__tree__']['level']) for row in result['records']]
        self.assertEqual(rows, [('Tree Root', 0), ('Tree Child', 1)])
        self.assertEqual(result['records'][1]['__tree__']['count'], 1)
