from __future__ import annotations

from odoo import fields, models, tools

from odoo.addons.muk_ai.tools.sources import UNSET_MODULE_ICON, web_icon_url


class IrModel(models.Model):
    """Carry the AI metadata of a model: approval sensitivity and app icon."""

    _inherit = 'ir.model'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_sensitive = fields.Boolean(
        string='Sensitive for AI',
        help=(
            'Creates on this model trigger an approval prompt for AI '
            'agents, regardless of which fields are written.'
        ),
        default=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_module_icons(self) -> dict[str, str]:
        """Map installed modules that ship a real icon to their icon path."""
        modules = (
            self.env['ir.module.module']
            .sudo()
            .search_read([('state', '=', 'installed')], ['name', 'icon'])
        )
        return {
            module['name']: module['icon']
            for module in modules
            if module['icon'] and module['icon'] != UNSET_MODULE_ICON
        }

    def _ai_app_icons(self) -> dict[str, str]:
        """Map models to the icon of the lowest-sequence app whose menu opens them."""
        menus = self.env['ir.ui.menu'].sudo().with_context(active_test=False)
        roots = {
            root['id']: (root['sequence'], root['web_icon'])
            for root in menus.search_read(
                [('parent_id', '=', False), ('web_icon', '!=', False)],
                ['sequence', 'web_icon'],
            )
        }
        roots_by_action: dict[int, list[int]] = {}
        for entry in menus.search_read(
            [('action', '!=', False)], ['action', 'parent_path']
        ):
            if not entry['action'].startswith('ir.actions.act_window,'):
                continue
            root_id = int(entry['parent_path'].split('/', 1)[0])
            if root_id in roots:
                action_id = int(entry['action'].split(',')[1])
                roots_by_action.setdefault(action_id, []).append(root_id)
        windows = (
            self.env['ir.actions.act_window']
            .sudo()
            .search_read(
                [('id', 'in', list(roots_by_action)), ('res_model', '!=', False)],
                ['res_model'],
            )
        )
        best: dict[str, tuple[tuple[int, int], str]] = {}
        for window in windows:
            for root_id in roots_by_action[window['id']]:
                sequence, web_icon = roots[root_id]
                if not (url := web_icon_url(web_icon)):
                    continue
                rank = (sequence, root_id)
                current = best.get(window['res_model'])
                if current is None or rank < current[0]:
                    best[window['res_model']] = (rank, url)
        return {model: entry[1] for model, entry in best.items()}

    @tools.ormcache()
    def _ai_source_icons(self) -> dict[str, str]:
        """Map each model to the icon of the app a record of it belongs to.

        Resolution is layered, and the order is the point. A module named
        exactly like the model's prefix wins because that answer does not
        change when unrelated modules are installed; only the models it cannot
        answer for fall through to the app whose menu opens them, which is
        ambiguous (a partner is reachable from seven apps) and so is settled by
        app sequence. Models left unresolved get no icon at all rather than the
        placeholder, so the client shows its own glyph instead of a cube that
        reads as a real but wrong app.

        :return: model name mapped to the icon URL it resolves to
        """
        icons = self._ai_app_icons()
        by_module = self._ai_module_icons()
        for record in self.sudo().search_read([], ['model']):
            if icon := by_module.get(record['model'].split('.')[0]):
                icons[record['model']] = icon
        return icons
