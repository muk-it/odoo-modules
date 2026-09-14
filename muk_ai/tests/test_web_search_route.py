from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from odoo import models
from odoo.tools.sql import column_exists

from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.tests.common import AITestCommon

MIGRATION = Path('migrations') / '17.0.1.19.12' / 'pre-migrate.py'


class TestWebSearchRouteChoice(AITestCommon):
    """Verify each explicit web search route is honoured instead of substituted."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _configure(self, backend: str | None) -> None:
        """Set or clear the global web search backend."""
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.search_backend', backend or False
        )
        self.env.invalidate_all()

    def _agent(self, route: str, **values) -> models.BaseModel:
        """Create an agent on the given web search route."""
        return self.env['muk_ai.agent'].create(
            {'name': f'Route {route}', 'web_search': route, **values}
        )

    # ----------------------------------------------------------
    # Tests: off
    # ----------------------------------------------------------

    def test_off_never_routes_and_never_warns(self):
        self._configure('brave')
        agent = self._agent('off')
        self.assertIsNone(agent._web_search_route())
        self.assertFalse(agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: automatic
    # ----------------------------------------------------------

    def test_automatic_prefers_the_backend_over_the_connector(self):
        self._configure('brave')
        self.assertEqual(self._agent('auto')._web_search_route(), 'tool')

    def test_automatic_falls_back_to_the_connector(self):
        self._configure(None)
        self.assertEqual(self._agent('auto')._web_search_route(), 'native')

    def test_automatic_warns_when_neither_route_serves(self):
        self._configure(None)
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            agent = self._agent('auto')
            self.assertIsNone(agent._web_search_route())
            self.assertIn('Web search is enabled', agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: provider built-in
    # ----------------------------------------------------------

    def test_native_is_kept_even_when_a_backend_is_configured(self):
        self._configure('brave')
        self.assertEqual(self._agent('native')._web_search_route(), 'native')

    def test_native_warns_instead_of_using_the_backend(self):
        self._configure('brave')
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            agent = self._agent('native')
            self.assertIsNone(agent._web_search_route())
            self.assertIn('"Provider Built-in"', agent.capability_warning)
            self.assertIn('serves no built-in search', agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: search backend
    # ----------------------------------------------------------

    def test_the_backend_route_is_kept_even_when_the_connector_serves(self):
        self._configure('brave')
        self.assertEqual(self._agent('tool')._web_search_route(), 'tool')

    def test_the_backend_route_warns_instead_of_using_the_connector(self):
        self._configure(None)
        agent = self._agent('tool')
        self.assertTrue(self.provider.supports_web_search)
        self.assertIsNone(agent._web_search_route())
        self.assertIn('"Search Backend"', agent.capability_warning)
        self.assertIn('no Web Search Backend is configured', agent.capability_warning)

    # ----------------------------------------------------------
    # Tests: tool filter conflicts
    # ----------------------------------------------------------

    def test_a_whitelist_without_the_tool_kills_the_backend_route(self):
        self._configure('brave')
        agent = self._agent('tool', tool_filter=['search_read'])
        self.assertIsNone(agent._web_search_route())
        self.assertIn('does not list "web_search"', agent.capability_warning)
        self.assertIn('Add it on the Tools page', agent.capability_warning)

    def test_a_whitelist_listing_the_tool_keeps_the_backend_route(self):
        self._configure('brave')
        agent = self._agent('tool', tool_filter=['search_read', 'web_search'])
        self.assertEqual(agent._web_search_route(), 'tool')
        self.assertFalse(agent.capability_warning)

    def test_a_whitelist_without_generate_image_is_named(self):
        self._configure(None)
        image = self.env['muk_ai.model'].create(
            {
                'name': 'Filter Image',
                'provider_id': self.provider.id,
                'technical_name': 'gpt-image-filter',
                'modality': 'image',
                'input_rate': 0.0,
                'output_rate': 0.25,
            }
        )
        agent = self._agent(
            'off',
            enable_image_generation=True,
            image_model_id=image.id,
            tool_filter=['search_read'],
        )
        self.assertIn('does not list "generate_image"', agent.capability_warning)
        agent.tool_filter = ['search_read', 'generate_image']
        self.assertFalse(agent.capability_warning)


class TestWebSearchMigration(AITestCommon):
    """Verify the boolean toggle maps onto the explicit route on upgrade."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _load_migration() -> ModuleType:
        """Import the pre-migration script of this release by path."""
        path = Path(__file__).resolve().parent.parent / MIGRATION
        spec = spec_from_file_location('muk_ai_web_search_pre_migrate', path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _restore_the_toggle(self, enabled: models.BaseModel) -> None:
        """Put the schema back on its pre-upgrade shape, with the toggle set."""
        self.env.flush_all()
        self.env.cr.execute(
            """
            ALTER TABLE muk_ai_agent ALTER COLUMN web_search DROP NOT NULL;
            ALTER TABLE muk_ai_agent ADD COLUMN enable_web_search boolean;
            UPDATE muk_ai_agent
               SET web_search = NULL,
                   enable_web_search = id IN %s
            """,
            (tuple(enabled.ids),),
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_toggle_maps_onto_the_route(self):
        agents = self.env['muk_ai.agent'].create(
            [{'name': 'Was On'}, {'name': 'Was Off'}]
        )
        on, off = agents
        self._restore_the_toggle(on)
        self._load_migration().migrate(self.env.cr, '17.0.1.19.11')
        self.env.cr.execute(
            'SELECT id, web_search FROM muk_ai_agent WHERE id IN %s',
            (tuple(agents.ids),),
        )
        routes = dict(self.env.cr.fetchall())
        self.env.invalidate_all()
        self.assertEqual(routes[on.id], 'auto')
        self.assertEqual(routes[off.id], 'off')
        self.assertFalse(
            column_exists(self.env.cr, 'muk_ai_agent', 'enable_web_search')
        )

    def test_a_database_without_the_toggle_is_left_alone(self):
        self._load_migration().migrate(self.env.cr, '17.0.1.19.11')
        agent = self.env['muk_ai.agent'].create({'name': 'Fresh'})
        self.assertEqual(agent.web_search, 'off')
