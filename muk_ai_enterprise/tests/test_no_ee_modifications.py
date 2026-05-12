from odoo.tests.common import TransactionCase, tagged

EE_AI_MODELS = (
    'ai.agent',
    'ai.agent.source',
    'ai.composer',
    'ai.embedding',
    'ai.prompt.button',
    'ai.topic',
    'discuss.channel',
    'mail.composer.mixin',
    'mail.render.mixin',
    'mail.template',
    'mail.thread',
)


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestNoEeModifications(TransactionCase):
    """The bridge must NOT inherit-and-override any EE-owned model in a
    way that could change EE behaviour. We allow `_inherit` only on
    muk_ai-owned and base `muk_mcp.tool` types.

    The bridge legitimately may inherit ai.topic / ai.agent.source via
    Many2many *fields* on muk_ai.agent — that's not a model override.
    What we check here: muk_ai_enterprise does NOT register any model
    whose `_name` or `_inherit` targets an EE-AI model directly with a
    body of methods that could shadow EE.
    """

    def test_no_ee_model_shadowed_by_bridge(self):
        bridge_module = self.env['ir.module.module'].search([
            ('name', '=', 'muk_ai_enterprise'),
        ])
        self.assertTrue(bridge_module)
        models_owned = self.env['ir.model.data'].search([
            ('module', '=', 'muk_ai_enterprise'),
            ('model', '=', 'ir.model'),
        ])
        for record in models_owned:
            res = self.env['ir.model'].browse(record.res_id)
            self.assertNotIn(
                res.model, EE_AI_MODELS,
                "Bridge declared an ir.model record for EE-owned model "
                "%s — this is forbidden by the one-way design." % res.model,
            )

    def test_no_ee_field_added_by_bridge(self):
        field_xml_ids = self.env['ir.model.data'].search([
            ('module', '=', 'muk_ai_enterprise'),
            ('model', '=', 'ir.model.fields'),
        ])
        if not field_xml_ids:
            return
        fields_owned = self.env['ir.model.fields'].browse(
            field_xml_ids.mapped('res_id'),
        ).exists()
        bad = fields_owned.filtered(lambda f: f.model in EE_AI_MODELS)
        self.assertFalse(
            bad,
            "Bridge added fields to EE models: %s" % [
                f"{f.model}.{f.name}" for f in bad
            ],
        )

    def test_bridge_adapter_model_is_abstract(self):
        adapter = self.env.get('muk_ai_enterprise.ee_tools')
        self.assertIsNotNone(
            adapter,
            "Bridge adapter model must be registered.",
        )
        self.assertTrue(
            adapter._abstract,
            "muk_ai_enterprise.ee_tools must be an AbstractModel "
            "(not a concrete model that would create a table).",
        )
