import { expect, test } from '@odoo/hoot';
import { dblclick } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { mountView } from '@web/../tests/web_test_helpers';

import { defineTreeModels, TREE_ARCH } from './helpers/models';

defineTreeModels();

test.tags('muk_web_tree', 'desktop');
test('double click toggles auto refresh on a treelist', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-info');
});
