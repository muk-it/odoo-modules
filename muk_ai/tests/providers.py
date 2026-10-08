from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial

import requests

from odoo.addons.muk_ai.tests.common import AITestCommon, sse_response

SYSTEM = {'role': 'system', 'content': [{'type': 'input_text', 'text': 'be brief'}]}

USER = {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}

TOOLS = [
    {
        'type': 'function',
        'name': 'x',
        'description': 'd',
        'parameters': {'type': 'object', 'properties': {}},
    }
]


def openai_event(kind: str, **fields) -> dict:
    """Build an OpenAI Responses stream event of ``response.<kind>``."""
    return {'type': f'response.{kind}', **fields}


def openai_end(*output: dict, kind: str = 'completed', **response) -> dict:
    """Build the OpenAI event closing a response with its output items."""
    return openai_event(
        kind, response={'output': list(output), 'usage': {}, **response}
    )


def openai_message(text: str) -> dict:
    """Build an assistant message item of the OpenAI Responses wire."""
    return {
        'type': 'message',
        'role': 'assistant',
        'content': [{'type': 'output_text', 'text': text}],
    }


def anthropic_block(index: int, block: dict, *deltas: dict) -> list[dict]:
    """Build the Anthropic events of one content block and its deltas."""
    return [
        {'type': 'content_block_start', 'index': index, 'content_block': block},
        *({'type': 'content_block_delta', 'index': index, 'delta': d} for d in deltas),
        {'type': 'content_block_stop', 'index': index},
    ]


def anthropic_text(index: int, *chunks: str) -> list[dict]:
    """Build the Anthropic events of one text block streamed in chunks."""
    deltas = ({'type': 'text_delta', 'text': chunk} for chunk in chunks)
    return anthropic_block(index, {'type': 'text', 'text': ''}, *deltas)


def anthropic_stop(reason: str, output_tokens: int = 1) -> dict:
    """Build the Anthropic ``message_delta`` closing a message."""
    return {
        'type': 'message_delta',
        'delta': {'stop_reason': reason},
        'usage': {'output_tokens': output_tokens},
    }


def gemini(*parts: dict, finish: str | None = None, usage: dict | None = None) -> dict:
    """Build a Gemini stream chunk carrying the given model parts."""
    candidate = {'content': {'role': 'model', 'parts': list(parts)}}
    if finish:
        candidate['finishReason'] = finish
    return {'candidates': [candidate], **({'usageMetadata': usage} if usage else {})}


def _gemini_usage(
    prompt: int, candidates: int, thoughts: int = 0, cached: int = 0
) -> dict:
    """Build the ``usageMetadata`` of a Gemini chunk."""
    return {
        'promptTokenCount': prompt,
        'candidatesTokenCount': candidates,
        'thoughtsTokenCount': thoughts,
        'cachedContentTokenCount': cached,
    }


def _usage(read: int, written: int, cache_read: int = 0, cache_write: int = 0) -> dict:
    """Build the normalised usage an adapter returns."""
    return {
        'input_tokens': read,
        'output_tokens': written,
        'cache_read_tokens': cache_read,
        'cache_write_tokens': cache_write,
    }


def _openai_wire(url: str, body: dict) -> dict:
    """Normalise an OpenAI Responses request body."""
    tools = body.get('tools') or []
    system = [item for item in body['input'] if item.get('role') == 'system']
    return {
        'model': body['model'],
        'system': ''.join(b['text'] for item in system for b in item['content']),
        'tools': [tool['name'] for tool in tools if tool.get('type') == 'function'],
        'builtin': [tool['type'] for tool in tools if tool.get('type') != 'function'],
        'max_tokens': body.get('max_output_tokens'),
        'effort': (body.get('reasoning') or {}).get('effort'),
        'schema': ((body.get('text') or {}).get('format') or {}).get('schema'),
        'content': body['input'][-1]['content'],
    }


