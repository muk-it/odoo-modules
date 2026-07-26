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

import '@muk_contacts/js/partner_many2one';

describe.current.tags('muk_contacts');

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
 * Stub ``web_name_search`` on ``res.partner`` with the icon annotations the
 * Python override adds, then open the autocomplete dropdown.
 *
 * @param {Record<string, any>[]} rows the rows the name search should return
 * @param {string} [fieldName] the many2one field to type into
 * @returns {Promise<void>}
 */
async function openSuggestions(rows, fieldName = 'partner_id') {
    onRpc('res.partner', 'web_name_search', () => rows);
    await mountView({
        type: 'form',
        resModel: 'muk_contacts.lead',
        resId: 1,
        arch: `<form><field name="${fieldName}"/></form>`,
    });
    await contains(`[name="${fieldName}"] input`).edit('a', { confirm: false });
    await contains(`[name="${fieldName}"] input`).click();
}

test('a company suggestion is prefixed with the building icon', async () => {
    await openSuggestions([
        { id: 2, display_name: 'Acme Inc', company_type: 'company', type: 'contact' },
    ]);
    expect(`${SUGGESTION} i.fa-building`).toHaveCount(1);
    expect(SUGGESTION).toHaveText('Acme Inc');
});

test('a person suggestion is prefixed with the user icon', async () => {
    await openSuggestions([
        { id: 2, display_name: 'Ada Byron', company_type: 'person', type: 'contact' },
    ]);
    expect(`${SUGGESTION} i.fa-user`).toHaveCount(1);
});

test('the address type wins over the company type', async () => {
    await openSuggestions([
        {
            id: 2,
            display_name: 'Acme Billing',
            company_type: 'company',
            type: 'invoice',
        },
        {
            id: 3,
            display_name: 'Acme Warehouse',
            company_type: 'company',
            type: 'delivery',
        },
        { id: 4, display_name: 'Acme Other', company_type: 'company', type: 'other' },
    ]);
    expect(`${SUGGESTION} i.fa-usd`).toHaveCount(1);
    expect(`${SUGGESTION} i.fa-truck`).toHaveCount(1);
    expect(`${SUGGESTION} i.fa-address-book-o`).toHaveCount(1);
    expect(`${SUGGESTION} i.fa-building`).toHaveCount(0);
});

test('an unknown address type falls back to the address book icon', async () => {
    await openSuggestions([
        { id: 2, display_name: 'Odd One', company_type: 'person', type: 'private' },
    ]);
    expect(`${SUGGESTION} i.fa-address-book-o`).toHaveCount(1);
    expect(`${SUGGESTION} i.fa-user`).toHaveCount(0);
});

test('missing icon annotations fall back to the user icon', async () => {
    await openSuggestions([{ id: 2, display_name: 'Unannotated' }]);
    expect(`${SUGGESTION} i.fa-user`).toHaveCount(1);
});

test('the icon markup does not escape the highlighted display name', async () => {
    await openSuggestions([
        {
            id: 2,
            display_name: 'a<b>bold</b>',
            company_type: 'person',
            type: 'contact',
        },
    ]);
    expect(SUGGESTION).toHaveText('a<b>bold</b>');
    expect(`${SUGGESTION} b`).toHaveCount(0);
    expect(`${SUGGESTION} .text-primary`).toHaveCount(1);
});

test('suggestions for other models keep their plain label', async () => {
    await openSuggestions([], 'tag_id');
    expect(`${SUGGESTION}:first`).toHaveText('Hat');
    expect(`${SUGGESTION} i`).toHaveCount(0);
});
