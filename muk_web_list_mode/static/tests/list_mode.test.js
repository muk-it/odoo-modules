import { expect, test } from '@odoo/hoot';

import { 
    models, 
    fields, 
    defineModels, 
    mountView, 
    onRpc 
} from '@web/../tests/web_test_helpers';

import '@muk_web_list_mode/views/list/list_controller';

class Product extends models.Model {
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
    name = fields.Char();
}

defineModels({ Product });

onRpc('has_group', () => true);

test.tags('muk_web_list_mode');
test('renders mode switch in list view', async () => {
        await mountView({
            type: 'list',
            resModel: 'product',
            arch: '<list><field name="name"/></list>',
        });
        expect('.mk_mode_switch').toHaveCount(1);
    }
);
