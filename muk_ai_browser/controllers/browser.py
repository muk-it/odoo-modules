from __future__ import annotations

import json
from typing import Any

from odoo import _, http, models
from odoo.http import Response, request


class BrowserController(http.Controller):
    """HTTP endpoints bridging the browser extension to the MuK AI agent loop.

    Agent endpoints authenticate with a device API key via the ``mcp`` bearer auth
    method (``cors='*'``, ``csrf=False``). Pairing endpoints use a logged-in user
    session (``connect`` / ``connect/begin``) or the one-time code (``pair``).
    """

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _json_body(self, **kw: Any) -> dict[str, Any]:
        """Return the request body as a dict, merging route keyword arguments."""
        data = {}
        try:
            payload = request.get_json_data()
            if isinstance(payload, dict):
                data = payload
        except Exception:
            data = {}
        return {**data, **kw}

    def _resolve_browser_session(
        self, session_id: str | None
    ) -> models.BaseModel | None:
        """Resolve an active browser session owned by the calling device key."""
        if not session_id:
            return None
        key = getattr(request, '_mcp_key', None)
        session = (
            request.env['muk_ai_browser.session']
            .sudo()
            .search(
                [
                    ('session_id', '=', session_id),
                    ('active', '=', True),
                ],
                limit=1,
            )
        )
        if not session:
            return None
        if key and session.key_id and session.key_id.id != key.id:
            return None
        return session

    # ----------------------------------------------------------
    # Session / Events
    # ----------------------------------------------------------

    @http.route(
        '/muk_ai_browser/session',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def session(self, **kw: Any) -> Response:
        """Create or attach a browser session, creating an AI session when absent.

        :return: JSON ``{browser_session_id, ai_session_id}``
        """
        body = self._json_body(**kw)
        key = getattr(request, '_mcp_key', None)
        ai_session = request.env['muk_ai.session'].sudo()
        if ai_session_id := body.get('ai_session_id'):
            ai_session = ai_session.browse(int(ai_session_id)).exists()
            if not ai_session or ai_session.user_id.id != request.env.uid:
                return request.make_json_response(
                    {'error': 'ai_session_not_found'},
                    status=404,
                )
        else:
            ai_session = request.env['muk_ai.session'].create(
                {'name': body.get('device_label') or _('Browser Session')}
            )
        browser_session = request.env['muk_ai_browser.session']._attach(
            ai_session,
            key,
            device_label=body.get('device_label'),
        )
        return request.make_json_response(
            {
                'browser_session_id': browser_session.session_id,
                'ai_session_id': ai_session.id,
            },
        )

    @http.route(
        '/muk_ai_browser/events',
        type='http',
        auth='mcp',
        methods=['GET'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def events(self, **kw: Any) -> Response:
        """Stream undelivered session events as Server-Sent Events.

        Honours the ``X-Browser-Session`` header and ``Last-Event-ID`` resume,
        claims up to 50 events ordered by ``seq`` and emits a heartbeat comment
        every 20 seconds.

        :return: a ``text/event-stream`` response
        """
        session = self._resolve_browser_session(
            request.httprequest.headers.get('X-Browser-Session'),
        )
        if not session:
            return Response(status=404)
        after_seq = 0
        if last_event_id := request.httprequest.headers.get('Last-Event-ID'):
            try:
                after_seq = int(last_event_id)
            except (TypeError, ValueError):
                after_seq = 0
        rows = request.env['muk_ai_browser.event']._claim(session, after_seq)
        chunks = [b'retry: 10000\n\n']
        for seq, event_type, payload in rows:
            data = json.dumps(
                {'type': event_type, 'payload': payload or {}},
                ensure_ascii=False,
                default=str,
            )
            chunks.append(
                f'id: {seq}\nevent: message\ndata: {data}\n\n'.encode(),
            )
        if len(chunks) == 1:
            chunks.append(b':heartbeat\n\n')
        return Response(
            b''.join(chunks),
            status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )

    @http.route(
        '/muk_ai_browser/result',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def result(self, **kw: Any) -> Response:
        """Submit a client-executed tool result, recording the acting page origin.

        Persisting the origin reported with the result keeps per-site gating
        evaluating against the page actually acted on across in-turn navigations.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        session = self._resolve_browser_session(body.get('browser_session_id'))
        if not session or not session.ai_session_id:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        session._set_origin(body.get('origin'))
        snapshot = session.ai_session_id.submit_client_result(
            body.get('call_id'),
            body.get('result'),
        )
        return request.make_json_response(snapshot)

    @http.route(
        '/muk_ai_browser/reject',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def reject(self, **kw: Any) -> Response:
        """Reject a pending client action and resume the agent loop with an error.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        session = self._resolve_browser_session(body.get('browser_session_id'))
        if not session or not session.ai_session_id:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        snapshot = session.ai_session_id.reject_client_action(
            body.get('call_id'),
            body.get('reason'),
        )
        return request.make_json_response(snapshot)

    # ----------------------------------------------------------
    # Chat / Approval
    # ----------------------------------------------------------

    def _ai_session(self, body: dict[str, Any]) -> models.BaseModel | None:
        """Resolve the AI session behind a browser session for the calling user.

        :return: the AI session in the calling key's user environment, or ``None``
        """
        session = self._resolve_browser_session(body.get('browser_session_id'))
        if not session or not session.ai_session_id:
            return None
        return session.ai_session_id.with_user(request.env.user)

    @http.route(
        '/muk_ai_browser/message',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def message(self, **kw: Any) -> Response:
        """Send a user chat message to the agent loop, recording the page origin.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        session = self._resolve_browser_session(body.get('browser_session_id'))
        if not session or not session.ai_session_id:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        session._set_origin(body.get('origin'))
        snapshot = session.ai_session_id.with_user(request.env.user).send_message(
            body.get('message') or '',
        )
        return request.make_json_response(snapshot)

    @http.route(
        '/muk_ai_browser/answer',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def answer(self, **kw: Any) -> Response:
        """Answer a pending question and resume the agent loop.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        ai_session = self._ai_session(body)
        if not ai_session:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        return request.make_json_response(ai_session.answer(body.get('answer') or ''))

    @http.route(
        '/muk_ai_browser/approve',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def approve(self, **kw: Any) -> Response:
        """Approve the pending tool call once and resume the agent loop.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        ai_session = self._ai_session(body)
        if not ai_session:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        return request.make_json_response(ai_session.approve_tool())

    @http.route(
        '/muk_ai_browser/approve_session',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def approve_session(self, **kw: Any) -> Response:
        """Approve the pending call and whitelist it for the rest of the session.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        ai_session = self._ai_session(body)
        if not ai_session:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        return request.make_json_response(ai_session.approve_for_session())

    @http.route(
        '/muk_ai_browser/reject_approval',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def reject_approval(self, **kw: Any) -> Response:
        """Reject the pending approval and resume the agent loop with the rejection.

        :return: JSON snapshot of the AI session
        """
        body = self._json_body(**kw)
        ai_session = self._ai_session(body)
        if not ai_session:
            return request.make_json_response(
                {'error': 'browser_session_not_found'},
                status=404,
            )
        return request.make_json_response(ai_session.reject_tool(body.get('reason')))

    # ----------------------------------------------------------
    # Pairing
    # ----------------------------------------------------------

    @http.route(
        '/muk_ai_browser/connect',
        type='http',
        auth='user',
        methods=['GET'],
    )
    def connect(self, **kw: Any) -> Response:
        """Render the pairing page injecting the extension id and the base url.

        :return: an HTML QWeb page
        """
        params = request.env['ir.config_parameter'].sudo()
        base_url = params.get_param('web.base.url', '')
        return request.render(
            'muk_ai_browser.connect_page',
            {
                'extension_id': params.get_param('muk_ai_browser.extension_id', ''),
                'base_url': base_url,
                'csrf_token': request.csrf_token(),
            },
        )

    @http.route(
        '/muk_ai_browser/connect/begin',
        type='jsonrpc',
        auth='user',
        methods=['POST'],
    )
    def connect_begin(self, **kw: Any) -> dict[str, Any]:
        """Mint a one-time pairing code bound to the current user.

        :return: JSON ``{pairing_code, expires_in}``
        """
        scope = kw.get('scope') if kw.get('scope') in ('read', 'write') else 'write'
        pairing = request.env['muk_mcp.pairing'].sudo()
        code = pairing._mint_code(
            request.env.uid,
            device_label=kw.get('device_label'),
            scope=scope,
        )
        return {
            'pairing_code': code,
            'expires_in': pairing._pairing_ttl(),
        }

    @http.route(
        '/muk_ai_browser/pair',
        type='http',
        auth='none',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
        readonly=False,
    )
    def pair(self, **kw: Any) -> Response:
        """Consume a single-use pairing code and mint a device key.

        :return: JSON ``{api_key, key_prefix, device_id, scope}`` returned exactly once
        """
        body = self._json_body(**kw)
        consumed = (
            request.env['muk_mcp.pairing'].sudo()._consume(body.get('pairing_code'))
        )
        if not consumed:
            return request.make_json_response(
                {'error': 'invalid_or_expired_code'},
                status=400,
            )
        key, raw_key = (
            request.env['muk_ai_browser.device']
            .sudo()
            ._mint(
                consumed['user_id'],
                consumed['device_label'] or 'Browser',
                scope=consumed['scope'],
                user_agent=request.httprequest.headers.get('User-Agent'),
                ip_address=request.httprequest.remote_addr,
            )
        )
        return request.make_json_response(
            {
                'api_key': raw_key,
                'key_prefix': key.key_prefix,
                'device_id': key.id,
                'scope': key.scope,
            },
        )

    @http.route(
        '/muk_ai_browser/whoami',
        type='http',
        auth='mcp',
        methods=['GET'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def whoami(self, **kw: Any) -> Response:
        """Confirm the device key resolves to a user.

        :return: JSON ``{user, login}`` with status 200, or 401 when unauthorised
        """
        return request.make_json_response(
            {
                'user': request.env.uid,
                'login': request.env.user.login,
            },
        )

    @http.route(
        '/muk_ai_browser/unpair',
        type='http',
        auth='mcp',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def unpair(self, **kw: Any) -> Response:
        """Revoke the device key used by the current request.

        :return: JSON ``{ok}``
        """
        if key := getattr(request, '_mcp_key', None):
            key.sudo().write({'active': False})
        return request.make_json_response({'ok': True})
