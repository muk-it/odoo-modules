from __future__ import annotations

import json
import shutil
import time
from contextlib import closing
from datetime import timedelta

import requests

from odoo import _, api, fields, models, release
from odoo.tools import config
from odoo.tools.parse_version import parse_version
from odoo.tools.safe_eval import datetime, safe_eval

from odoo.addons.base.models.ir_module import assert_log_admin_access
from odoo.addons.muk_check.tools.odoo_release import (
    build_date,
    fetch_image_builds,
    installed_build,
)
from odoo.addons.muk_check.tools.server import (
    is_odoo_sh,
    master_password_is_default,
    read_option,
)


class CheckRule(models.Model):
    """One question asked about the database, passed when the answer is empty."""

    _name = 'muk_check.rule'
    _description = 'Check Rule'
    _order = 'category, name'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def IMAGE_BUILDS_PARAMETER(self) -> str:
        """Return the parameter holding the last answer from Docker Hub."""
        return 'muk_check.image_builds'

    @property
    def SUPPORTED_SERIES(self) -> int:
        """Return how many of the newest series Odoo supports."""
        return 3

    @property
    def FINDINGS_LIMIT(self) -> int:
        """Return how many records one rule reports at most."""
        return 200

    @property
    def INACTIVE_ADMIN_DAYS(self) -> int:
        """Return after how many days an administrator counts as inactive."""
        return 90

    @property
    def BUILD_MAX_DAYS_BEHIND(self) -> int:
        """Return how many days a build can be behind the newest image."""
        return 30

    @property
    def DISK_MIN_FREE_RATIO(self) -> float:
        """Return the share of the disk that has to stay free."""
        return 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )

    description = fields.Text(
        string='Why It Matters',
        translate=True,
    )

    recommendation = fields.Text(
        string='How to Fix',
        translate=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    category = fields.Selection(
        selection=[
            ('odoo', 'Odoo Version'),
            ('server', 'Server'),
            ('website', 'Website'),
            ('signin', 'Sign-in'),
            ('accounts', 'Accounts'),
            ('modules', 'Modules and Code'),
            ('mail', 'Mail and URL'),
            ('apps', 'Apps'),
            ('custom', 'Custom'),
        ],
        string='Category',
        required=True,
        default='custom',
    )

    severity = fields.Selection(
        selection='_selection_severity',
        string='Severity',
        required=True,
        default='medium',
    )

    severity_override = fields.Selection(
        selection='_selection_severity',
        string='Your Severity',
        help='Replaces the severity of this rule, and an upgrade keeps it.',
    )

    severity_effective = fields.Selection(
        compute='_compute_severity_effective',
        selection='_selection_severity',
        string='Effective Severity',
        store=True,
    )

    module_ids = fields.Many2many(
        comodel_name='ir.module.module',
        relation='muk_check_rule_module_rel',
        column1='rule_id',
        column2='module_id',
        string='Needs Modules',
        help='Without these modules installed the rule does not apply.',
    )

    kind = fields.Selection(
        selection=[
            ('records', 'Records'),
            ('expression', 'Expression'),
        ],
        string='Kind',
        required=True,
        default='records',
    )

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Model',
        help='The model the rule searches, or of the records its expression returns.',
        domain=lambda self: self._domain_model_id(),
    )

    model_name = fields.Char(
        related='model_id.model',
        string='Model Name',
    )

    domain = fields.Char(
        string='Domain',
        default='[]',
    )

    expression = fields.Text(
        string='Expression',
    )

    detail_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Detail Field',
        help='Field of the matching record that tells one finding from the next.',
    )

    action_id = fields.Many2one(
        comodel_name='ir.actions.act_window',
        string='Fix Screen',
        help='The screen that opens to fix this.',
    )

    is_custom = fields.Boolean(
        compute='_compute_is_custom',
        string='Custom Rule',
    )

    state = fields.Selection(
        selection=[
            ('passed', 'Passed'),
            ('failed', 'Failed'),
            ('not_applicable', 'Not Applicable'),
            ('error', 'Error'),
        ],
        string='Last Result',
        readonly=True,
        copy=False,
    )

    error = fields.Text(
        string='Error',
        readonly=True,
        copy=False,
    )

    duration = fields.Float(
        string='Duration (s)',
        readonly=True,
        copy=False,
    )

    finding_ids = fields.One2many(
        comodel_name='muk_check.finding',
        inverse_name='rule_id',
        string='Findings',
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _selection_severity(self) -> list[tuple[str, str]]:
        """Return the severity levels from most to least severe."""
        return [
            ('critical', _('Critical')),
            ('high', _('High')),
            ('medium', _('Medium')),
            ('low', _('Low')),
        ]

    @api.model
    def _domain_model_id(self) -> list:
        """Return the domain of the models a rule can search."""
        abstract = [
            name for name, model in self.env.registry.items() if model._abstract
        ]
        return [('transient', '=', False), ('model', 'not in', abstract)]

    def _is_applicable(self) -> bool:
        """Return whether the modules and the model of the rule are present."""
        return all(module.state == 'installed' for module in self.module_ids) and (
            self.kind != 'records' or bool(self.model_id)
        )

    def _ask(self) -> object:
        """Return the answer of the rule to its question."""
        context = {
            'env': self.env,
            'config': read_option,
            'master_password_is_default': master_password_is_default,
            'is_odoo_sh': is_odoo_sh,
            'datetime': datetime,
        }
        if self.kind == 'records':
            domain = safe_eval(self.domain or '[]', context)
            return self.env[self.model_name].search(domain, limit=self.FINDINGS_LIMIT)
        return safe_eval(self.expression, context)

    def _finding_values(self, answer) -> list[dict]:
        """Turn the answer of the rule into the values of its findings."""
        if isinstance(answer, models.BaseModel):
            field = self.detail_field_id.name
            return [
                {
                    'res_model': record._name,
                    'res_id': record.id,
                    'target': record.display_name,
                    'detail': (
                        field
                        and record[field]
                        and record._fields[field].convert_to_display_name(
                            record[field], record
                        )
                    )
                    or False,
                }
                for record in answer
            ]
        if not answer:
            return []
        if answer is True:
            return [{}]
        texts = [answer] if isinstance(answer, str) else answer
        return [{'detail': text} for text in dict.fromkeys(map(str, texts))]

    def _sync_findings(self, values: list[dict]) -> None:
        """Open, keep, reopen or resolve the findings of the rule from its answer."""
        known = {
            (finding.res_model, finding.res_id, finding.detail): finding
            for finding in self.finding_ids
        }
        today = fields.Date.context_today(self)
        expired = self.finding_ids.filtered(
            lambda finding: finding.accepted_until and finding.accepted_until < today
        )
        for value in values:
            key = (
                value.get('res_model', False),
                value.get('res_id', 0),
                value.get('detail', False),
            )
            finding = known.pop(key, None)
            if not finding:
                self.env['muk_check.finding'].create({'rule_id': self.id, **value})
                continue
            finding.write({**value, 'last_seen': fields.Datetime.now()})
            if finding.state == 'resolved' or (
                finding.state == 'accepted' and finding in expired
            ):
                finding.action_reopen()
                finding.notified = False
        for finding in known.values():
            if finding.state != 'accepted' or finding in expired:
                finding.state = 'resolved'

    def _run_rule(self) -> None:
        """Ask the rule in a savepoint that is always rolled back, then record it."""
        started = time.monotonic()
        result = {'state': 'not_applicable', 'error': False}
        values = []
        if self._is_applicable():
            try:
                with closing(self.env.cr.savepoint()):
                    answer = self._ask()
                    if answer is not None:
                        values = self._finding_values(answer)
                        result['state'] = 'failed' if values else 'passed'
            except Exception as error:
                result = {'state': 'error', 'error': str(error)}
        self.write({**result, 'duration': time.monotonic() - started})
        if result['state'] != 'error':
            self._sync_findings(values)

    def _image_builds(self) -> dict[str, str]:
        """Return the last known build date of each series, if online checks run."""
        parameters = self.env['ir.config_parameter'].sudo()
        if parameters.get_param('muk_check.online', 'True') == 'False':
            return {}
        return json.loads(parameters.get_param(self.IMAGE_BUILDS_PARAMETER) or '{}')

    def _update_image_builds(self) -> None:
        """Read the newest image builds, keeping the last answer on failure."""
        try:
            builds = fetch_image_builds()
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return
        if builds:
            self.env['ir.config_parameter'].sudo().set_param(
                self.IMAGE_BUILDS_PARAMETER, json.dumps(builds)
            )

    def _check_series_unsupported(self) -> bool | None:
        """Return whether the running series is too old to be supported."""
        builds = self._image_builds()
        if not builds:
            return None
        supported = sorted(builds, key=parse_version)[-self.SUPPORTED_SERIES :]
        return parse_version(release.serie) < parse_version(supported[0])

    def _check_newer_series(self) -> bool | None:
        """Return whether a newer series than the running one is available."""
        builds = self._image_builds()
        if not builds:
            return None
        newest = max(builds, key=parse_version)
        return parse_version(newest) > parse_version(release.serie)

    def _check_build_behind(self) -> str | None:
        """Return the installed and newest build when the gap is too large."""
        newest = self._image_builds().get(release.serie)
        installed = installed_build()
        if not newest or not installed:
            return None
        behind = build_date(newest) - build_date(installed)
        if behind.days > self.BUILD_MAX_DAYS_BEHIND:
            return installed
        return ''

    def _check_database_superuser(self) -> bool:
        """Return whether Odoo connects to PostgreSQL as a superuser."""
        self.env.cr.execute("SELECT current_setting('is_superuser') = 'on'")
        return self.env.cr.fetchone()[0]

    def _check_disk_space(self) -> bool:
        """Return whether the disk holding the Odoo files is almost full."""
        usage = shutil.disk_usage(config['data_dir'])
        return usage.free / usage.total < self.DISK_MIN_FREE_RATIO

    def _check_inactive_admins(self) -> models.BaseModel:
        """Return the administrators without a recent login."""
        limit = fields.Datetime.now() - timedelta(days=self.INACTIVE_ADMIN_DAYS)
        return self.env.ref('base.group_system').users.filtered(
            lambda user: (user.login_date or user.create_date) < limit
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @assert_log_admin_access
    def action_run_rule(self) -> None:
        """Run this rule alone, without refreshing the online information."""
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        self.sudo()._run_rule()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('severity', 'severity_override')
    def _compute_severity_effective(self) -> None:
        """Prefer the severity chosen in this database over the shipped one."""
        for rule in self:
            rule.severity_effective = rule.severity_override or rule.severity

    @api.depends('name')
    def _compute_is_custom(self) -> None:
        """Mark the rules no module ships, which are fully editable."""
        external_ids = self.get_external_id()
        for rule in self:
            external_id = external_ids.get(rule.id) or '__'
            rule.is_custom = external_id.startswith('__')
