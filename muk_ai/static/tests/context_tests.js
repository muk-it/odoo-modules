// @odoo-module

import {
    captureViewContext,
    probeCurrentView,
    registerViewTarget,
} from '@muk_ai/views/context';

QUnit.module('view_context');

QUnit.test(
    'an editor on top of a view pins its context while it has one',
    async (assert) => {
        const pinned = [];
        const env = {
            services: {
                action: { currentController: { props: { resModel: 'res.partner' } } },
                orm: {
                    read: async () => [],
                    call: async (model, method, [, payload]) => pinned.push(payload),
                },
                'muk_ai.chat_window': { sessionIds: [7] },
            },
        };
        const form = { kind: 'record', model: 'res.partner', id: 3 };
        let element = null;
        const unregister = registerViewTarget(() => element);
        assert.strictEqual((await probeCurrentView(env)).kind, 'list');
        captureViewContext(env, form);
        element = { kind: 'element', model: 'mailing.mailing', id: 1 };
        assert.strictEqual(await probeCurrentView(env), element);
        captureViewContext(env, form);
        unregister();
        assert.strictEqual((await probeCurrentView(env)).kind, 'list');
        captureViewContext(env, form);
        assert.deepEqual(pinned, [form, element, form]);
    },
);
