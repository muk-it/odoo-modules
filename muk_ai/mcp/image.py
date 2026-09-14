from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import IMAGE_OPTIONS
from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIImage(models.AbstractModel):
    """Expose app-side image generation as an MCP tool.

    The image is answered in the file convention ``export_records`` uses, so
    the session stores it as an attachment and settles its ``cost`` block.
    """

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _image_model(self) -> models.BaseModel:
        """Return the image model of the calling session.

        :raise UserError: when no session is bound or it resolves no image model
        """
        session = self.env['muk_ai.session'].browse(
            self.env.context.get('muk_mcp_session_id') or []
        )
        if not (session and (record := session._resolve_model_for('image'))):
            raise UserError(
                _(
                    'No image model is available to this session. Set a Default '
                    'Image Model on a provider, or pick one on the agent.'
                )
            )
        return record

    @api.model
    def _image_options(
        self,
        size: str | None,
        quality: str | None,
        background: str | None,
    ) -> tuple[dict, list[str]]:
        """Return the adapter options, dropping values :data:`IMAGE_OPTIONS` forbids.

        :return: the options to send and one notice per dropped value
        """
        options = {'size': size, 'quality': quality, 'background': background}
        notices = []
        for name, spec in IMAGE_OPTIONS.items():
            if (value := options[name]) is None or value in spec['enum']:
                continue
            options[name] = None
            notices.append(
                _(
                    '%(option)s "%(value)s" is not supported and was ignored. '
                    'Supported values are: %(allowed)s.',
                    option=name,
                    value=value,
                    allowed=', '.join(spec['enum']),
                )
            )
        return options, notices

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='generate_image',
        description=(
            'Generate one image from a text prompt. Returns the stored image '
            'as a file descriptor with an "image_url": embed it in your reply '
            'as ![alt](image_url) so the user sees it, and mention the '
            '"revised_prompt" when the model rewrote the request. Describe '
            'the subject, style, composition and lighting in the prompt; '
            'call the tool once per image and in parallel for several '
            'variants. "size" is WIDTHxHEIGHT (e.g. 1024x1024, 1536x1024, '
            '1024x1536); the other options take only the values their schema '
            'lists. Each call costs money: the returned "cost" counts against '
            'the turn budget. AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'prompt': {
                    'type': 'string',
                    'description': 'What to render, in detail.',
                },
                'size': {
                    'type': 'string',
                    'description': (
                        'Image dimensions as WIDTHxHEIGHT. Omit for the model default.'
                    ),
                },
                **{
                    name: {
                        'type': 'string',
                        'enum': list(spec['enum']),
                        'description': spec['description'],
                    }
                    for name, spec in IMAGE_OPTIONS.items()
                },
            },
            'required': ['prompt'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_generate_image(
        self,
        prompt: str,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
    ) -> dict:
        """Render ``prompt`` with the resolved image model.

        :return: a file descriptor carrying ``revised_prompt``, ``cost`` and any
            ``warnings``, or ``{prompt, error}`` when the render fails
        :raise UserError: when no usable image model is configured
        """
        record = self._image_model()
        options, warnings = self._image_options(size, quality, background)
        try:
            image = record.provider_id._get_client().generate_image(
                record.technical_name,
                prompt,
                options,
            )
        except UserError as exc:
            return {'prompt': prompt, 'error': str(exc)}
        cost = record._compute_usage_cost(image['usage'])
        result = {
            'type': 'image',
            'filename': f'generated.{image["mimetype"].rpartition("/")[2]}',
            'mimetype': image['mimetype'],
            'content_base64': image['data_b64'],
            'model': record.technical_name,
            'revised_prompt': image['revised_prompt'],
            'cost': {
                'usage': image['usage'],
                'total': cost['total_cost'],
                'currency': record.currency,
            },
        }
        if warnings:
            result['warnings'] = warnings
        return result
