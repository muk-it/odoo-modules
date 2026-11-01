from __future__ import annotations

import base64
import json
import re

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon, PNG_1x1


class TestProductContent(AITestCommon):
    """Read, write and illustrate a product through the writer's tools."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Activate English and German and create a product to work on."""
        super().setUpClass()
        cls.env['res.lang']._activate_lang('en_US')
        cls.env['res.lang']._activate_lang('de_DE')
        cls.agent = cls.env.ref('muk_ai_product.agent_product_writer')
        cls.template = cls.env['product.template'].create({'name': 'Flat steel'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tools(self, session: models.BaseModel | None = None) -> models.BaseModel:
        """Return the tools mixin, bound to a chat when one is given."""
        tools = self.env['muk_mcp.mixin']
        return tools.with_context(muk_mcp_session_id=session.id) if session else tools

    def _tool_response(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload calling one tool."""
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': arguments}],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 2, 'output_tokens': 1},
        }

    def _attachment(self, name: str, mimetype: str, data: bytes) -> models.BaseModel:
        """Store a document on the product."""
        return self.env['ir.attachment'].create(
            {
                'name': name,
                'mimetype': mimetype,
                'raw': data,
                'res_model': 'product.template',
                'res_id': self.template.id,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_context_offers_the_fields_the_installed_apps_add(self):
        context = self._tools()._mcp_product_context(self.template.id)
        self.assertLessEqual(
            {'name', 'description_sale', 'description_purchase'}, set(context['fields'])
        )
        self.assertLessEqual(
            {'barcode', 'default_code'}, set(context['never_generate'])
        )
        self.assertLessEqual({'en_US', 'de_DE'}, set(context['languages']))
        shop = self.env['ir.module.module']._get('website_sale').state == 'installed'
        shop_fields = {
            'description_ecommerce',
            'website_meta_title',
            'website_meta_description',
            'website_meta_keywords',
            'seo_name',
        }
        self.assertEqual(shop_fields <= set(context['fields']), shop)
        self.assertEqual(context['images'], {'main': 0, 'extra': 0 if shop else None})
        self.template.image_1920 = PNG_1x1
        main = self._tools()._mcp_product_context(self.template.id)['images']['main']
        self.assertEqual(self.env['ir.attachment'].browse(main).res_field, 'image_1920')

    def test_texts_per_language_and_images_are_approved_one_by_one(self):
        image = self._attachment('variant.png', 'image/png', base64.b64decode(PNG_1x1))
        self.template.image_1920 = PNG_1x1
        markup = 'description_ecommerce' in self.template._fields
        extra = 'product_template_image_ids' in self.template._fields
        texts = {
            'en_US': ('Flat steel 40 x 5 mm', 'Hot rolled S235JR flat steel.'),
            'de_DE': ('Flachstahl 40 x 5 mm', 'Warmgewalzter Flachstahl S235JR.'),
        }
        html = {lang: f'<p>{sale}</p>' for lang, (_name, sale) in texts.items()}
        calls = [
            (
                'update_records',
                {
                    'model': 'product.template',
                    'ids': [self.template.id],
                    'values': {
                        'name': name,
                        'description_sale': sale,
                        **(
                            {
                                'description_ecommerce': html[lang]
                                if lang == 'en_US'
                                else html
                            }
                            if markup
                            else {}
                        ),
                    },
                    'context': {'lang': lang},
                },
            )
            for lang, (name, sale) in texts.items()
        ]
        labelled = 'Flat steel packshot'
        calls.append(
            (
                'create_records',
                {
                    'model': 'product.image',
                    'values': {
                        'product_tmpl_id': self.template.id,
                        'name': labelled,
                        'image_1920': f'@attachment:{image.id}',
                    },
                }
                if extra
                else {
                    'model': 'ir.attachment',
                    'values': {
                        'name': f'{labelled}.png',
                        'res_model': 'product.template',
                        'res_id': self.template.id,
                        'datas': f'@attachment:{image.id}',
                    },
                },
            )
        )
        session = self.env['muk_ai.session'].create(
            {'name': 'Test chat', 'agent_id': self.agent.id}
        )
        with self._mock_responses(
            [
                *(
                    self._tool_response(name, arguments, f'c{index}')
                    for index, (name, arguments) in enumerate(calls)
                ),
                self._make_text_response(),
            ]
        ):
            session.start('Complete the product')
            for _name, arguments in calls[:-1]:
                with self.subTest(lang=arguments['context']['lang']):
                    self.assertEqual(session.state, 'waiting')
                    self.assertEqual(
                        [
                            change['field']
                            for change in session.pending_ask['preview']['changes']
                        ],
                        list(arguments['values']),
                    )
                    session.approve_tool()
        self.assertEqual(session.state, 'done')
        fields = self._tools()._mcp_product_context(self.template.id)['fields']
        for lang, (name, sale) in texts.items():
            with self.subTest(lang=lang):
                self.assertEqual(fields['name']['values'][lang], name)
                self.assertEqual(fields['description_sale']['values'][lang], sale)
                if markup:
                    self.assertEqual(
                        fields['description_ecommerce']['values'][lang], html[lang]
                    )
        added = (
            self.template.product_template_image_ids
            if extra
            else self.env['ir.attachment'].search(
                [('res_model', '=', 'product.template'), ('name', 'like', labelled)]
            )
        )
        self.assertEqual(
            added.mapped('name'), [labelled if extra else f'{labelled}.png']
        )

    def test_the_skills_name_only_the_tools_of_the_writer(self):
        skills = self.env['muk_ai.skill'].search([('agent_ids', 'in', self.agent.ids)])
        self.assertEqual(len(skills), 3)
        tools = self.env['muk_mcp.mixin']
        for skill in skills:
            with self.subTest(skill=skill.name):
                self.assertLessEqual(
                    {
                        word
                        for word in re.findall(r'`(\w+)', skill.body)
                        if hasattr(tools, f'_mcp_{word}')
                    },
                    set(self.agent.tool_filter),
                )
