from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    ids_field,
    model_field,
)


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_translated_values(self, target, values):
        """Return the translated fields of ``values`` given as ``{lang: value}``."""
        return {
            name: value
            for name, value in values.items()
            if isinstance(value, dict)
            and getattr(target._fields.get(name), 'translate', False)
        }

    @api.model
    def _mcp_write_translations(self, records, translated):
        """Write translated fields from one value per language.

        The ``en_US`` value is the source; a field translated by terms maps
        the terms of the source to those of each language, in order.
        """
        for name, texts in translated.items():
            field = records._fields[name]
            if 'en_US' in texts:
                records.with_context(lang='en_US').write({name: texts['en_US']})
            texts = {lang: text for lang, text in texts.items() if lang != 'en_US'}
            for record in records:
                translations = texts
                if callable(field.translate):
                    source = field.get_trans_terms(
                        record.with_context(lang='en_US')[name] or ''
                    )
                    translations = {}
                    for lang, text in texts.items():
                        terms = field.get_trans_terms(text or '')
                        if len(terms) != len(source):
                            raise UserError(_(
                                'The %(lang)s text of %(field)s has another '
                                'structure than its en_US text: keep its '
                                'tags and translate only its texts.',
                                lang=lang,
                                field=field.string,
                            ))
                        translations[lang] = dict(zip(source, terms, strict=True))
                record.update_field_translations(name, translations)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='create_records',
        description=(
            'Create a new record. Pass field values as a JSON object. For '
            'Many2one fields, pass the integer ID. For Many2many fields, '
            'use command tuples: [[6,0,[id1,id2]]] to set, [[4,id]] to '
            'add. For One2many fields, use [[0,0,{values}]] to create '
            'inline records. Check required fields with describe_model '
            'first. Fields Odoo computes itself on create are listed in '
            '"ignored_fields" when given, since their value is not kept.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values for the new record. Example: '
                        '{"name": "John", "email": "john@example.com", '
                        '"company_id": 1}.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'values'],
        },
        category='write',
    )
    def _mcp_create_records(self, model, values):
        """Create one record from ``values`` and return its id and display name.

        :raise UserError: when ``values`` is not a JSON object.
        """
        if not isinstance(values, dict):
            raise UserError(_('Pass "values" as one JSON object.'))
        target = self._resolve_model(model)
        ignored = sorted(
            name for name in values
            if (field := target._fields.get(name))
            and field.compute and field.readonly and not field.precompute
        )
        translated = self._mcp_translated_values(target, values)
        with self.env.cr.savepoint():
            record = target.create({
                **values,
                **{
                    name: texts.get(self.env.lang, next(iter(texts.values())))
                    for name, texts in translated.items()
                },
            })
            self._mcp_write_translations(record, translated)
            self._mcp_assert_records_allowed(model, [record.id])
        result = {'id': record.id, 'display_name': record.display_name}
        return {**result, 'ignored_fields': ignored} if ignored else result

    @api.model
    @mcp_tool(
        name='update_records',
        description=(
            'Update existing records by their IDs. Only pass the fields '
            'you want to change — other fields remain untouched. Same '
            'value formats as create_records apply for relational fields.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'ids': ids_field('update'),
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values to change. Only include fields you '
                        'want to modify.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'ids', 'values'],
        },
        category='write',
    )
    def _mcp_update_records(self, model, ids, values):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
        records = self._resolve_model(model).browse(target_ids)
        values = values or {}
        translated = self._mcp_translated_values(records, values)
        records.write({
            name: value for name, value in values.items() if name not in translated
        })
        self._mcp_write_translations(records, translated)
        return {'success': True, 'ids': target_ids}

    @api.model
    @mcp_tool(
        name='delete_records',
        description=(
            'Permanently delete records by their IDs. This cannot be '
            'undone. Some records cannot be deleted if other records '
            'depend on them (e.g. you cannot delete a partner that has '
            'invoices). Consider archiving (setting active=false) instead '
            'of deleting.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'ids': ids_field('permanently delete'),
                'context': context_field(),
            },
            'required': ['model', 'ids'],
        },
        category='write',
    )
    def _mcp_delete_records(self, model, ids):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
        self._resolve_model(model).browse(target_ids).unlink()
        return {'success': True, 'deleted_ids': target_ids}
