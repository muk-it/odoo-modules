import { expect, test } from '@odoo/hoot';
import { mountView } from '@web/../tests/web_test_helpers';

import { defineTreeModels, TREE_ARCH } from './helpers/models';

defineTreeModels();

/**
 * Build a search view carrying a search panel on the parent field.
 * @param {string} [attributes] extra attributes of the searchpanel node
 * @returns {string} the search view arch
 */
function searchPanelArch(attributes = '') {
    return `
        <search>
            <searchpanel ${attributes}>
                <field name="parent_id"/>
            </searchpanel>
        </search>
    `;
}

test.tags('muk_web_tree', 'desktop');
test('a treelist shows the search panel of its list', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: searchPanelArch(),
    });
    expect('.o_search_panel').toHaveCount(1);
});

test.tags('muk_web_tree', 'desktop');
test('a search panel limited to other views stays hidden', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: searchPanelArch('view_types="kanban"'),
    });
    expect('.o_search_panel').toHaveCount(0);
});
