from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import MissingError
from odoo.tools import OrderedSet
from odoo.tools.query import Query

from odoo.addons.muk_ai.tools import with_record_ctx
from odoo.addons.muk_ai_automation.tools.dispatch import (
    PreviousProxy,
    _resolve_records,
)


class AISession(models.Model):
    """Link AI sessions to business records, server actions, and chains."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    action_server_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Server Action',
        help='Server action that spawned this session.',
        index=True,
        copy=False,
        ondelete='set null',
    )

    base_automation_id = fields.Many2one(
        comodel_name='base.automation',
        related='action_server_id.base_automation_id',
        string='Automation Rule',
        readonly=True,
        store=False,
    )

    previous_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Previous Session',
        help='Prior session in the per-record chain.',
        copy=False,
        ondelete='set null',
    )

    res_model = fields.Char(
        string='Linked Model',
        help='Model of the business record this session is linked to.',
        index=True,
        copy=False,
    )

    res_id = fields.Many2oneReference(
        model_field='res_model',
        string='Linked Record',
        help='Identifier of the linked business record.',
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _linked_record(self) -> models.BaseModel | None:
        """Return the linked business record, or ``None`` when unresolved."""
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        record = self.env[self.res_model].sudo().browse(self.res_id)
        return record if record.exists() else None

    def _owner_can_read(self, record: models.BaseModel) -> bool:
        """Return whether the session owner may read the linked record."""
        owner = self.user_id or self.env.user
        return record.with_user(owner).has_access('read')

    @api.model
    def _non_owner_sensitive_fields(self) -> tuple[str, ...]:
        """Return transcript fields hidden from non-owner, non-admin readers.

        These carry tool and RAG output produced under the owner's (or
        ``sudo``) privileges, so they must be blanked for a reader who only
        gained record-level access through the linked business record.
        """
        return ('conversation',)

    def _hides_transcript_from_current_user(self) -> bool:
        """Return whether the caller must be denied this session's transcript."""
        if self.env.su or self.env.is_admin():
            return False
        return self.user_id.id != self.env.uid

    def _build_request_inputs(self) -> list[dict]:
        """Extend request inputs with the linked record context when present."""
        inputs = super()._build_request_inputs()
        record = self._linked_record()
        if record is not None and self._owner_can_read(record):
            inputs = with_record_ctx(
                inputs,
                {
                    'kind': 'record',
                    'model': record._name,
                    'id': record.id,
                    'display_name': record.display_name,
                },
            )
        return inputs

    def _session_prompt_extras(self) -> dict:
        """Add record, records, previous-session, and now to the prompt scope."""
        extras = super()._session_prompt_extras()
        empty = self.env['base'].browse([])
        record, records, previous = empty, empty, PreviousProxy(None)
        if self and self.id:
            linked = self._linked_record()
            if linked is not None and self._owner_can_read(linked):
                record = linked.with_user(self.user_id or self.env.user)
            previous = PreviousProxy(self.previous_session_id or None)
            action = self.action_server_id
            if action and action.agent_dispatch_mode == 'single':
                records = _resolve_records(action, {})
        extras.update(
            {
                'now': fields.Datetime.now(),
                'record': record,
                'records': records,
                'previous_session': previous,
            }
        )
        return extras

    def _post_chatter_mirror(self) -> None:
        """Post a chatter note on the linked record pointing at this session."""
        record = self._linked_record()
        if record is None or not hasattr(record, 'message_post'):
            return
        if not self._owner_can_read(record):
            return
        link = Markup(
            '<a href="/odoo/action-muk_ai.action_ai_session/{sid}">{label}</a>'
        ).format(sid=self.id, label=self.display_name or _('AI Session'))
        body = Markup('<p>%s</p>') % _(
            'AI session %(link)s started for this record.',
            link=link,
        )
        with suppress(Exception):
            record.message_post(body=body, subtype_xmlid='mail.mt_note')

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    @api.model
    def _search(
        self,
        domain: list,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        *,
        active_test: bool = True,
        bypass_access: bool = False,
    ) -> Query:
        """Filter sessions by per-linked-record access for non-admin users."""
        if self.env.su or self.env.is_admin() or bypass_access:
            return super()._search(
                domain,
                offset=offset,
                limit=limit,
                order=order,
                active_test=active_test,
                bypass_access=bypass_access,
            )
        candidate_query = super()._search(
            domain,
            order=order,
            active_test=active_test,
            bypass_access=True,
        )
        candidate_ids = list(candidate_query)
        if not candidate_ids:
            return candidate_query
        accessible = self.browse(candidate_ids)._filtered_access('read')
        return super()._search(
            [('id', 'in', list(accessible._ids))],
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=True,
        )

    def _check_access(self, operation: str) -> tuple[AISession, Callable] | None:
        """Grant read access to sessions linked to records the user may read."""
        res = super()._check_access(operation)
        if operation != 'read' or self.env.su or self.env.is_admin() or not self:
            return res
        if not res:
            return res
        forbidden, error_func = res
        forbidden_ids = OrderedSet(forbidden._ids)
        sudo_self = self.sudo().browse(forbidden_ids)
        sudo_self.fetch(['user_id', 'res_model', 'res_id'])
        uid = self.env.uid
        by_model = defaultdict(set)
        session_links = {}
        for session in sudo_self:
            if session.user_id.id == uid:
                forbidden_ids.discard(session.id)
                continue
            if session.res_model and session.res_id and session.res_model in self.env:
                by_model[session.res_model].add(session.res_id)
                session_links[session.id] = (session.res_model, session.res_id)
        granted_pairs = set()
        for res_model, res_ids in by_model.items():
            records = self.env[res_model].browse(list(res_ids))
            try:
                allowed = records._filtered_access('read')
            except MissingError:
                allowed = records.exists()._filtered_access('read')
            for rec_id in allowed._ids:
                granted_pairs.add((res_model, rec_id))
        for sid, key in session_links.items():
            if key in granted_pairs:
                forbidden_ids.discard(sid)
        if forbidden_ids:
            return self.browse(forbidden_ids), error_func
        return None

    def read(
        self, fields: list[str] | None = None, load: str = '_classic_read'
    ) -> list[dict]:
        """Blank transcript fields when a non-owner reads a granted session.

        The record-level grant added by :meth:`_check_access` lets a non-owner
        see a session and its metadata, but the transcript fields hold data
        gathered under the owner's privileges. Empty them for non-owner,
        non-admin readers while preserving owner and admin behavior.
        """
        result = super().read(fields, load)
        if not result or self.env.su or self.env.is_admin():
            return result
        sensitive = self._non_owner_sensitive_fields()
        if fields is not None and not any(name in fields for name in sensitive):
            return result
        uid = self.env.uid
        owner_by_id = {
            session.id: session.user_id.id
            for session in self.sudo().browse([row['id'] for row in result])
        }
        for row in result:
            if owner_by_id.get(row['id']) == uid:
                continue
            for name in sensitive:
                if name in row:
                    row[name] = []
        return result

    def get_snapshot(self, include_conversation: bool = False) -> dict:
        """Drop the transcript from snapshots taken by non-owner readers."""
        if include_conversation and self._hides_transcript_from_current_user():
            snapshot = super().get_snapshot(include_conversation=False)
            snapshot['conversation'] = []
            return snapshot
        return super().get_snapshot(include_conversation=include_conversation)

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Create sessions, mirroring a note onto linked business records."""
        records = super().create(vals_list)
        for record in records:
            if record.res_model and record.res_id:
                record._post_chatter_mirror()
        return records
