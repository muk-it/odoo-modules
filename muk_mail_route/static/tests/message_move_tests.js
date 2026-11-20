// @odoo-module

import { startServer } from '@bus/../tests/helpers/mock_python_environment';

import { start } from '@mail/../tests/helpers/test_utils';

import { makeDeferred, triggerHotkey } from '@web/../tests/helpers/utils';
import { click, contains } from '@web/../tests/utils';

QUnit.module('message_move');

QUnit.test(
    'escape leaves, picked messages open the router with a rule, ranges by shift-click',
    async (assert) => {
        const pyEnv = await startServer();
        const [recordId, customerId] = pyEnv['res.partner'].create([
            { name: 'Berger Logistik' },
            { name: 'Jonas Weber' },
        ]);
        const messageIds = pyEnv['mail.message'].create(
            ['Invoice question', 'Freight charged twice', 'Delivery delay'].map(
                (body, index) => ({
                    author_id: index < 2 ? customerId : pyEnv.currentPartnerId,
                    body,
                    message_type: 'comment',
                    model: 'res.partner',
                    res_id: recordId,
                }),
            ),
        );
        const fieldId = pyEnv['ir.model.fields'].create({
            model: 'res.partner',
            name: 'name',
            ttype: 'char',
        });
        const trackingId = pyEnv['mail.tracking.value'].create({
            field_id: fieldId,
            old_value_char: 'Berger',
            new_value_char: 'Berger Logistik',
        });
        pyEnv['mail.message'].create({
            body: '',
            message_type: 'notification',
            model: 'res.partner',
            res_id: recordId,
            tracking_value_ids: [trackingId],
        });
        const routed = makeDeferred();
        const { openFormView } = await start({
            mockRPC(route, args) {
                if (args.method === 'get_route_configurations') {
                    return [{ id: 1, name: 'New Ticket' }];
                }
                if (args.method === 'action_route_message') {
                    routed.resolve([...args.args[0]].sort((a, b) => a - b));
                    return { type: 'ir.actions.act_window_close' };
                }
            },
        });
        await openFormView('res.partner', recordId);
        const startMove = async () => {
            await click("[title='Expand']", {
                parent: ['.o-mail-Message', { text: 'Delivery delay' }],
            });
            await click('.dropdown-item', { text: 'Move' });
            await contains('.mk_move_count', { text: '1 selected' });
        };
        await startMove();
        await triggerHotkey('Escape');
        await contains('.mk_move_bar', { count: 0 });
        await contains('.o-mail-Chatter-sendMessage');
        await startMove();
        await contains('.o-mail-Message.mk_move_disabled input:disabled');
        await click('.o-mail-Message', { text: 'Invoice question', shiftKey: true });
        await contains('.mk_move_count', { text: '3 selected' });
        await click('.o-mail-Message', { text: 'Freight charged twice' });
        await contains('.o-mail-Message.mk_move_selected', { count: 2 });
        await click('.mk_move_confirm');
        await click('.mk_move_configuration', { text: 'New Ticket' });
        assert.deepEqual(await routed, [messageIds[0], messageIds[2]]);
    },
);
