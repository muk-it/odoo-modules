import inspect
import logging

from odoo.tests.common import TransactionCase, tagged

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestResPartner(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_contact_number_is_generated_on_action(self):
        partner = self.env['res.partner'].create({
            'contact_number': False,
            'name': 'Test Partner',
        })
        partner.action_generate_contact_number()
        self.assertTrue(partner.contact_number)

    def test_contact_number_is_generated_on_create(self):
        Partner = self.env['res.partner']
        model_cls = type(Partner)
        create_method = model_cls.create
        create_src = inspect.getfile(create_method)
        mro_with_create = []
        for cls in model_cls.__mro__:
            if 'create' not in cls.__dict__:
                continue
            fn = cls.__dict__['create']
            wrapped = getattr(fn, '__wrapped__', fn)
            try:
                src_lines = inspect.getsource(wrapped)
                first_line = src_lines.strip().split('\n')[0]
            except (OSError, TypeError):
                first_line = '???'
            mro_with_create.append(
                f"{cls.__module__}:{cls.__qualname__}"
                f" -> {inspect.getfile(cls)}"
                f" first_line={first_line!r}"
            )
        _logger.info(
            "DEBUG test MRO: create resolved to %s:%s, "
            "model_cls.__bases__ count=%d, "
            "base_classes count=%d",
            create_src,
            getattr(create_method, '__qualname__', '?'),
            len(model_cls.__bases__),
            len(getattr(model_cls, '_base_classes__', ())),
        )
        for entry in mro_with_create:
            _logger.info("DEBUG MRO create entry: %s", entry)
        partner = Partner.create({
            'name': 'Test Partner',
        })
        self.assertTrue(partner.contact_number)

    def test_contact_number_is_inherited_for_child_contacts(self):
        parent = self.env['res.partner'].create({
            'name': 'Parent Partner',
        })
        child = self.env['res.partner'].create({
            'name': 'Child Partner',
            'parent_id': parent.id,
            'type': 'contact',
        })
        self.assertEqual(child.contact_number, parent.contact_number)

    def test_address_get_respects_default_invoice_delivery(self):
        partner = self.env['res.partner'].create({
            'name': 'Address Partner'
        })
        invoice = self.env['res.partner'].create({
            'name': 'Invoice Address',
            'parent_id': partner.id,
            'type': 'invoice',
        })
        delivery = self.env['res.partner'].create({
            'name': 'Delivery Address',
            'parent_id': partner.id,
            'type': 'delivery',
        })
        partner.write({
            'default_invoice_partner_id': invoice.id,
            'default_delivery_partner_id': delivery.id,
        })
        addresses = partner.address_get(['invoice', 'delivery'])
        self.assertEqual(addresses.get('invoice'), invoice.id)
        self.assertEqual(addresses.get('delivery'), delivery.id)

    def test_display_name_can_include_contact_number(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
        })
        self.assertTrue(partner.contact_number)
        self.assertIn(
            partner.contact_number,
            partner.with_context(show_contact_number=True).display_name
        )
        partner_formatted = partner.with_context(
            show_contact_number=True,
            formatted_display_name=True,
        )
        self.assertIn(
            f"--[{partner_formatted.contact_number}]--", 
                partner_formatted.display_name
        )
