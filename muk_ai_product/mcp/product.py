from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIProductTools(models.AbstractModel):
    """Expose what a product says and what may be written to it."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='product_context',
        description=(
            'Read what a product says and what may be written to it: each '
            'text field the database has, with its value in every product '
            'language, fields to propose a value for, fields never to '
            'generate, its images and documents. Call it first. A "markup" field '
            'is HTML shown under the product name, the only heading of the '
            'shop page: write <p> and <ul> with <li>, never a heading (<h1> '
            'to <h6>) or a title of its own. It keeps one HTML structure in '
            'all languages, only its texts translated: write it in en_US '
            'first, then in a further language as {"en_US": <its HTML, '
            'unchanged>, "<language>": <the translated HTML>}. An en_US value '
            'replaces the texts of every language the same dict does not '
            'carry unchanged.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'template_id': {
                    'type': 'integer',
                    'description': 'The product.template id.',
                },
            },
            'required': ['template_id'],
        },
        category='read',
    )
    def _mcp_product_context(self, template_id: int) -> dict:
        """Describe the content of a product per language."""
        return self._mcp_record('product.template', template_id)._ai_product_context()
