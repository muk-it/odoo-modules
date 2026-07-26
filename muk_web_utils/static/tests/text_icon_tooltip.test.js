import { describe, expect, test } from '@odoo/hoot';
import { queryText } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';

import { contains, mountView } from '@web/../tests/web_test_helpers';

import { defineProductModels, listArch } from './helpers/product_model';

import '@muk_web_utils/views/fields/text_icons/text_icon';

describe.current.tags('muk_web_utils');

defineProductModels();

const ARCH = listArch({
    body: `
        <field
            name="description"
            widget="text_icon"
            nolabel="1"
            options="{'icon': 'book'}"
        />
    `,
});

// ----------------------------------------------------------
// Tests

test('clicking the icon reveals the text value in a popover', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: ARCH });
    expect('.o_popover').toHaveCount(0);
    await contains('.o_list_table tbody tr:nth-child(1) .fa-book').click();
    await animationFrame();
    expect('.o_popover').toHaveCount(1);
    expect(queryText('.o_popover')).toBe('Has value');
});

test('the icon carries the field label as its title', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: ARCH });
    expect('.o_list_table tbody tr:nth-child(1) .fa-book').toHaveAttribute(
        'title',
        'Description',
    );
});
