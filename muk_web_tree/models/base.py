from __future__ import annotations

from collections import Counter, defaultdict

from lxml import etree

from odoo import api, models
from odoo.fields import Domain
from odoo.orm.query import Query
from odoo.tools import SQL

EXPAND_ALL_LIMIT = 2000
ROLLUP_FIELD_TYPES = ('integer', 'float', 'monetary')


class Base(models.AbstractModel):
    """Read records as a tree of parents and children for the treelist view."""

    _inherit = 'base'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _tree_context(
        self, domain: Domain, parent_field: str
    ) -> tuple[dict[int, int], dict[int, int]]:
        """Return the matches and their accessible ancestors outside the domain."""
        matched = self._search(domain)
        matched.order = None
        rows = self.env.execute_query(
            matched.select(matched.table.id, matched.table[parent_field])
        )
        matched = dict(rows)
        start_ids = list(
            {parent_id for parent_id in matched.values() if parent_id} - set(matched)
        )
        if not start_ids:
            return matched, {}
        accessible = self._search(Domain.TRUE)
        accessible.order = None
        rows = self.env.execute_query(
            SQL(
                """
                WITH RECURSIVE tree_up(id, parent_id) AS (
                    SELECT node.id, node.%(parent)s
                      FROM %(table)s AS node
                     WHERE node.id = ANY(%(start_ids)s)
                       AND EXISTS (
                           SELECT 1
                             FROM (%(accessible)s) AS tree_access
                            WHERE tree_access.id = node.id
                       )
                     UNION
                    SELECT node.id, node.%(parent)s
                      FROM tree_up
                      JOIN %(table)s AS node ON node.id = tree_up.parent_id
                     WHERE EXISTS (
                           SELECT 1
                             FROM (%(accessible)s) AS tree_access
                            WHERE tree_access.id = node.id
                     )
                )
                SELECT id, parent_id FROM tree_up
                """,
                parent=SQL.identifier(parent_field),
                table=SQL.identifier(self._table),
                start_ids=start_ids,
                accessible=accessible.select(),
            )
        )
        return matched, {
            record_id: parent_id
            for record_id, parent_id in rows
            if record_id not in matched
        }

    @api.model
    def _tree_with(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        context: dict[int, int],
        parent_field: str,
        *ctes: SQL,
    ) -> SQL:
        """Return the common table expressions of the visible tree.

        ``tree_visible`` holds the visible records with their parent and whether
        they match. The nodes of a search are listed once, else the domain is
        inlined so that the database plans it with its own statistics.
        """
        if nodes is None:
            query = self._search(domain)
            query.order = None
            visible = SQL(
                'tree_visible AS NOT MATERIALIZED (%s)',
                query.select(
                    SQL('%s AS id', query.table.id),
                    SQL('%s AS parent_id', query.table[parent_field]),
                    SQL('TRUE AS matched'),
                ),
            )
        else:
            visible = SQL(
                """
                tree_visible AS MATERIALIZED (
                    SELECT node.id, node.%s AS parent_id,
                           NOT (node.id = ANY(%s)) AS matched
                      FROM %s AS node
                     WHERE node.id = ANY(%s)
                )
                """,
                SQL.identifier(parent_field),
                list(context),
                SQL.identifier(self._table),
                list(nodes),
            )
        return SQL(
            'WITH RECURSIVE %s%s ',
            visible,
            SQL(', %s', SQL(', ').join(ctes)) if ctes else SQL(),
        )

    @api.model
    def _tree_top_query(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        parent_field: str,
        parent_id: int | None,
        **kwargs,
    ) -> Query:
        """Return a query of the top records: the roots or the children.

        The top records of a search are picked from its nodes, else the roots
        are the records of the domain whose parent is outside of it.
        """
        extra = Domain(parent_field, '=', parent_id) if parent_id else Domain.TRUE
        if nodes is not None:
            top_ids = [
                record_id
                for record_id, node_parent_id in nodes.items()
                if (
                    node_parent_id == parent_id
                    if parent_id
                    else node_parent_id not in nodes
                )
            ]
            return self._search(extra & Domain('id', 'in', top_ids), **kwargs)
        query = self._search(domain & extra, **kwargs)
        if not parent_id:
            parent = query.table[parent_field]
            query.add_where(
                SQL(
                    """
                    (%s IS NULL OR NOT EXISTS (
                        SELECT 1 FROM tree_visible AS tree_up WHERE tree_up.id = %s
                    ))
                    """,
                    parent,
                    parent,
                )
            )
        return query

    @api.model
    def _tree_frame(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        context: dict[int, int],
        parent_field: str,
        parent_id: int | None,
        offset: int,
        limit: int | None,
        order: str | None,
        count_limit: int | None,
    ) -> tuple[list[int], int]:
        """Return the page of top records and their count, up to the limit."""
        page = self._tree_top_query(
            domain,
            nodes,
            parent_field,
            parent_id,
            offset=offset,
            limit=limit,
            order=order or self._order,
        )
        rank = SQL('ROW_NUMBER() OVER (ORDER BY %s)', page.order)
        count = self._tree_top_query(
            domain, nodes, parent_field, parent_id, limit=count_limit
        )
        count.order = None
        rows = self.env.execute_query(
            SQL(
                """
                %s
                SELECT tree_page.id, tree_page.rank
                  FROM (%s) AS tree_page
                 UNION ALL
                SELECT NULL, COUNT(*)
                  FROM (%s) AS tree_count
                """,
                self._tree_with(domain, nodes, context, parent_field)
                if nodes is None
                else SQL(),
                page.select(SQL('%s AS id', page.table.id), SQL('%s AS rank', rank)),
                count.select(),
            )
        )
        page_rows = sorted((rank, record_id) for record_id, rank in rows if record_id)
        total = next(rank for record_id, rank in rows if record_id is None)
        return [record_id for _rank, record_id in page_rows], total

    @api.model
    def _tree_children(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        parent_field: str,
        child_offsets: dict[int, int],
        order: str | None,
        limit: int | None,
        max_rows: int | None,
    ) -> dict[int, list[int]]:
        """Return a page of children of each parent, ranked in SQL by the order.

        Each parent pages its children from its own offset, and no more than
        ``max_rows`` children are returned in all.
        """
        if nodes is None:
            scope = domain & Domain(parent_field, 'in', list(child_offsets))
        else:
            scope = Domain(
                'id',
                'in',
                [
                    record_id
                    for record_id, parent_id in nodes.items()
                    if parent_id in child_offsets
                ],
            )
        query = self._search(scope, order=order or self._order)
        parent = query.table[parent_field]
        rank = SQL(
            'ROW_NUMBER() OVER (PARTITION BY %s ORDER BY %s)', parent, query.order
        )
        query.order = None
        rows = self.env.execute_query(
            SQL(
                """
                SELECT tree_child.id, tree_child.parent_id
                  FROM (%s) AS tree_child
                  JOIN unnest(%s::integer[], %s::integer[])
                       AS tree_page(parent_id, page_offset)
                    ON tree_page.parent_id = tree_child.parent_id
                 WHERE tree_child.rank > tree_page.page_offset
                   AND (%s::integer IS NULL
                        OR tree_child.rank <= tree_page.page_offset + %s)
                 ORDER BY tree_child.rank
                 LIMIT %s
                """,
                query.select(
                    SQL('%s AS id', query.table.id),
                    SQL('%s AS parent_id', parent),
                    SQL('%s AS rank', rank),
                ),
                list(child_offsets),
                list(child_offsets.values()),
                limit,
                limit,
                max_rows,
            )
        )
        children = defaultdict(list)
        for child_id, parent_id in rows:
            children[parent_id].append(child_id)
        return children

    @api.model
    def _tree_counts(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        parent_field: str,
        parent_ids: list[int],
    ) -> dict[int, int]:
        """Count the visible children of each of the given records."""
        if nodes is not None:
            wanted = set(parent_ids)
            return Counter(parent for parent in nodes.values() if parent in wanted)
        return {
            parent.id: count
            for parent, count in self._read_group(
                domain & Domain(parent_field, 'in', parent_ids),
                [parent_field],
                ['__count'],
            )
        }

    @api.model
    def _tree_rollups(
        self,
        domain: Domain,
        nodes: dict[int, int] | None,
        context: dict[int, int],
        parent_field: str,
        parent_ids: list[int],
        rollup_fields: list[str],
    ) -> dict[int, dict[str, float]]:
        """Sum the rollup fields of the matches in the subtrees of the parents."""
        names = [
            name
            for name in rollup_fields
            if self._fields[name].store
            and self._fields[name].type in ROLLUP_FIELD_TYPES
            and not self._fields[name].company_dependent
        ]
        if not names:
            return {}
        columns = SQL(', ').join(SQL.identifier(name) for name in names)
        values = SQL(', ').join(SQL.identifier('record', name) for name in names)
        node = SQL(
            """
            tree_node(id, root_id, matched, %(columns)s) AS (
                SELECT tree_visible.id, tree_visible.id, tree_visible.matched,
                       %(values)s
                  FROM tree_visible
                  JOIN %(table)s AS record ON record.id = tree_visible.id
                 WHERE tree_visible.id = ANY(%(parent_ids)s)
                 UNION ALL
                SELECT tree_visible.id, tree_node.root_id, tree_visible.matched,
                       %(values)s
                  FROM tree_node
                  JOIN tree_visible ON tree_visible.parent_id = tree_node.id
                  JOIN %(table)s AS record ON record.id = tree_visible.id
            ) CYCLE id SET is_cycle USING cycle_path
            """,
            columns=columns,
            values=values,
            table=SQL.identifier(self._table),
            parent_ids=parent_ids,
        )
        rows = self.env.execute_query(
            SQL(
                """
                %s
                SELECT root_id, %s
                  FROM tree_node
                 WHERE matched AND NOT is_cycle
                 GROUP BY root_id
                """,
                self._tree_with(domain, nodes, context, parent_field, node),
                SQL(', ').join(
                    SQL('COALESCE(SUM(%s), 0)', SQL.identifier(name)) for name in names
                ),
            )
        )
        return {
            row[0]: {
                name: value if isinstance(value, int) else float(value)
                for name, value in zip(names, row[1:], strict=True)
            }
            for row in rows
        }

    @api.model
    def _tree_nodes(
        self, domain: Domain, parent_field: str
    ) -> tuple[dict[int, int], dict[int, int]]:
        """Return the visible records of a search and its context rows.

        Both map a record to its parent: the matches with their accessible
        ancestors, and those ancestors alone. The search runs only once.
        """
        matched, context = self._tree_context(domain, parent_field)
        return {**matched, **context}, context

    def _tree_export_levels(self, parent_field: str) -> dict[int, int]:
        """Return the level of each record, with every parent before its children.

        Siblings keep the order of the recordset, and a record whose parent is
        not in the recordset is a root.
        """
        record_ids = set(self.ids)
        children = defaultdict(list)
        for record in self:
            parent_id = record[parent_field].id
            children[parent_id if parent_id in record_ids else False].append(record.id)
        levels = {}
        stack = [(record_id, 0) for record_id in reversed(children[False])]
        while stack:
            record_id, level = stack.pop()
            levels[record_id] = level
            stack.extend(
                (child_id, level + 1) for child_id in reversed(children[record_id])
            )
        return levels

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _get_default_treelist_view(self) -> etree._Element:
        """Generate a single-field treelist view nesting by the parent field."""
        arch = self._get_default_list_view()
        arch.tag = 'treelist'
        arch.set('parent_field', self._parent_name)
        return arch

    @api.model
    @api.readonly
    def web_tree_search_count(
        self, domain: list, parent_field: str, search: bool = False
    ) -> int:
        """Count the root records of the tree of the given domain."""
        domain = Domain(domain)
        nodes, context = (
            self._tree_nodes(domain, parent_field) if search else (None, {})
        )
        return self._tree_frame(
            domain,
            nodes,
            context,
            parent_field,
            parent_id=None,
            offset=0,
            limit=0,
            order=None,
            count_limit=None,
        )[1]

    @api.model
    @api.readonly
    def web_tree_read(
        self,
        domain: list,
        specification: dict[str, dict],
        parent_field: str,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        count_limit: int | None = None,
        parent_id: int | None = None,
        search: bool = False,
        expanded_ids: list[int] | None = None,
        expand_all: bool = False,
        expand_context: bool = False,
        rollup_fields: list[str] | None = None,
        child_offsets: dict[str, int] | None = None,
    ) -> dict:
        """Read a page of top records with their expanded descendants.

        The top records are the roots, or the children of ``parent_id``, and each
        expanded parent pages its children from its ``child_offsets`` entry.
        When searching, unmatched ancestors of the matches come as context rows.
        """
        domain = Domain(domain)
        nodes, context = (
            self._tree_nodes(domain, parent_field) if search else (None, {})
        )
        top_ids, length = self._tree_frame(
            domain,
            nodes,
            context,
            parent_field,
            parent_id,
            offset,
            limit,
            order,
            count_limit,
        )
        expanded = set(expanded_ids or [])
        if expand_context:
            expanded |= set(context) | set(context.values())
        child_offsets = {
            int(key): value for key, value in (child_offsets or {}).items()
        }
        levels = dict.fromkeys(top_ids, 0)
        children = {}
        frontier = [
            record_id for record_id in top_ids if expand_all or record_id in expanded
        ]
        while frontier:
            remaining = EXPAND_ALL_LIMIT - len(levels) if expand_all else None
            if remaining is not None and remaining <= 0:
                break
            level_children = self._tree_children(
                domain,
                nodes,
                parent_field,
                {record_id: child_offsets.get(record_id, 0) for record_id in frontier},
                order,
                limit,
                remaining,
            )
            children.update(level_children)
            frontier = []
            for record_id, child_ids in level_children.items():
                for child_id in child_ids:
                    levels[child_id] = levels[record_id] + 1
                    if expand_all or child_id in expanded:
                        frontier.append(child_id)
        ordered_ids = []
        stack = list(reversed(top_ids))
        while stack:
            record_id = stack.pop()
            ordered_ids.append(record_id)
            stack.extend(reversed(children.get(record_id, [])))
        counts = (
            self._tree_counts(domain, nodes, parent_field, ordered_ids)
            if ordered_ids
            else {}
        )
        parent_ids = [record_id for record_id in ordered_ids if counts.get(record_id)]
        rollups = (
            self._tree_rollups(
                domain, nodes, context, parent_field, parent_ids, rollup_fields
            )
            if rollup_fields and parent_ids
            else {}
        )
        records = self.browse(ordered_ids).web_read(specification)
        for record in records:
            loaded = len(children.get(record['id'], []))
            record['__tree__'] = {
                'level': levels[record['id']],
                'count': counts.get(record['id'], 0),
                'offset': child_offsets.get(record['id'], 0) if loaded else 0,
                'context': record['id'] in context,
                'expanded': bool(loaded),
                'rollups': rollups.get(record['id'], {}),
            }
        if not limit or len(top_ids) < limit:
            length = offset + len(top_ids)
        return {'length': length, 'records': records}
