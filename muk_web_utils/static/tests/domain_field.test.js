import { describe, expect, test } from '@odoo/hoot';
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';

import '@muk_web_utils/views/fields/domain/domain';

describe.current.tags('muk_web_utils');

class Filter extends models.Model {
    _name = 'muk_web_utils.filter';
    domain = fields.Char();
    _records = [
        { id: 1, domain: '[("id", "=", uid)]' },
        { id: 2, domain: '[("id", "=", unknown_name)]' },
    ];
}

defineModels([Filter]);

// ----------------------------------------------------------
// Tests

test('the non-literal warning is shown only when the domain fails to evaluate', async () => {
    mockService('notification', {
        add(message) {
            expect.step(String(message));
        },
    });
    for (const resId of [1, 2]) {
        await mountView({
            type: 'form',
            resModel: 'muk_web_utils.filter',
            resId,
            arch: `
                <form>
                    <field
                        name="domain"
                        widget="domain"
                        options="{'model': 'muk_web_utils.filter', 'allow_expressions': True}"
                    />
                </form>`,
        });
    }
    expect.verifySteps([
        'The domain involves non-literals. Their evaluation might fail.',
    ]);
});
