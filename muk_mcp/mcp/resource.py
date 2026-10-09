from odoo import api, fields, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.models.transfer import TRANSFER_MINUTES
from odoo.addons.muk_mcp.tools.descriptions import HTTP_HINT


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='authorize_download',
        description=(
            'Get a one-time link to download a file over plain HTTP: an '
            'attachment (odoo://attachment/<id>) or a binary field '
            '(odoo://record/<model>/<id>/<field>). Fetch it with an HTTP GET '
            f'(curl -o <path> <url>) within {TRANSFER_MINUTES} minutes. '
            + HTTP_HINT
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'uri': {
                    'type': 'string',
                    'description': (
                        'Resource uri, e.g. "odoo://attachment/42" or '
                        '"odoo://record/res.partner/5/image_1920".'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['uri'],
        },
        category='read',
        registry='mcp',
    )
    def _mcp_authorize_download(self, uri):
        """Check the resource is readable and issue the link that streams it."""
        self._resolve_resource_target(uri)
        transfer, url = self.env['muk_mcp.transfer']._issue('download', uri=uri)
        return {
            'download_url': url,
            'method': 'GET',
            'expires_at': fields.Datetime.to_string(transfer.expires_at),
            'example': f'curl -o "<path>" "{url}"',
        }
