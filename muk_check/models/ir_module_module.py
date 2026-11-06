from __future__ import annotations

import json
import logging
from collections import defaultdict

import requests

from odoo import fields, models, release
from odoo.tools.parse_version import parse_version

from odoo.addons.base.models.ir_module import assert_log_admin_access
from odoo.addons.base_import_module.models.ir_module import APPS_URL
from odoo.addons.muk_check.tools.fingerprint import (
    database_terms,
    digest,
    field_argument,
    upgrade_files,
)

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    """Report store versions, pending upgrades and changed translations."""

    _inherit = 'ir.module.module'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def UPDATE_CHECK_DOMAIN(self) -> list:
        """Return the domain of the modules the update check covers."""
        return [
            ('state', '=', 'installed'),
            ('imported', '=', False),
            ('author', 'not ilike', 'Odoo S'),
            ('author', 'not ilike', 'Odoo PS'),
            ('author', 'not =ilike', 'Odoo'),
        ]

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    store_version = fields.Char(
        string='On Store',
        readonly=True,
    )

    store_changelog = fields.Html(
        string='Changelog',
        readonly=True,
    )

    store_checked_at = fields.Datetime(
        string='Last Checked',
        readonly=True,
    )

    store_status = fields.Selection(
        selection=[('update', 'Store Update')],
        string='Store Status',
        readonly=True,
    )

    upgrade_status = fields.Selection(
        selection=[('needed', 'Upgrade Needed')],
        string='Upgrade Status',
        readonly=True,
    )

    translation_status = fields.Selection(
        selection=[('changed', 'Translations Changed')],
        string='Translation Status',
        readonly=True,
    )

    disk_status = fields.Selection(
        selection=[('missing', 'Missing')],
        string='Disk Status',
        readonly=True,
    )

    upgrade_fingerprint = fields.Char(
        string='Upgrade Baseline',
        readonly=True,
    )

    translation_fingerprint = fields.Char(
        string='Translation Baseline',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _schema_signatures(self) -> dict[str, list[str]]:
        """Return what each module itself declares of fields and table objects."""
        definitions = {
            definition
            for model in self.env.registry.values()
            for definition in model.mro()
            if getattr(definition, '_field_definitions', None) is not None
            and getattr(definition, 'pool', None) is None
        }
        signatures = defaultdict(list)
        for definition in definitions:
            for field in definition._field_definitions:
                arguments = sorted(
                    (key, field_argument(key, value))
                    for key, value in field._args__.items()
                    if not callable(value)
                )
                signatures[definition._module].append(
                    f'{definition._name}.{field.name}:{type(field).__name__}:{arguments}'
                )
            for table_object in definition._table_object_definitions:
                sql = table_object.get_definition(self.env.registry)
                signatures[definition._module].append(
                    f'{definition._name}:{table_object.name}:{sql}'
                )
        return signatures

    def _upgrade_fingerprints(self) -> dict[str, str]:
        """Hash what only a database upgrade applies, per module found on disk.

        Covers the data files, the migration scripts, the fields and the table
        objects. Python methods and static assets take effect without an upgrade.
        """
        if not self:
            return {}
        signatures = self._schema_signatures()
        fingerprints = {}
        for name in self.mapped('name'):
            if manifest := self.get_module_info(name):
                fingerprints[name] = digest(
                    upgrade_files(manifest)
                    + [signature.encode() for signature in sorted(signatures[name])]
                )
        return fingerprints

    def _translation_fingerprints(self) -> dict[str, dict[str, str]]:
        """Hash the database terms of the translation files, per module and language.

        Code terms are left out, as they are read from the files at runtime.
        """
        languages = [code for code, _name in self.env['res.lang'].get_installed()]
        return {
            name: {
                language: digest(
                    [term.encode() for term in sorted(database_terms(name, language))]
                )
                for language in languages
            }
            for name in self.mapped('name')
            if self.get_module_info(name)
        }

    def _save_upgrade_baseline(self) -> None:
        """Accept the current data and fields as applied to the database."""
        fingerprints = self._upgrade_fingerprints()
        for module in self.filtered(lambda module: module.name in fingerprints):
            module.write(
                {
                    'upgrade_fingerprint': fingerprints[module.name],
                    'upgrade_status': False,
                }
            )

    def _save_translation_baseline(self) -> None:
        """Accept the current translation files as applied to the database."""
        fingerprints = self._translation_fingerprints()
        for module in self.filtered(lambda module: module.name in fingerprints):
            module.write(
                {
                    'translation_fingerprint': json.dumps(fingerprints[module.name]),
                    'translation_status': False,
                }
            )

    def _update_store_info(self) -> None:
        """Read the published versions from the store, keeping them on failure."""
        try:
            response = requests.post(
                f'{APPS_URL}/apps/embed/update',
                json={
                    'jsonrpc': '2.0',
                    'method': 'call',
                    'params': {
                        'modules': {name: {} for name in self.mapped('name')},
                        'version': {'server_serie': release.serie},
                    },
                },
                timeout=10,
            )
            response.raise_for_status()
            published = {
                name: {
                    'store_version': info.get('version_remote'),
                    'store_changelog': info.get('changelog'),
                }
                for name, info in response.json()['result'].items()
                if info
            }
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as error:
            _logger.warning('The update check could not read the store: %s', error)
            return
        for module in self:
            module.write(
                published.get(
                    module.name, {'store_version': False, 'store_changelog': False}
                )
            )
        self.store_checked_at = fields.Datetime.now()

    def _refresh_update_states(self) -> None:
        """Compare the modules with the store and their saved baselines."""
        upgrades = self._upgrade_fingerprints()
        translations = self._translation_fingerprints()
        for module in self:
            name = module.name
            on_disk = name in upgrades
            newer = (
                on_disk
                and module.store_version
                and parse_version(module.store_version)
                > parse_version(module.installed_version)
            )
            baseline = json.loads(module.translation_fingerprint or '{}')
            current = translations.get(name, {})
            module.write(
                {
                    'store_status': newer and 'update',
                    'upgrade_status': on_disk
                    and upgrades[name] != module.upgrade_fingerprint
                    and 'needed',
                    'translation_status': any(
                        baseline.get(language, value) != value
                        for language, value in current.items()
                    )
                    and 'changed',
                    'translation_fingerprint': json.dumps({**current, **baseline}),
                    'disk_status': not on_disk and 'missing',
                }
            )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @assert_log_admin_access
    def action_check_updates(self) -> None:
        """Run the update check over every covered module."""
        modules = self.search(self.UPDATE_CHECK_DOMAIN)
        if self.env['ir.config_parameter'].sudo().get_bool('muk_check.online', True):
            modules._update_store_info()
            self.env['muk_check.rule'].sudo()._update_image_builds()
        modules._refresh_update_states()

    def action_open_store(self) -> dict:
        """Open the store page of the module."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'{APPS_URL}/apps/modules/{release.serie}/{self.name}/',
            'target': 'new',
        }

    @assert_log_admin_access
    def action_dismiss_upgrade(self) -> None:
        """Clear a pending upgrade without upgrading."""
        self._save_upgrade_baseline()

    @assert_log_admin_access
    def action_reload_translations(self) -> None:
        """Load the translation files, overwriting on the context's request."""
        self._update_translations(overwrite=self.env.context.get('overwrite', False))
        self._save_translation_baseline()

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _register_hook(self) -> None:
        """Save the baselines of the modules just upgraded or first seen."""
        super()._register_hook()
        modules = self.search(self.UPDATE_CHECK_DOMAIN)
        updated = self.env.registry.updated_modules
        modules.filtered(
            lambda module: module.name in updated or not module.upgrade_fingerprint
        )._save_upgrade_baseline()
        modules.filtered(
            lambda module: not module.translation_fingerprint
        )._save_translation_baseline()