def _anthropic_wire(url: str, body: dict) -> dict:
    """Normalise an Anthropic Messages request body, cache breakpoints left out."""
    tools = body.get('tools') or []
    system = body.get('system') or ''
    thinking = body.get('thinking') or {}
    effort = (body.get('output_config') or {}).get('effort')
    if thinking.get('type') == 'enabled':
        effort = f'budget:{thinking["budget_tokens"]}'
    return {
        'model': body['model'],
        'system': system if isinstance(system, str) else system[0]['text'],
        'tools': [tool['name'] for tool in tools if 'type' not in tool],
        'builtin': [tool['type'] for tool in tools if 'type' in tool],
        'max_tokens': body['max_tokens'],
        'effort': effort,
        'schema': ((body.get('output_config') or {}).get('format') or {}).get('schema'),
        'content': [
            {key: value for key, value in block.items() if key != 'cache_control'}
            for block in body['messages'][-1]['content']
        ],
    }


def _google_wire(url: str, body: dict) -> dict:
    """Normalise a Gemini generateContent request body and its URL."""
    tools = body.get('tools') or []
    config = body.get('generationConfig') or {}
    system = (body.get('systemInstruction') or {}).get('parts') or []
    return {
        'model': url.split('/models/')[1].partition(':')[0],
        'system': ''.join(part['text'] for part in system),
        'tools': [
            declaration['name']
            for tool in tools
            for declaration in tool.get('functionDeclarations') or []
        ],
        'builtin': [
            key for tool in tools for key in tool if key != 'functionDeclarations'
        ],
        'max_tokens': config.get('maxOutputTokens'),
        'effort': (config.get('thinkingConfig') or {}).get('thinkingLevel'),
        'schema': config.get('responseSchema'),
        'content': body['contents'][-1]['parts'],
    }


def deltas_of(deltas: list[tuple[str, dict]], kind: str) -> list[str]:
    """Return the ``delta`` text of every streamed delta of ``kind``."""
    return [data.get('delta') for got, data in deltas if got == kind]


@dataclass(frozen=True)
class ProviderCase:
    """Hold the recorded wire of one vendor and how to read what it is sent.

    Streams: ``text`` says "Hello" with cache usage, ``tool_call`` calls
    ``do_x({"a": 1})``, ``reasoning`` thinks before it answers, ``truncated``
    stops at 4096 tokens; ``reply`` is a plain "ok" answer.
    """

    xmlid: str
    model: str
    endpoint: str
    auth: tuple[str, str]
    builtin: tuple[str, str]
    unlimited: int | None
    text: list
    usage: dict
    tool_call: list
    reasoning: list
    truncated: list
    reply: dict
    error: Callable[[str], dict]
    wire: Callable[[str, dict], dict]


