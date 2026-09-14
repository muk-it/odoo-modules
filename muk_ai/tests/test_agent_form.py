from __future__ import annotations

from lxml import etree

from odoo.api import Environment
from odoo.tests.common import TransactionCase, tagged


def agent_form_arch(env: Environment) -> etree._Element:
    """Return the parsed arch of the fully inherited agent form."""
    view = env.ref('muk_ai.view_ai_agent_form')
    return etree.fromstring(env['muk_ai.agent'].get_view(view.id, 'form')['arch'])


def ability_rows(env: Environment) -> list[str]:
    """Name each Abilities row by the field that carries its switch or picker.

    A row is either a plain field or a ``div`` pairing a switch with what
    performs the ability; the hidden placeholder fields carry no row.
    """
    group = agent_form_arch(env).xpath("//group[@name='abilities']")[0]
    rows = []
    for node in group:
        if node.tag == 'div':
            rows.append(node.xpath('field')[0].get('name'))
        elif node.tag == 'field' and node.get('invisible') != '1':
            rows.append(node.get('name'))
    return rows


@tagged('post_install', '-at_install')
class TestAgentForm(TransactionCase):
    """Verify the agent form pairs every ability with what performs it."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_model_group_holds_the_chat_picks_only(self):
        group = agent_form_arch(self.env).xpath("//group[@name='model']")[0]
        names = [node.get('name') for node in group.xpath('field')]
        self.assertIn('provider_id', names)
        self.assertIn('model_id', names)
        self.assertIn('reasoning_effort', names)
        self.assertNotIn('image_model_id', names)
        self.assertNotIn('tts_model_id', names)
        self.assertNotIn('stt_model_id', names)

    def test_the_abilities_group_replaces_the_capabilities_one(self):
        arch = agent_form_arch(self.env)
        self.assertEqual(len(arch.xpath("//group[@name='abilities']")), 1)
        self.assertFalse(arch.xpath("//group[@name='capabilities']"))
        self.assertFalse(arch.xpath("//group[@name='models']"))

    def test_every_ability_row_names_what_performs_it(self):
        group = agent_form_arch(self.env).xpath("//group[@name='abilities']")[0]
        images = group.xpath(".//div[field[@name='enable_image_generation']]")
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0].xpath("field[@name='image_model_id']"))
        code = group.xpath(".//div[field[@name='enable_code_interpreter']]")
        self.assertEqual(len(code), 1)
        self.assertTrue(code[0].xpath("field[@name='code_interpreter_performer']"))

    def test_the_ability_rows_read_in_order(self):
        rows = ability_rows(self.env)
        self.assertEqual(rows[0], 'web_search')
        self.assertEqual(rows[-1], 'enable_code_interpreter')
        self.assertLess(
            rows.index('enable_image_generation'),
            rows.index('enable_code_interpreter'),
        )
