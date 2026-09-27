import { describe, expect, test } from '@odoo/hoot';
import { contains, mountView } from '@web/../tests/web_test_helpers';

import { defineProductModels, listArch } from './helpers/product_model';

import '@muk_web_utils/views/fields/text_icons/text_icon';

describe.current.tags('muk_web_utils');

defineProductModels();

const ARCH = listArch({
    body: `
        <field name="description" widget="text_icon" nolabel="1" options="{'icon': 'book'}"/>
        <field name="note" widget="text_icon" nolabel="1" options="{'icon': 'notes'}"/>
    `,
});

// ----------------------------------------------------------
// Tests

test('the icon is shown only for non-empty text and html values', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: ARCH });
    expect('tbody tr:nth-child(1) .oi[data-icon="book"]').toHaveAttribute(
        'title',
        'Description',
    );
    expect('tbody tr:nth-child(1) .oi[data-icon="notes"]').toHaveCount(1);
    expect('tbody tr:nth-child(2) .oi').toHaveCount(0);
});

test('clicking the icon reveals the text value in a popover', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: ARCH });
    await contains('tbody tr:nth-child(1) .oi[data-icon="book"]').click();
    expect('.o_popover .mk_text_value_popover').toHaveText('Has value');
});