CASES = {
    'openai': ProviderCase(
        xmlid='muk_ai.provider_openai',
        model='gpt-5.4-mini',
        endpoint='/responses',
        auth=('Authorization', 'Bearer test-key'),
        builtin=('web_search', 'code_interpreter'),
        unlimited=None,
        text=[
            openai_event('output_text.delta', delta='Hel'),
            openai_event('output_text.delta', delta='lo'),
            openai_end(
                openai_message('Hello'),
                usage={
                    'input_tokens': 11,
                    'output_tokens': 4,
                    'input_tokens_details': {'cached_tokens': 3},
                },
            ),
        ],
        usage=_usage(11, 4, 3),
        tool_call=[
            openai_event(
                'output_item.added',
                output_index=0,
                item={'type': 'function_call', 'call_id': 'c1', 'name': 'do_x'},
            ),
            openai_event(
                'function_call_arguments.delta', output_index=0, delta='{"a":'
            ),
            openai_event('function_call_arguments.delta', output_index=0, delta='1}'),
            openai_event(
                'output_item.done',
                output_index=0,
                item={
                    'type': 'function_call',
                    'call_id': 'c1',
                    'name': 'do_x',
                    'arguments': '{"a":1}',
                },
            ),
            openai_end(),
        ],
        reasoning=[
            openai_event('reasoning_summary_text.delta', delta='weighing it'),
            openai_event('output_text.delta', delta='answer'),
            openai_end(openai_message('answer')),
        ],
        truncated=[
            openai_event('output_text.delta', delta='partial'),
            openai_end(
                kind='incomplete',
                incomplete_details={'reason': 'max_output_tokens'},
                usage={'input_tokens': 20, 'output_tokens': 4096},
            ),
        ],
        reply={'output': [openai_message('ok')]},
        error=lambda message: openai_event('error', error={'message': message}),
        wire=_openai_wire,
    ),
    'anthropic': ProviderCase(
        xmlid='muk_ai.provider_anthropic',
        model='claude-opus-4-8',
        endpoint='/messages',
        auth=('x-api-key', 'test-key'),
        builtin=('web_search_20250305', 'code_execution_20250825'),
        unlimited=4096,
        text=[
            {
                'type': 'message_start',
                'message': {
                    'usage': {
                        'input_tokens': 100,
                        'cache_read_input_tokens': 300,
                        'cache_creation_input_tokens': 50,
                    }
                },
            },
            *anthropic_text(0, 'Hel', 'lo'),
            anthropic_stop('end_turn', 20),
        ],
        usage=_usage(450, 20, 300, 50),
        tool_call=[
            *anthropic_block(
                0,
                {'type': 'tool_use', 'id': 'c1', 'name': 'do_x', 'input': {}},
                {'type': 'input_json_delta', 'partial_json': '{"a":'},
                {'type': 'input_json_delta', 'partial_json': '1}'},
            ),
            anthropic_stop('tool_use'),
        ],
        reasoning=[
            *anthropic_block(
                0,
                {'type': 'thinking', 'thinking': ''},
                {'type': 'thinking_delta', 'thinking': 'weighing it'},
                {'type': 'signature_delta', 'signature': 'sig-1'},
            ),
            *anthropic_text(1, 'answer'),
            anthropic_stop('end_turn'),
        ],
        truncated=[
            {'type': 'message_start', 'message': {'usage': {'input_tokens': 7}}},
            *anthropic_text(0, 'partial'),
            anthropic_stop('max_tokens', 4096),
        ],
        reply={'content': [{'type': 'text', 'text': 'ok'}], 'stop_reason': 'end_turn'},
        error=lambda message: {'type': 'error', 'error': {'message': message}},
        wire=_anthropic_wire,
    ),
    'google': ProviderCase(
        xmlid='muk_ai.provider_google',
        model='gemini-3.8-flash',
        endpoint='/models/{model}:streamGenerateContent?alt=sse',
        auth=('x-goog-api-key', 'test-key'),
        builtin=('googleSearch', 'codeExecution'),
        unlimited=None,
        text=[
            gemini({'text': 'Hel'}, usage=_gemini_usage(44, 100, 553)),
            gemini(
                {'text': 'lo'}, finish='STOP', usage=_gemini_usage(44, 194, 553, 12)
            ),
        ],
        usage=_usage(44, 747, 12),
        tool_call=[gemini({'functionCall': {'name': 'do_x', 'args': {'a': 1}}})],
        reasoning=[
            gemini({'thought': True, 'text': 'weighing it'}),
            gemini({'text': 'answer'}, finish='STOP'),
        ],
        truncated=[
            gemini({'text': 'partial'}),
            gemini(finish='MAX_TOKENS', usage=_gemini_usage(7, 4096)),
        ],
        reply={'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]},
        error=lambda message: {'error': {'message': message, 'status': 'INTERNAL'}},
        wire=_google_wire,
    ),
}

EFFORT = [
    ('openai', 'gpt-5.4-mini', None, 'medium'),
    ('openai', 'gpt-5.4-mini', 'low', 'low'),
    ('openai', 'gpt-5.4', 'max', 'xhigh'),
    ('openai', 'gpt-5.4', 'minimal', 'low'),
    ('openai', 'gpt-5.6-sol', 'max', 'max'),
    ('openai', 'gpt-4o', 'high', None),
    ('openai', 'o3-uncatalogued', 'minimal', 'minimal'),
    ('anthropic', 'claude-opus-4-8', None, 'medium'),
    ('anthropic', 'claude-opus-4-8', 'xhigh', 'xhigh'),
    ('anthropic', 'claude-opus-4-8', 'minimal', 'low'),
    ('anthropic', 'claude-sonnet-4-6', 'xhigh', 'high'),
    ('anthropic', 'claude-sonnet-5', 'low', 'low'),
    ('anthropic', 'claude-fable-5', 'max', 'max'),
    ('anthropic', 'claude-opus-5-uncatalogued', 'minimal', 'low'),
    ('anthropic', 'claude-opus-4-5', None, 'budget:1024'),
    ('anthropic', 'claude-opus-4-5', 'high', 'budget:4096'),
    ('anthropic', 'claude-opus-4-5', 'max', 'budget:4096'),
    ('anthropic', 'claude-opus-4-5', 'low', None),
    ('anthropic', 'claude-haiku-4-5', 'high', None),
    ('google', 'gemini-3.8-flash', None, None),
    ('google', 'gemini-3.8-flash', 'low', 'low'),
    ('google', 'gemini-3.8-flash', 'max', 'high'),
    ('google', 'gemini-3.8-flash', 'minimal', 'low'),
    ('google', 'gemini-2.5-flash', 'low', None),
    ('google', 'gemini-9-uncatalogued', 'xhigh', 'high'),
]

FILE_TEXT = '--- File: note.txt (text/plain) ---\nhello body'


def _attached(**block) -> list[dict]:
    """Return user content holding one materialised attachment block."""
    return [{'type': 'muk_ai_attachment', **block}]


def _texts(text: str) -> dict:
    """Return the content each vendor is sent for one text part."""
    return {
        'openai': [{'type': 'input_text', 'text': text}],
        'anthropic': [{'type': 'text', 'text': text}],
        'google': [{'text': text}],
    }


def _encoded(kind: str, mimetype: str, data: str) -> dict:
    """Return the content Anthropic and Google are sent for one binary file."""
    source = {'type': 'base64', 'media_type': mimetype, 'data': data}
    return {
        'anthropic': [{'type': kind, 'source': source}],
        'google': [{'inlineData': {'mimeType': mimetype, 'data': data}}],
    }


TEXT_FILE = {
    'strategy': 'inline_text',
    'mimetype': 'text/plain',
    'inline_text': 'hello body',
    'filename': 'note.txt',
}

ATTACHMENTS = [
    (
        'image',
        _attached(strategy='image', mimetype='image/png', data_b64='AAA='),
        {
            'openai': [
                {'type': 'input_image', 'image_url': 'data:image/png;base64,AAA='}
            ],
            **_encoded('image', 'image/png', 'AAA='),
        },
    ),
    (
        'pdf',
        _attached(
            strategy='file',
            mimetype='application/pdf',
            data_b64='PDF=',
            filename='doc.pdf',
        ),
        {
            'openai': [
                {
                    'type': 'input_file',
                    'filename': 'doc.pdf',
                    'file_data': 'data:application/pdf;base64,PDF=',
                }
            ],
            **_encoded('document', 'application/pdf', 'PDF='),
        },
    ),
    ('text', _attached(**TEXT_FILE), _texts(FILE_TEXT)),
    (
        'truncated',
        _attached(**TEXT_FILE, truncated=True),
        _texts(f'{FILE_TEXT}\n[truncated]'),
    ),
    ('plain string', 'hi', {**_texts('hi'), 'openai': 'hi'}),
]


class ProviderTestCase(AITestCommon):
    """Shared setup of the provider adapter tests: the record of every vendor."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Bind the provider record of every recorded vendor."""
        super().setUpClass()
        cls.providers = {name: cls.env.ref(case.xmlid) for name, case in CASES.items()}

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _record(
        self, sent: list, answer, kwargs: dict
    ) -> requests.Response | Exception:
        """Record one POST with a copy of its body, then give its answer.

        :param answer: a list of SSE events, or what ``_capture_post`` takes
        """
        sent.append({**kwargs, 'json': copy.deepcopy(kwargs.get('json'))})
        if isinstance(answer, list):
            return sse_response(answer)
        return answer(kwargs) if callable(answer) else answer

    @contextmanager
    def _wire(self, *answers) -> Iterator[list[dict]]:
        """Answer each POST with the next answer and record every request sent.

        A record holds the POST keyword arguments, its ``url`` and a copy of
        the ``json`` body taken before a retry can change it.
        """
        sent = []
        replies = [partial(self._record, sent, answer) for answer in answers]
        with self._capture_post(*replies) as captured:
            try:
                yield sent
            finally:
                for record, (url, _kwargs) in zip(sent, captured, strict=False):
                    record['url'] = url

    def _stream(
        self, name: str, *answers, **kwargs
    ) -> tuple[dict, list[tuple[str, dict]], list[dict]]:
        """Stream one request of the vendor and return result, deltas and sends.

        :param kwargs: request arguments, ``inputs`` defaulting to one user turn
        """
        deltas = []
        with self._wire(*answers) as sent:
            result = self.providers[name]._request_responses(
                **{'inputs': [USER], **kwargs},
                on_delta=lambda kind, data: deltas.append((kind, data)),
            )
        return result, deltas, sent
