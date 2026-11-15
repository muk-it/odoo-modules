from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from werkzeug.exceptions import Forbidden

from odoo import _, http, models
from odoo.exceptions import UserError
from odoo.http import Response, request


def extension_route(path: str, methods: tuple[str, ...] = ('POST',)) -> Callable:
    """Declare a JSON route the browser extension calls with its device key."""
    return http.route(
        path,
        type='http',
        auth='mcp',
        methods=list(methods),
        cors='*',
        csrf=False,
        save_session=False,
    )


class BrowserController(http.Controller):
    """Endpoints the MuK AI browser extension talks to."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _body(self, **kw: Any) -> dict[str, Any]:
        """Return the JSON body merged with the query arguments."""
        try:
            data = request.get_json_data()
        except ValueError:
            data = None
        return {**kw, **(data if isinstance(data, dict) else {})}

    def _own_chat(self, chat_id: Any, *domain: tuple) -> models.BaseModel:
        """Return the caller's chat ``chat_id`` matching ``domain``, or no chat."""
        if not str(chat_id or '').isdigit():
            return request.env['muk_ai.session']
        return request.env['muk_ai.session'].search(
            [('id', '=', int(chat_id)), ('user_id', '=', request.env.uid), *domain],
            limit=1,
        )

    def _chat(self, body: dict[str, Any]) -> models.BaseModel:
        """Return the caller's chat this device key is attached to, or no chat."""
        return self._own_chat(
            body.get('browser_session_id'),
            ('browser_key_id', '=', request._mcp_key.id),
        )

    def _not_found(self) -> Response:
        """Answer that the request names no chat this browser is attached to."""
        return request.make_json_response(
            {'error': 'browser_session_not_found'}, status=404
        )

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/muk_ai_browser/connect',
        type='http',
        auth='user',
        methods=['GET'],
        website=True,
        multilang=False,
    )
    def connect(self) -> Response:
        """Show an internal user a one-time pairing code for the extension to pick up.

        :raise Forbidden: for portal and public users
        """
        if not request.env.user._is_internal():
            raise Forbidden()
        pairing = request.env['muk_ai_browser.pairing']
        response = request.render(
            'muk_ai_browser.connect_page',
            {'code': pairing._mint(), 'ttl': pairing._pairing_ttl() // 60},
        )
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route(
        ['/ai_browser/chat', '/ai_browser/chat/<int:chat_id>'],
        type='http',
        auth='user',
        methods=['GET'],
    )
    def chat(self, chat_id: int | None = None) -> Response:
        """Open a chat in the extension's side panel.

        Without an id it opens the user's latest chat while it is empty, else a new one.
        """
        if not chat_id:
            latest = request.env['muk_ai.session'].search(
                [('user_id', '=', request.env.uid)],
                order='create_date DESC, id DESC',
                limit=1,
            )
            if not latest or latest.event_ids:
                latest = request.env['muk_ai.session'].create({'name': _('New Chat')})
            chat_id = latest.id
        return request.redirect(f'/web#action=muk_ai.chat&session_id={chat_id}')

    @http.route('/odoo/<string:model>/<int:record_id>', type='http', auth='user')
    def record(self, model: str, record_id: int) -> Response:
        """Open the record form the side panel shows in a tab of the agent's group."""
        return request.redirect(
            '/web#{}'.format(
                urlencode({'model': model, 'id': record_id, 'view_type': 'form'})
            )
        )

    @http.route(
        '/muk_ai_browser/pair',
        type='http',
        auth='none',
        methods=['POST'],
        cors='*',
        csrf=False,
        save_session=False,
    )
    def pair(self, **kw: Any) -> Response:
        """Exchange a pairing code for the device key, shown exactly once."""
        body = self._body(**kw)
        env = request.env(su=True)
        user = env['muk_ai_browser.pairing']._redeem(body.get('pairing_code'))
        if not user:
            return request.make_json_response(
                {'error': 'invalid_or_expired_code'}, status=400
            )
        label = str(body.get('device_label') or 'Browser')[:64]
        key, raw = env['muk_mcp.key']._pair_browser(
            user, label, request.httprequest.headers.get('Origin')
        )
        return request.make_json_response(
            {
                'api_key': raw,
                'scope': key.scope,
                'device_id': key.id,
                'user': {'id': user.id, 'name': user.name},
            }
        )

    @extension_route('/muk_ai_browser/whoami', methods=('GET',))
    def whoami(self) -> Response:
        """Confirm the device key and name its user."""
        user = request.env.user
        return request.make_json_response({'id': user.id, 'name': user.name})

    @extension_route('/muk_ai_browser/unpair')
    def unpair(self) -> Response:
        """Delete the device key of the request."""
        request._mcp_key.unlink()
        return request.make_json_response({'ok': True})

    @extension_route('/muk_ai_browser/session')
    def session(self, **kw: Any) -> Response:
        """Attach the browser to a chat of its user, starting one when none is named."""
        body = self._body(**kw)
        chats = request.env['muk_ai.session']
        if chat_id := body.get('ai_session_id'):
            if not (chat := self._own_chat(chat_id)):
                return request.make_json_response(
                    {'error': 'ai_session_not_found'}, status=404
                )
        else:
            chat = chats.create({'name': _('Browser Chat')})
        chat._browser_attach(request._mcp_key)
        chat._browser_set_origin(body.get('origin'))
        return request.make_json_response(
            {'browser_session_id': str(chat.id), 'ai_session_id': chat.id}
        )

    @extension_route('/muk_ai_browser/events', methods=('GET',))
    def events(self, **kw: Any) -> Response:
        """Record the browser's page and return the actions it has to run."""
        body = self._body(**kw)
        if not (chat := self._chat(body)):
            return self._not_found()
        chat._browser_set_origin(body.get('origin'))
        return request.make_json_response(chat._browser_poll())

    @extension_route('/muk_ai_browser/result')
    def result(self, **kw: Any) -> Response:
        """Hand the result of a browser action back to the agent."""
        body = self._body(**kw)
        if not (chat := self._chat(body)):
            return self._not_found()
        chat._browser_set_origin(body.get('origin'))
        result = body.get('result')
        try:
            snapshot = chat.submit_client_result(
                body.get('call_id'),
                {**result, 'page_content_is_untrusted': True}
                if isinstance(result, dict)
                else result,
            )
        except UserError:
            return request.make_json_response({'error': 'not_pending'}, status=409)
        return request.make_json_response(snapshot)
