from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from unittest.mock import MagicMock, patch

import requests

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai.tools.url_fetch import FetchResult

HTML_PAGE = (
    b'<!doctype html><html><head><title>  Hello   World </title>'
    b'<style>.x{color:red}</style></head>'
    b'<body><nav>Home About</nav>'
    b'<main><h1>Heading</h1><p>First <a href="/docs">paragraph</a>.</p>'
    b'<script>var x = 1;</script>'
    b'<ul><li>one</li><li>two</li></ul>'
    b'<pre><code>code line</code></pre></main>'
    b'<footer>copyright</footer></body></html>'
)

PNG_1x1 = base64.b64encode(
    bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
        '890000000d49444154789c63f8cf00000003000100184b96c10000000049454e'
        '44ae426082'
    )
).decode()


def html_result(url: str = 'https://example.com/page') -> FetchResult:
    """Build a fetch result serving the shared HTML fixture page."""
    return FetchResult(url=url, body=HTML_PAGE, content_type='text/html', charset=None)


class FakeRequest:
    """Stand-in for the werkzeug request proxy used by the dispatch hook."""

    def __init__(self, dbname: str = 'testdb', bound: bool = True) -> None:
        self.db = dbname
        self.bound = bound

    def __bool__(self) -> bool:
        """Report whether a request is bound, as the werkzeug proxy does."""
        return self.bound


@tagged('post_install', '-at_install')
class AITestCommon(TransactionCase):
    """Shared setup and mocking helpers for the AI provider/session tests."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().write({'api_key': 'test-key', 'active': True})
        cls.provider_anthropic = cls.env.ref('muk_ai.provider_anthropic')
        cls.provider_anthropic.sudo().api_key = 'test-key'
        cls.provider_google = cls.env.ref('muk_ai.provider_google')
        cls.provider_google.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def enter_registry_test_mode(self) -> Iterator[None]:
        """Make new cursors opened on this registry reuse the test cursor.

        Mirrors the helper Odoo 19 provides on ``TransactionCase``; on 17.0 the
        registry primitives have to be driven directly.
        """
        env = self.env
        env.flush_all()
        self.registry.enter_test_mode(self.cr)
        try:
            yield
        finally:
            self.registry.leave_test_mode()
            env.invalidate_all()

    def _create_model(self, technical_name: str, **values) -> models.BaseModel:
        """Create a catalog model record for ``technical_name`` on the provider."""
        return self.env['muk_ai.model'].create(
            {
                'name': technical_name,
                'provider_id': self.provider.id,
                'technical_name': technical_name,
                'context_window': 400000,
                'input_rate': 1.0,
                'output_rate': 1.0,
                **values,
            }
        )

    @classmethod
    def _clear_default_models(cls, modality: str = 'chat') -> None:
        """Unset the default model of the modality on every provider."""
        cls.env['muk_ai.provider'].with_context(active_test=False).search([]).write(
            {f'default_{modality}_model_id': False},
        )

    @classmethod
    def _mark_sensitive(cls, *model_names: str) -> None:
        """Flag the given models as AI-sensitive for approval tests."""
        cls.env['ir.model'].sudo().search(
            [('model', 'in', list(model_names))],
        ).write({'ai_sensitive': True})

    def _mock_http_response(self, payload: dict, status_code: int = 200) -> MagicMock:
        """Build a mocked HTTP response returning the given JSON payload."""
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @contextmanager
    def _mock_responses(self, payloads: list) -> Iterator[MagicMock]:
        """Patch the provider to pop one mocked payload per LLM request."""
        remaining = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if not remaining:
                msg = 'No more mocked responses'
                raise AssertionError(msg)
            return remaining.pop(0)

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ) as mock:
            yield mock

    def _make_text_response(self, text: str = 'ok') -> dict:
        """Build a provider payload emitting plain assistant text."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_tokens': 0},
        }

    def _patch_tool(
        self, result_by_tool: dict[str, str]
    ) -> tuple[AbstractContextManager[MagicMock], list[str]]:
        """Patch MCP tool execution to serve canned results per tool name.

        :return: the patcher and the list collecting the executed tool names
        """
        calls: list[str] = []

        def fake(self_arg, name, arguments, env, enforce_scope):
            calls.append(name)
            return result_by_tool.get(name, '{"ok": true}'), {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        ), calls


class ImageCase(AITestCommon):
    """Shared fixtures: an image model on OpenAI and a rendered-image stub."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.image = cls.env['muk_ai.model'].create(
            {
                'name': 'Test Image',
                'provider_id': cls.provider.id,
                'technical_name': 'gpt-image-test',
                'modality': 'image',
                'input_rate': 0.0,
                'output_rate': 0.25,
            }
        )
        cls.chat_anthropic = cls.env['muk_ai.model'].create(
            {
                'name': 'Claude',
                'provider_id': cls.provider_anthropic.id,
                'technical_name': 'claude-test',
                'context_window': 200000,
                'input_rate': 1.0,
                'output_rate': 1.0,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _post(self, payload: dict, captured: dict) -> AbstractContextManager:
        """Return a patch of the pooled POST answering ``payload``.

        :param captured: filled with the request kwargs and its ``url``
        """

        def fake(self_arg, url, **kwargs):
            captured.update(kwargs, url=url)
            return self._mock_http_response(payload)

        return patch.object(requests.Session, 'post', autospec=True, side_effect=fake)

    def _rendered(self, revised: str = '') -> dict:
        """Return what ``generate_image`` answers for a rendered image."""
        return {
            'data_b64': PNG_1x1,
            'mimetype': 'image/png',
            'revised_prompt': revised,
            'usage': {'images': 1},
        }

    def _session(self, agent: models.BaseModel) -> models.BaseModel:
        """Create a session bound to ``agent``."""
        return self.env['muk_ai.session'].create(
            {'name': 'images', 'agent_id': agent.id}
        )

    def _painter_session(self) -> models.BaseModel:
        """Create a session whose agent renders with the fixture image model."""
        return self._session(
            self.env['muk_ai.agent'].create(
                {
                    'name': 'Painter',
                    'enable_image_generation': True,
                    'image_model_id': self.image.id,
                }
            )
        )

    def _tool_result(self) -> dict:
        """Return the tool result the image tool produces for ``self.image``."""
        return {
            'type': 'image',
            'filename': 'generated.png',
            'mimetype': 'image/png',
            'content_base64': PNG_1x1,
            'model': self.image.technical_name,
            'revised_prompt': '',
            'cost': {
                'usage': {'images': 1},
                'total': 0.25,
                'currency': 'USD',
            },
        }


class ToolCatalogMixin:
    """Serve a fixture MCP tool catalog to the test case mixing it in."""

    catalog: list[dict] = []

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_catalog(self) -> AbstractContextManager[MagicMock]:
        """Patch the MCP tool listing to return this case's fixture catalog."""
        return patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=list(self.catalog),
        )
