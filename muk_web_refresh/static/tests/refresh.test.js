import { expect, test } from '@odoo/hoot';

import '@muk_web_refresh/search/control_panel';

import {
    models,
    fields,
    defineModels,
    mountView,
    onRpc,
    contains,
} from '@web/../tests/web_test_helpers';

class Product extends models.Model {
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
    name = fields.Char();
}
defineModels({ Product });

onRpc('has_group', () => true);

test.tags('muk_web_refresh');
test('refresh toggle switches active state', async () => {
        await mountView({
            type: 'list',
            resModel: 'product',
            arch: `<list><field name='name'/></list>`,
        });
        expect('.o_control_panel i.fa-refresh').toHaveClass('text-muted');
        expect('.o_control_panel i.fa-refresh').not.toHaveClass('fa-spin');
        await contains('.o_control_panel i.fa-refresh').click();
        expect('.o_control_panel i.fa-refresh').toHaveClass('fa-spin');
        expect('.o_control_panel i.fa-refresh').toHaveClass('text-info');
        expect('.o_control_panel i.fa-refresh').not.toHaveClass('text-muted');
        await contains('.o_control_panel i.fa-refresh').click();
        expect('.o_control_panel i.fa-refresh').not.toHaveClass('fa-spin');
        expect('.o_control_panel i.fa-refresh').toHaveClass('text-muted');
});
