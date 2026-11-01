from __future__ import annotations

from odoo import models


class ProductTemplate(models.Model):
    """Describe the content of a product for the AI."""

    _inherit = 'product.template'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def AI_TEXT_FIELDS(self) -> tuple[str, ...]:
        """Return the text fields the AI writes, when the database has them."""
        return (
            'name',
            'description_sale',
            'description_purchase',
            'description_ecommerce',
            'website_meta_title',
            'website_meta_description',
            'website_meta_keywords',
            'seo_name',
        )

    @property
    def AI_MANUAL_FIELDS(self) -> tuple[str, ...]:
        """Return the identifier and compliance fields the AI never writes."""
        return (
            'barcode',
            'default_code',
            'manufacturer_id',
            'manufacturer_name',
            'manufacturer_code',
            'manufacturer_url',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_values(self, names: list[str], lang: str | None = None) -> dict:
        """Read fields as plain values, relations by their display name."""
        record = self.with_context(lang=lang) if lang else self
        return {
            name: value.display_name
            if isinstance(value := record[name], models.BaseModel)
            else value
            for name in names
        }

    def _ai_product_context(self) -> dict:
        """Describe the content of the product for the AI, per language.

        Each text field carries its value in every product language; a field
        with ``markup`` keeps one structure and translates its texts only.
        """
        langs = self.env['res.lang'].search([]).mapped('code')
        texts, manual = (
            [name for name in names if name in self._fields]
            for names in (self.AI_TEXT_FIELDS, self.AI_MANUAL_FIELDS)
        )
        described = self.fields_get([*texts, *manual], ['string', 'type'])
        per_lang = {lang: self._ai_values(texts, lang) for lang in langs}
        return {
            'languages': langs,
            'fields': {
                name: {
                    **described[name],
                    'values': {lang: per_lang[lang][name] for lang in langs},
                    'markup': callable(self._fields[name].translate),
                }
                for name in texts
            },
            'never_generate': {
                name: {**described[name], 'value': value}
                for name, value in self._ai_values(manual).items()
            },
            'images': {
                'main': self.env['ir.attachment']
                .search(
                    [
                        ('res_model', '=', self._name),
                        ('res_id', '=', self.id),
                        ('res_field', '=', 'image_1920'),
                    ],
                    limit=1,
                )
                .id,
                'extra': len(self.product_template_image_ids)
                if 'product_template_image_ids' in self._fields
                else None,
            },
            'documents': self.env['ir.attachment']
            .search([('res_model', '=', self._name), ('res_id', '=', self.id)])
            .read(['name', 'mimetype']),
        }
