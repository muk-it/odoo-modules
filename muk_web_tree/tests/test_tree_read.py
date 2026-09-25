from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import TransactionCase

SPECIFICATION = {'name': {}}


class TestTreeRead(TransactionCase):
    """Read records as a tree through ``web_tree_read``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a small hierarchy of tagged partners."""
        super().setUpClass()
        cls.tag = cls.env['res.partner.category'].create({'name': 'Tree Test'})
        cls.alpha = cls._create_partner('Alpha', color=1)
        cls.alpha_one = cls._create_partner('Alpha One', cls.alpha, color=2)
        cls.alpha_two = cls._create_partner('Alpha Two', cls.alpha, color=3)
        cls.alpha_two_leaf = cls._create_partner(
            'Alpha Two Leaf', cls.alpha_two, color=4
        )
        cls.beta = cls._create_partner('Beta', color=5)
        cls.domain = [('category_id', 'in', cls.tag.ids)]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _create_partner(
        cls, name: str, parent: models.BaseModel | None = None, color: int = 0
    ) -> models.BaseModel:
        """Create a tagged partner under the given parent."""
        return cls.env['res.partner'].create(
            {
                'name': name,
                'parent_id': parent.id if parent else False,
                'color': color,
                'category_id': [(4, cls.tag.id)],
            }
        )

    def _read(
        self, domain: list | None = None, model: str = 'res.partner', **kwargs
    ) -> dict:
        """Read a tree ordered by name, searching when a domain is given."""
        kwargs.setdefault('search', domain is not None)
        return self.env[model].web_tree_read(
            domain or self.domain, SPECIFICATION, 'parent_id', order='name', **kwargs
        )

    def _rows(self, result: dict) -> list[tuple[str, int]]:
        """Return the name and level of every row of a tree read."""
        return [(row['name'], row['__tree__']['level']) for row in result['records']]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_roots_only(self):
        result = self._read()
        self.assertEqual(self._rows(result), [('Alpha', 0), ('Beta', 0)])
        self.assertEqual(result['length'], 2)
        alpha, beta = result['records']
        self.assertEqual(alpha['__tree__']['count'], 2)
        self.assertFalse(alpha['__tree__']['expanded'])
        self.assertEqual(beta['__tree__']['count'], 0)

    def test_expanded_descendants(self):
        result = self._read(expanded_ids=[self.alpha.id, self.alpha_two.id])
        self.assertEqual(
            self._rows(result),
            [
                ('Alpha', 0),
                ('Alpha One', 1),
                ('Alpha Two', 1),
                ('Alpha Two Leaf', 2),
                ('Beta', 0),
            ],
        )
        self.assertEqual(result['length'], 2)

    def test_collapsed_ancestor_hides_expanded_child(self):
        result = self._read(expanded_ids=[self.alpha_two.id])
        self.assertEqual(self._rows(result), [('Alpha', 0), ('Beta', 0)])

    def test_expand_all(self):
        result = self._read(expand_all=True)
        self.assertEqual(len(result['records']), 5)
        expanded = {
            row['name'] for row in result['records'] if row['__tree__']['expanded']
        }
        self.assertEqual(expanded, {'Alpha', 'Alpha Two'})

    def test_pagination_counts_roots(self):
        result = self._read(limit=1)
        self.assertEqual(self._rows(result), [('Alpha', 0)])
        self.assertEqual(result['length'], 2)
        result = self._read(limit=1, offset=1)
        self.assertEqual(self._rows(result), [('Beta', 0)])

    def test_search_adds_context_ancestors(self):
        domain = [*self.domain, ('name', '=', 'Alpha Two Leaf')]
        result = self._read(domain, expand_context=True)
        self.assertEqual(
            self._rows(result),
            [('Alpha', 0), ('Alpha Two', 1), ('Alpha Two Leaf', 2)],
        )
        context = [row['__tree__']['context'] for row in result['records']]
        self.assertEqual(context, [True, True, False])
        self.assertEqual(result['records'][0]['__tree__']['count'], 1)

    def test_search_without_context_expansion(self):
        domain = [*self.domain, ('name', '=', 'Alpha Two Leaf')]
        result = self._read(domain)
        self.assertEqual(self._rows(result), [('Alpha', 0)])
        self.assertTrue(result['records'][0]['__tree__']['context'])

    def test_matching_ancestor_is_not_context(self):
        domain = [*self.domain, ('name', 'in', ('Alpha', 'Alpha Two Leaf'))]
        result = self._read(domain, expand_context=True)
        self.assertEqual(
            self._rows(result),
            [('Alpha', 0), ('Alpha Two', 1), ('Alpha Two Leaf', 2)],
        )
        context = [row['__tree__']['context'] for row in result['records']]
        self.assertEqual(context, [False, True, False])

    def test_unmatched_parent_without_matching_descendant(self):
        domain = [*self.domain, ('name', '=', 'Alpha One')]
        result = self._read(domain, expand_context=True)
        self.assertEqual(self._rows(result), [('Alpha', 0), ('Alpha One', 1)])
        self.assertNotIn('Alpha Two', {row['name'] for row in result['records']})

    def test_rollups(self):
        result = self._read(expanded_ids=[self.alpha.id], rollup_fields=['color'])
        rollups = {row['name']: row['__tree__']['rollups'] for row in result['records']}
        self.assertEqual(rollups['Alpha'], {'color': 10})
        self.assertEqual(rollups['Alpha Two'], {'color': 7})
        self.assertEqual(rollups['Alpha One'], {})
        self.assertEqual(rollups['Beta'], {})

    def test_rollups_follow_search(self):
        domain = [*self.domain, ('name', '!=', 'Alpha One')]
        result = self._read(domain, rollup_fields=['color'])
        rollups = {row['name']: row['__tree__']['rollups'] for row in result['records']}
        self.assertEqual(rollups['Alpha'], {'color': 8})

    def test_parent_store_model(self):
        category = self.env['res.partner.category']
        root = category.create({'name': 'Node Root'})
        child = category.create({'name': 'Node Child', 'parent_id': root.id})
        category.create({'name': 'Node Leaf', 'parent_id': child.id})
        result = self._read(
            [('name', '=like', 'Node %')],
            model='res.partner.category',
            expand_all=True,
        )
        self.assertEqual(
            self._rows(result),
            [('Node Root', 0), ('Node Child', 1), ('Node Leaf', 2)],
        )

    def test_archived_parent_makes_root(self):
        category = self.env['res.partner.category']
        root = category.create({'name': 'Node Root'})
        category.create({'name': 'Node Child', 'parent_id': root.id})
        root.active = False
        result = self._read(
            [('name', '=like', 'Node %')], model='res.partner.category', search=False
        )
        self.assertEqual(self._rows(result), [('Node Child', 0)])

    def test_empty(self):
        result = self._read([('id', '=', 0)])
        self.assertEqual(result, {'length': 0, 'records': []})

    def test_children_are_paged_by_the_limit(self):
        result = self._read(limit=1, expanded_ids=[self.alpha.id])
        self.assertEqual(self._rows(result), [('Alpha', 0), ('Alpha One', 1)])
        alpha = result['records'][0]['__tree__']
        self.assertEqual((alpha['count'], alpha['offset']), (2, 0))

    def test_child_offsets_show_another_page(self):
        result = self._read(
            limit=1,
            expanded_ids=[self.alpha.id],
            child_offsets={str(self.alpha.id): 1},
        )
        self.assertEqual(self._rows(result), [('Alpha', 0), ('Alpha Two', 1)])
        self.assertEqual(result['records'][0]['__tree__']['offset'], 1)

    def test_expand_all_stops_at_the_limit(self):
        with patch('odoo.addons.muk_web_tree.models.base.EXPAND_ALL_LIMIT', 3):
            result = self._read(expand_all=True)
        self.assertEqual(
            self._rows(result),
            [('Alpha', 0), ('Alpha One', 1), ('Beta', 0)],
        )
        self.assertEqual(result['records'][0]['__tree__']['count'], 2)

    def test_search_count_counts_the_roots(self):
        partner = self.env['res.partner']
        self.assertEqual(partner.web_tree_search_count(self.domain, 'parent_id'), 2)
        domain = [*self.domain, ('name', '=', 'Alpha Two Leaf')]
        self.assertEqual(partner.web_tree_search_count(domain, 'parent_id'), 1)

    def test_default_treelist_view(self):
        result = self.env['res.partner.category'].get_views([(False, 'treelist')])
        arch = result['views']['treelist']['arch']
        self.assertIn('<treelist', arch)
        self.assertIn('parent_field="parent_id"', arch)

    def test_rollups_skip_context_rows(self):
        domain = [*self.domain, ('name', '=', 'Alpha Two Leaf')]
        result = self._read(domain, expand_context=True, rollup_fields=['color'])
        rollups = {row['name']: row['__tree__']['rollups'] for row in result['records']}
        self.assertEqual(rollups['Alpha'], {'color': 4})
        self.assertEqual(rollups['Alpha Two'], {'color': 4})

    def test_children_page_with_offset(self):
        result = self._read(parent_id=self.alpha.id, limit=1)
        self.assertEqual(self._rows(result), [('Alpha One', 0)])
        self.assertEqual(result['length'], 2)
        result = self._read(parent_id=self.alpha.id, limit=1, offset=1)
        self.assertEqual(self._rows(result), [('Alpha Two', 0)])

    def test_deep_tree(self):
        category = self.env['res.partner.category']
        nodes = category
        for depth in range(15):
            nodes |= category.create(
                {'name': f'Deep {depth:02d}', 'parent_id': nodes[-1:].id, 'color': 1}
            )
        domain = [('name', '=like', 'Deep %')]
        result = self._read(
            domain,
            model='res.partner.category',
            expanded_ids=nodes.ids,
            rollup_fields=['color'],
        )
        self.assertEqual(
            self._rows(result), [(f'Deep {depth:02d}', depth) for depth in range(15)]
        )
        self.assertEqual(result['records'][0]['__tree__']['rollups'], {'color': 15})
        result = self._read(
            [('name', '=', 'Deep 14')],
            model='res.partner.category',
            search=True,
            expand_context=True,
        )
        self.assertEqual(len(result['records']), 15)
        self.assertEqual(result['records'][-1]['__tree__']['level'], 14)
        self.assertTrue(
            all(row['__tree__']['context'] for row in result['records'][:-1])
        )

    def test_wide_tree_pages_every_level(self):
        category = self.env['res.partner.category']
        root = category.create({'name': 'Wide Root'})
        children = category.create(
            [{'name': f'Wide {index:03d}', 'parent_id': root.id} for index in range(30)]
        )
        category.create(
            [
                {'name': f'Wide {index:03d} Leaf', 'parent_id': children[0].id}
                for index in range(30)
            ]
        )
        result = self._read(
            [('name', '=like', 'Wide %')],
            model='res.partner.category',
            limit=10,
            expanded_ids=[root.id, children[0].id],
        )
        levels = [row['__tree__']['level'] for row in result['records']]
        self.assertEqual(
            (levels.count(0), levels.count(1), levels.count(2)), (1, 10, 10)
        )
        tree = {row['name']: row['__tree__'] for row in result['records']}
        self.assertEqual(tree['Wide Root']['count'], 30)
        self.assertEqual(tree['Wide 000']['count'], 30)
        result = self._read(
            [('name', '=like', 'Wide %')],
            model='res.partner.category',
            limit=10,
            parent_id=root.id,
            offset=20,
        )
        self.assertEqual(result['records'][0]['name'], 'Wide 020')
        self.assertEqual(result['length'], 30)
