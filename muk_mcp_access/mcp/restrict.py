from odoo import api, models


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_search_count(self, model, domain=None):
        return super()._mcp_search_count(
            model, domain=self._mcp_apply_domain(model, domain),
        )

    @api.model
    def _mcp_search_read(
        self,
        model,
        domain=None,
        fields=None,
        limit=80,
        offset=0,
        order=None,
    ):
        return super()._mcp_search_read(
            model,
            domain=self._mcp_apply_domain(model, domain),
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

    @api.model
    def _mcp_read_group(
        self,
        model,
        groupby,
        aggregates=None,
        domain=None,
        limit=None,
        order=None,
    ):
        return super()._mcp_read_group(
            model,
            groupby,
            aggregates=aggregates,
            domain=self._mcp_apply_domain(model, domain),
            limit=limit,
            order=order,
        )

    @api.model
    def _mcp_read_records(self, model, ids, fields=None):
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_read_records(model, ids, fields=fields)

    @api.model
    def _mcp_create_records(self, model, values):
        result = super()._mcp_create_records(model, values)
        self._mcp_assert_records_allowed(model, [result['id']])
        return result

    @api.model
    def _mcp_update_records(self, model, ids, values):
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_update_records(model, ids, values)

    @api.model
    def _mcp_delete_records(self, model, ids):
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_delete_records(model, ids)
