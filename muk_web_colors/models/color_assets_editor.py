from __future__ import annotations

from collections.abc import Sequence

from odoo import api, models
from odoo.tools import file_open

from odoo.addons.base.models.assetsbundle import EXTENSIONS
from odoo.addons.muk_web_colors.tools import read_variables, replace_variables


class ColorAssetsEditor(models.AbstractModel):
    """Read, write and reset the customized SCSS color variable assets."""

    _name = 'muk_web_colors.color_assets_editor'
    _description = 'Color Assets Editor'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_custom_colors_url(self, url: str, bundle: str) -> str:
        """Return the attachment URL holding the customized color asset."""
        return f'/_custom/{bundle}{url}'

    @api.model
    def _get_colors_attachment(self, custom_url: str) -> models.BaseModel:
        """Return the attachment storing the customized color asset."""
        return self.env['ir.attachment'].search([('url', '=', custom_url)])

    @api.model
    def _get_colors_asset(self, custom_url: str) -> models.BaseModel:
        """Return the ``ir.asset`` record replacing the original color asset."""
        return self.env['ir.asset'].search([('path', '=', custom_url)])

    @api.model
    def _get_colors_content(self, url: str, bundle: str) -> str:
        """Return the color asset content, preferring the customized copy."""
        attachment = self._get_colors_attachment(
            self._get_custom_colors_url(url, bundle)
        )
        if attachment:
            return attachment.raw.decode('utf-8')
        with file_open(url.strip('/'), 'rb', filter_ext=EXTENSIONS) as asset:
            return asset.read().decode('utf-8')

    @api.model
    def _save_colors_content(self, url: str, bundle: str, content: str) -> None:
        """Store the color content as an attachment replacing the bundled asset."""
        custom_url = self._get_custom_colors_url(url, bundle)
        raw = (content or '\n').encode('utf-8')
        attachment = self._get_colors_attachment(custom_url)
        if attachment:
            attachment.write({'raw': raw})
            self.env.transaction.invalidate_ormcache('assets')
            return
        self.env['ir.attachment'].create(
            {
                'name': url.rsplit('/', maxsplit=1)[-1],
                'type': 'binary',
                'mimetype': 'text/scss',
                'raw': raw,
                'url': custom_url,
            }
        )
        self.env['ir.asset'].create(
            {
                'name': f'{bundle}: replace {custom_url.rsplit("/", maxsplit=1)[-1]}',
                'bundle': self.env['ir.asset']._get_related_bundle(url, bundle),
                'path': custom_url,
                'target': url,
                'directive': 'replace',
            }
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @api.private
    def read_colors(self, url: str, bundle: str, names: Sequence[str]) -> dict:
        """Return the current value of each named color variable."""
        return read_variables(self._get_colors_content(url, bundle), names)

    @api.model
    @api.private
    def write_colors(self, url: str, bundle: str, values: dict) -> None:
        """Assign the given values to the color variables and save the asset."""
        content = replace_variables(self._get_colors_content(url, bundle), values)
        self._save_colors_content(url, bundle, content)

    @api.model
    @api.private
    def reset_colors(self, url: str, bundle: str) -> None:
        """Delete the customized attachment and ``ir.asset`` of a color bundle."""
        custom_url = self._get_custom_colors_url(url, bundle)
        self._get_colors_attachment(custom_url).unlink()
        self._get_colors_asset(custom_url).unlink()
