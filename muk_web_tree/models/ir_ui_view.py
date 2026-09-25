from __future__ import annotations

from lxml import etree

from odoo import fields, models

from odoo.addons.base.models.ir_ui_view import NameManager


class IrUiView(models.Model):
    """Register the treelist view type and validate its architecture."""

    _inherit = 'ir.ui.view'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    type = fields.Selection(
        selection_add=[('treelist', 'Tree List')],
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _get_view_info(self) -> dict:
        """Give the treelist view its switcher icon."""
        return {'treelist': {'icon': 'account_tree'}} | super()._get_view_info()

    def _get_view_fields(self, view_type: str, models: dict) -> dict:
        """Load the fields a treelist needs like those of a list."""
        if view_type == 'treelist':
            view_type = 'list'
        return super()._get_view_fields(view_type, models)

    def _add_missing_fields(
        self, node: etree._Element, name_manager: NameManager
    ) -> dict:
        """Hide the added fields of a treelist as columns instead of cells."""
        missing_fields = super()._add_missing_fields(node, name_manager)
        if node.tag == 'treelist':
            for item in node.iterchildren('field'):
                if item.get('data-used-by') and 'invisible' in item.attrib:
                    item.set('column_invisible', item.attrib.pop('invisible'))
        return missing_fields

    def _postprocess_tag_treelist(
        self, node: etree._Element, name_manager: NameManager, node_info: dict
    ) -> None:
        """Post-process a treelist node like a list node."""
        self._postprocess_tag_list(node, name_manager, node_info)

    def _editable_tag_treelist(
        self, node: etree._Element, name_manager: NameManager
    ) -> bool:
        """Consider a treelist editable under the same rules as a list."""
        return self._editable_tag_list(node, name_manager)

    def _onchange_able_view_treelist(self, node: etree._Element) -> bool:
        """Run onchanges on inline edited treelist rows."""
        return True

    def _modifiers_from_model(self, node: etree._Element) -> list[str]:
        """Take the readonly and required modifiers of the model fields."""
        if node.tag == 'treelist':
            return ['readonly', 'required']
        return super()._modifiers_from_model(node)

    def _validate_tag_treelist(
        self, node: etree._Element, name_manager: NameManager, node_info: dict
    ) -> None:
        """Validate a treelist node like a list and check its parent field."""
        self._validate_tag_list(node, name_manager, node_info)
        if not node_info['validate']:
            return
        parent_field = node.get('parent_field', 'parent_id')
        model = name_manager.model
        field = model._fields.get(parent_field)
        if not field or field.type != 'many2one' or field.comodel_name != model._name:
            self._raise_view_error(
                self.env._(
                    'The parent field "%(field)s" of a tree list must be a many2one '
                    'to "%(model)s".',
                    field=parent_field,
                    model=model._name,
                ),
                node,
            )
