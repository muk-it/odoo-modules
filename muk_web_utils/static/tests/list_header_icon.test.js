import { expect, test } from '@odoo/hoot';
import { mountView } from '@web/../tests/web_test_helpers';

import { defineProductModels, listArch } from './helpers/product_model';

defineProductModels();

test.tags('muk_web_utils');
test('list column with icon renders header icon', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: listArch({
            body: `<field name="name" string="Name" icon="star"/>`,
        }),
    });
    expect('.o_list_table thead th i.oi[data-icon="star"]').toHaveCount(1);
    expect('.o_list_table thead th:contains(Name)').toHaveCount(0);
});
