from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_mcp.core.prompt import mcp_prompt


class MCPMixin(models.AbstractModel):
    """Add MCP prompt definitions to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_prompt(
        name='summarize_record',
        title='Summarize a record',
        description=(
            'Produce a concise natural-language summary of a single Odoo '
            'record. The assistant should load the record with the '
            'read_records tool, then summarize its key fields, statuses '
            'and linked records.'
        ),
        arguments=[
            {
                'name': 'model',
                'description': "Technical model name, e.g. 'sale.order'.",
                'required': True,
            },
            {
                'name': 'record_id',
                'description': 'Database id of the record to summarize.',
                'required': True,
            },
        ],
    )
    def _mcp_prompt_summarize_record(self, model: str, record_id: int) -> str:
        """Build the summarize-record prompt instructing the assistant to read then summarize the record."""
        return (
            'Summarize the Odoo %(model)s record with id %(rid)s. First call '
            'the read_records tool with model=%(model)r and ids=[%(rid)s] to '
            'load the record, then write a short, factual summary of its most '
            'important fields, current status and linked records. Call out '
            'anything that looks incomplete or needs attention.'
            % {
                'model': model,
                'rid': record_id,
            }
        )
