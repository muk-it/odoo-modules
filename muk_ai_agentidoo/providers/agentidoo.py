import json
import logging
import threading
import time

import requests

from odoo import _

from odoo.addons.muk_ai.providers.base import ProviderBase

_logger = logging.getLogger(__name__)

CAPABILITIES_TTL = 3600

_capabilities_cache = {}
_capabilities_lock = threading.Lock()


class AgentidooProvider(ProviderBase):

    name = 'agentidoo'
    label = "Agentidoo"
    default_model = ''
    default_url = 'https://api.agentidoo.com'

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def request(
        self,
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_image_generation=False,
        enable_code_interpreter=False,
        extra=None,
    ):
        extra = extra or {}
        user_text = self._extract_last_user_message(inputs)
        bag = extra.get('bag')
        session_id = bag.get('session_id') if isinstance(bag, dict) else ''
        if not session_id:
            session_id = self._create_session(metadata=extra.get('metadata'))
            if isinstance(bag, dict):
                bag['session_id'] = session_id
        send_resp = self._send_message(session_id, user_text)
        if send_resp.get('status') not in ('running', 'queued', 'accepted'):
            _logger.warning(
                "Agentidoo /messages returned unexpected status: %s", send_resp,
            )
        text, frontend_actions, owlets, action_buttons = self._read_sse_stream(
            session_id, on_delta,
        )
        carry_inputs = []
        if text:
            carry_inputs.append({
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': text}],
            })
        result = {
            'text': text,
            'tool_calls': [],
            'carry_inputs': carry_inputs,
            'usage': self._usage(),
        }
        if action_buttons:
            result['agentidoo_action_buttons'] = action_buttons
        if frontend_actions:
            result['agentidoo_frontend_actions'] = frontend_actions
        if owlets:
            result['agentidoo_owlets'] = owlets
        return result

    def test_connection(self):
        try:
            response = requests.get(
                f'{self.api_url.rstrip("/")}/api/v1/me',
                headers=self.headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        return True

    # ----------------------------------------------------------
    # API
    # ----------------------------------------------------------

    def _create_session(self, metadata=None):
        payload = {
            'metadata': {
                'source': 'muk_ai_agentidoo',
                **(metadata or {}),
            },
        }
        try:
            response = requests.post(
                f'{self.api_url.rstrip("/")}/api/v1/chat/sessions',
                json=payload,
                headers=self.headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)
        session_id = data.get('id') or ''
        if not session_id:
            self._raise(_("Agentidoo returned an empty session id"))
        return session_id

    def _send_message(self, session_id, content):
        try:
            response = requests.post(
                f'{self.api_url.rstrip("/")}/api/v1/chat/sessions/{session_id}/messages',
                json={'content': content},
                headers=self.headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as error:
            self._raise(getattr(error.response, 'text', '') or str(error))
        except requests.RequestException as error:
            self._raise(error)

    def _read_sse_stream(self, session_id, on_delta=None):
        url = f'{self.api_url.rstrip("/")}/api/v1/chat/sessions/{session_id}/stream'
        text_parts = []
        frontend_actions = []
        owlets = []
        action_buttons = []
        active_tools = {}
        connect_timeout = min(self.request_timeout or 30, 30)
        read_timeout = self.idle_timeout or 300
        try:
            with requests.get(
                url,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Accept': 'text/event-stream',
                },
                stream=True,
                timeout=(connect_timeout, read_timeout),
            ) as response:
                if response.status_code != 200:
                    _logger.warning(
                        "Agentidoo SSE stream returned %d: %s",
                        response.status_code, response.text[:200],
                    )
                    return ('', [], [], [])
                event_type = None
                for line in response.iter_lines(decode_unicode=True):
                    if line is None:
                        continue
                    if line.startswith(':'):
                        continue
                    if line.startswith('event: '):
                        event_type = line[7:].strip()
                        continue
                    if not line.startswith('data: '):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except (ValueError, TypeError):
                        continue
                    if event_type == 'text_delta':
                        delta = data.get('delta') or data.get('text') or ''
                        if not delta:
                            continue
                        text_parts.append(delta)
                        self._call_on_delta(on_delta, 'text', {'delta': delta})
                    elif event_type == 'tool_start':
                        tool_call_id = data.get('tool_call_id') or data.get('id') or ''
                        tool_name = data.get('tool_name') or data.get('name') or ''
                        active_tools[tool_call_id] = {
                            'id': tool_call_id,
                            'name': tool_name,
                            'arguments': {},
                        }
                        self._call_on_delta(on_delta, 'tool_start', {
                            'call_id': tool_call_id,
                            'name': tool_name,
                        })
                    elif event_type == 'tool_args_delta':
                        tool_call_id = data.get('tool_call_id') or ''
                        delta = data.get('delta') or ''
                        if delta:
                            self._call_on_delta(on_delta, 'tool_args', {
                                'call_id': tool_call_id,
                                'delta': delta,
                            })
                    elif event_type == 'tool_end':
                        tool_call_id = data.get('tool_call_id') or data.get('id') or ''
                        args = data.get('arguments') or {}
                        if tool_call_id in active_tools:
                            active_tools[tool_call_id]['arguments'] = args
                    elif event_type == 'tool_result':
                        tool_call_id = data.get('tool_call_id') or ''
                        tool_name = (
                            data.get('tool_name')
                            or (active_tools.get(tool_call_id) or {}).get('name')
                            or ''
                        )
                        output = self._extract_tool_output(data.get('result') or {})
                        if tool_name == 'odoo_frontend_action':
                            self._collect_frontend_actions(output, frontend_actions)
                        elif tool_name == 'owlet':
                            self._collect_owlets(output, owlets)
                        elif tool_name == 'odoo_action_buttons':
                            self._collect_action_buttons(output, action_buttons)
                        active_tools.pop(tool_call_id, None)
                    elif event_type in ('agent_end', 'done'):
                        break
                    elif event_type == 'error':
                        _logger.warning("Agentidoo agent error: %s", data)
                        break
        except requests.RequestException as error:
            _logger.warning("Agentidoo SSE stream failed: %s", error)
        return (''.join(text_parts), frontend_actions, owlets, action_buttons)

    def capabilities(self):
        api_url = self.api_url.rstrip('/')
        now = time.time()
        with _capabilities_lock:
            entry = _capabilities_cache.get(api_url)
            if entry and (now - entry['fetched_at']) < CAPABILITIES_TTL:
                return entry['manifest']
        try:
            response = requests.get(
                f'{api_url}/api/v1/capabilities',
                headers=self.headers(),
                timeout=10,
            )
            response.raise_for_status()
            manifest = response.json()
        except requests.RequestException as error:
            _logger.debug("Agentidoo /capabilities failed: %s", error)
            return {}
        with _capabilities_lock:
            _capabilities_cache[api_url] = {
                'manifest': manifest,
                'fetched_at': now,
            }
        return manifest

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _extract_last_user_message(inputs):
        for item in reversed(inputs or []):
            if item.get('role') != 'user':
                continue
            content = item.get('content')
            if isinstance(content, str):
                return content
            for chunk in content or []:
                if text := chunk.get('text'):
                    return text
        return ''

    @staticmethod
    def _extract_tool_output(result):
        if not isinstance(result, dict):
            return ''
        parts = [
            chunk.get('text', '')
            for chunk in result.get('content') or []
            if isinstance(chunk, dict) and chunk.get('type') == 'text'
        ]
        if parts:
            return ''.join(parts)
        try:
            return json.dumps(result)
        except (TypeError, ValueError):
            return ''

    @staticmethod
    def _collect_frontend_actions(output, sink):
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except (json.JSONDecodeError, ValueError):
            return
        if isinstance(parsed, dict) and parsed.get('status') == 'validated':
            sink.extend(parsed.get('actions') or [])

    @staticmethod
    def _collect_owlets(output, sink):
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except (json.JSONDecodeError, ValueError):
            return
        if isinstance(parsed, dict) and parsed.get('status') == 'validated':
            sink.append({
                'type': parsed.get('type'),
                'props': parsed.get('props'),
            })

    @staticmethod
    def _collect_action_buttons(output, sink):
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except (json.JSONDecodeError, ValueError):
            return
        if isinstance(parsed, dict):
            sink.extend(parsed.get('action_buttons') or [])
        elif isinstance(parsed, list):
            sink.extend(parsed)
