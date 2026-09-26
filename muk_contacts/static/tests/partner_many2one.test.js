import { describe, expect, test } from '@odoo/hoot';
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_contacts/views/fields/partner_many2one/partner_many2one';

describe.current.tags('muk_contacts', 'desktop');

const SUGGESTION = '.o-autocomplete--dropdown-item:not(.o_m2o_dropdown_option)';

class Lead extends models.Model {
    _name = 'muk_contacts.lead';
    name = fields.Char();
    partner_id = fields.Many2one({ relation: 'res.partner' });
    tag_id = fields.Many2one({ relation: 'muk_contacts.tag' });
    _records = [{ id: 1, name: 'Lead', partner_id: false, tag_id: false }];
}

class Tag extends models.Model {
    _name = 'muk_contacts.tag';
    name = fields.Char();
    _records = [{ id: 1, name: 'Hat' }];
}

defineMailModels();
defineModels({ Lead, Tag });

/**
 * Stub ``web_name_search`` on ``res.partner`` with the given rows, record the
 * requested specification, then open the autocomplete dropdown.
 * @param {object[]} rows the rows the name search should return
 * @param {string} [fieldName] the many2one field to type into
 * @returns {Promise<object[]>} the specifications the searches asked for
 */
async function openSuggestions(rows, fieldName = 'partner_id') {
    const specifications = [];
    onRpc('res.partner', 'web_name_search', ({ kwargs }) => {
        specifications.push(kwargs.specification);
        return rows;
    });
    await mountView({
        type: 'form',
        resModel: 'muk_contacts.lead',
        resId: 1,
        arch: `<form><field name="${fieldName}"/></form>`,
    });
    await contains(`[name="${fieldName}"] input`).edit('a', { confirm: false });
    await contains(`[name="${fieldName}"] input`).click();
    return specifications;
}

test('the partner search asks for the contact kind', async () => {
    const specifications = await openSuggestions([]);
    expect(specifications.at(-1)).toEqual({ display_name: {}, contact_kind: {} });
});

test('each suggestion is prefixed with the icon of its kind', async () => {
    await openSuggestions([
        { id: 2, display_name: 'Acme Inc', contact_kind: 'company' },
        { id: 3, display_name: 'Ada Byron', contact_kind: 'person' },
        { id: 4, display_name: 'Acme Billing', contact_kind: 'invoice' },
        { id: 5, display_name: 'Acme Warehouse', contact_kind: 'delivery' },
        { id: 6, display_name: 'Acme Other', contact_kind: 'other' },
    ]);
    expect(`${SUGGESTION} i[data-icon=business]`).toHaveCount(1);
    expect(`${SUGGESTION} i[data-icon=person]`).toHaveCount(1);
    expect(`${SUGGESTION} i[data-icon=description]`).toHaveCount(1);
    expect(`${SUGGESTION} i[data-icon=local_shipping]`).toHaveCount(1);
    expect(`${SUGGESTION} i[data-icon=deployed_code]`).toHaveCount(1);
    expect(`${SUGGESTION}:first`).toHaveText('Acme Inc');
});

test('a suggestion without a kind falls back to the person icon', async () => {
    await openSuggestions([{ id: 2, display_name: 'Unannotated' }]);
    expect(`${SUGGESTION} i[data-icon=person]`).toHaveCount(1);
});

test('the icon markup does not escape the highlighted display name', async () => {
    await openSuggestions([
        { id: 2, display_name: 'a<b>bold</b>', contact_kind: 'person' },
    ]);
    expect(SUGGESTION).toHaveText('a<b>bold</b>');
    expect(`${SUGGESTION} b`).toHaveCount(0);
    expect(`${SUGGESTION} .text-primary`).toHaveCount(1);
});

test('suggestions for other models keep their plain label', async () => {
    const specifications = await openSuggestions([], 'tag_id');
    expect(specifications).toEqual([]);
    expect(`${SUGGESTION}:first`).toHaveText('Hat');
    expect(`${SUGGESTION} i`).toHaveCount(0);
});
