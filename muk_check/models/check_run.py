from __future__ import annotations

from datetime import date

from odoo import SUPERUSER_ID, api, fields, models, release
from odoo.tools import format_datetime

from odoo.addons.base.models.ir_module import assert_log_admin_access
from odoo.addons.muk_check.tools.odoo_release import installed_build
from odoo.addons.muk_check.tools.server import is_odoo_sh


class CheckRun(models.Model):
    """The score and the counts of one run of all rules."""

    _name = 'muk_check.run'
    _description = 'Check Run'
    _order = 'id desc'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def SEVERITY_WEIGHTS(self) -> dict[str, int]:
        """Return the points an open finding of each severity costs."""
        return {'critical': 20, 'high': 10, 'medium': 4, 'low': 1}

    @property
    def GRADE_THRESHOLDS(self) -> tuple[tuple[int, str], ...]:
        """Return the lowest score of each grade, from best to worst."""
        return ((90, 'A'), (75, 'B'), (60, 'C'), (40, 'D'), (0, 'F'))

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    score = fields.Integer(
        string='Score',
        readonly=True,
        aggregator='avg',
    )

    grade = fields.Char(
        compute='_compute_grade',
        string='Grade',
        store=True,
    )

    critical_count = fields.Integer(
        string='Critical',
        readonly=True,
    )

    high_count = fields.Integer(
        string='High',
        readonly=True,
    )

    medium_count = fields.Integer(
        string='Medium',
        readonly=True,
    )

    low_count = fields.Integer(
        string='Low',
        readonly=True,
    )

    accepted_count = fields.Integer(
        string='Accepted',
        readonly=True,
    )

    passed_count = fields.Integer(
        string='Passed',
        readonly=True,
    )

    not_applicable_count = fields.Integer(
        string='Not Applicable',
        readonly=True,
    )

    error_count = fields.Integer(
        string='Errors',
        readonly=True,
    )

    open_finding_ids = fields.Many2many(
        comodel_name='muk_check.finding',
        compute='_compute_open_finding_ids',
        string='Open Findings',
    )

    open_note = fields.Char(
        compute='_compute_open_note',
        string='Open Findings Note',
    )

    next_check = fields.Datetime(
        compute='_compute_open_finding_ids',
        string='Next Check',
    )

    is_latest = fields.Boolean(
        compute='_compute_open_finding_ids',
        string='Latest Check',
    )

    odoo_version = fields.Char(
        compute='_compute_odoo_release',
        string='Odoo Version',
    )

    odoo_build = fields.Date(
        compute='_compute_odoo_release',
        string='Your Build',
    )

    odoo_build_note = fields.Char(
        compute='_compute_odoo_release',
        string='Build Status',
    )

    odoo_build_late = fields.Boolean(
        compute='_compute_odoo_release',
        string='Build Is Late',
    )

    odoo_newest = fields.Char(
        compute='_compute_odoo_release',
        string='Newest Version',
    )

    odoo_image = fields.Date(
        compute='_compute_odoo_release',
        string='Newest Build',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _record_run(self) -> CheckRun:
        """Save the score and the counts of the current findings and rules."""
        finding_counts = dict(
            self.env['muk_check.finding']._read_group(
                [('state', '=', 'open')], ['severity'], ['__count']
            )
        )
        rule_counts = dict(
            self.env['muk_check.rule']._read_group([], ['state'], ['__count'])
        )
        penalty = sum(
            weight * finding_counts.get(severity, 0)
            for severity, weight in self.SEVERITY_WEIGHTS.items()
        )
        return self.create(
            {
                'score': max(0, 100 - penalty),
                'critical_count': finding_counts.get('critical', 0),
                'high_count': finding_counts.get('high', 0),
                'medium_count': finding_counts.get('medium', 0),
                'low_count': finding_counts.get('low', 0),
                'accepted_count': self.env['muk_check.finding'].search_count(
                    [('state', '=', 'accepted')]
                ),
                'passed_count': rule_counts.get('passed', 0),
                'not_applicable_count': rule_counts.get('not_applicable', 0),
                'error_count': rule_counts.get('error', 0),
            }
        )

    @api.model
    def _notify_findings(self) -> None:
        """Post the open findings not reported yet in the administrators channel."""
        findings = self.env['muk_check.finding'].search(
            [('state', '=', 'open'), ('notified', '=', False)]
        )
        channel = self.env.ref('mail.channel_admin', raise_if_not_found=False)
        wanted = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_check.notifications', 'True')
        )
        if findings and channel and wanted == 'True':
            channel.with_user(SUPERUSER_ID).message_post(
                body=self.env['ir.qweb']._render(
                    'muk_check.message_findings', {'findings': findings}
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
        findings.notified = True

    def _action_open(self) -> dict:
        """Open this run as the overview."""
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Overview'),
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'main',
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @assert_log_admin_access
    def action_run(self) -> dict:
        """Refresh the online information, run every rule and report the result."""
        self.env['ir.module.module'].action_check_updates()
        for rule in self.env['muk_check.rule'].sudo().search([]):
            rule._run_rule()
        self.env['muk_check.finding'].search(
            [('state', '!=', 'resolved'), ('rule_id.active', '=', False)]
        ).state = 'resolved'
        run = self._record_run()
        self.sudo()._notify_findings()
        return run._action_open()

    def action_open_overview(self) -> dict:
        """Open the latest run, running the rules when there is none yet."""
        run = self.search([], limit=1)
        return run._action_open() if run else self.action_run()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('score')
    def _compute_grade(self) -> None:
        """Turn the score into a school grade."""
        for run in self:
            run.grade = next(
                grade
                for threshold, grade in self.GRADE_THRESHOLDS
                if run.score >= threshold
            )

    def _compute_display_name(self) -> None:
        """Name a run after its date."""
        for run in self:
            run.display_name = self.env._(
                'Check of %s',
                format_datetime(self.env, run.create_date, dt_format='short'),
            )

    def _compute_open_finding_ids(self) -> None:
        """Show what is open now and the next check on the latest run only."""
        findings = self.env['muk_check.finding'].search([('state', '=', 'open')])
        cron = self.env.ref('muk_check.ir_cron_check', raise_if_not_found=False)
        next_check = cron and cron.sudo().active and cron.sudo().nextcall
        latest = self.search([], limit=1)
        for run in self:
            run.is_latest = run == latest
            run.open_finding_ids = findings if run == latest else False
            run.next_check = next_check if run == latest else False

    @api.depends('critical_count', 'high_count', 'medium_count', 'low_count')
    def _compute_open_note(self) -> None:
        """Say how many findings the run left open."""
        for run in self:
            count = (
                run.critical_count + run.high_count + run.medium_count + run.low_count
            )
            if count == 1:
                run.open_note = self.env._('1 open finding')
            else:
                run.open_note = self.env._('%(count)s open findings', count=count)

    def _compute_odoo_release(self) -> None:
        """Show the running Odoo next to the newest one, which Odoo.sh does not use."""
        build = installed_build()
        builds = {} if is_odoo_sh() else self.env['muk_check.rule']._image_builds()
        image = builds.get(release.serie)
        days = None
        if build and image:
            days = (date.fromisoformat(image) - date.fromisoformat(build)).days
        self.odoo_version = release.version
        self.odoo_build = build and date.fromisoformat(build)
        self.odoo_newest = image and release.serie
        self.odoo_image = image and date.fromisoformat(image)
        self.odoo_build_late = (
            days is not None and days > self.env['muk_check.rule'].BUILD_MAX_DAYS_BEHIND
        )
        if days is None:
            self.odoo_build_note = False
        elif days <= 0:
            self.odoo_build_note = self.env._('Up to date')
        elif days == 1:
            self.odoo_build_note = self.env._('One day behind')
        else:
            self.odoo_build_note = self.env._('%(days)s days behind', days=days)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_history(self) -> None:
        """Delete the runs and resolved findings older than the configured days."""
        days = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_check.history_days', 0)
        )
        if days > 0:
            limit = fields.Datetime.subtract(fields.Datetime.now(), days=days)
            self.search([('create_date', '<', limit)]).unlink()
            self.env['muk_check.finding'].search(
                [('state', '=', 'resolved'), ('last_seen', '<', limit)]
            ).unlink()
