import { after, describe, expect, test } from '@odoo/hoot';

import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { rpcBus } from '@web/core/network/rpc';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_mail_route/core/view_cache/view_cache';

describe.current.tags('muk_mail_route', 'desktop');

class Configuration extends models.Model {
    _name = 'muk_mail_route.configuration';
    name = fields.Char();
}

class Note extends models.Model {
    _name = 'x_test_note';
    name = fields.Char();
}

defineMailModels();
defineModels({ Configuration, Note });

function listenToCacheClears() {
    const listener = (ev) => expect.step(`CLEAR-CACHES ${ev.detail}`);
    rpcBus.addEventListener('CLEAR-CACHES', listener);
    after(() => rpcBus.removeEventListener('CLEAR-CACHES', listener));
}

test('saving a router clears the cached views', async () => {
    onRpc('web_save', ({ model }) => expect.step(`web_save ${model}`));
    await mountView({
        type: 'form',
        resModel: 'muk_mail_route.configuration',
        arch: '<form><field name="name"/></form>',
    });
    listenToCacheClears();
    await contains('.o_field_widget[name=name] input').edit('Create Lead');
    await contains('.o_form_button_save').click();
    expect.verifySteps([
        'web_save muk_mail_route.configuration',
        'CLEAR-CACHES get_views',
    ]);
});

test('saving another record keeps the cached views', async () => {
    onRpc('web_save', ({ model }) => expect.step(`web_save ${model}`));
    await mountView({
        type: 'form',
        resModel: 'x_test_note',
        arch: '<form><field name="name"/></form>',
    });
    listenToCacheClears();
    await contains('.o_field_widget[name=name] input').edit('Azure Interior');
    await contains('.o_form_button_save').click();
    expect.verifySteps(['web_save x_test_note']);
});
