import { describe, expect, test } from '@odoo/hoot';
import { press } from '@odoo/hoot-dom';

import { onRpc, serverState } from '@web/../tests/web_test_helpers';
import {
    click,
    contains,
    defineMailModels,
    openFormView,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';

describe.current.tags('muk_mail_route', 'desktop');
defineMailModels();

test('picked messages open the router with a rule, ranges by shift-click, escape leaves', async () => {
    const pyEnv = await startServer();
    const [recordId, customerId] = pyEnv['res.partner'].create([
        { name: 'Berger Logistik' },
        { name: 'Jonas Weber' },
    ]);
    const messageIds = pyEnv['mail.message'].create(
        ['Invoice question', 'Freight charged twice', 'Delivery delay'].map(
            (body, index) => ({
                author_id: index < 2 ? customerId : serverState.partnerId,
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
    pyEnv['mail.message'].create({
        message_type: 'notification',
        model: 'res.partner',
        res_id: recordId,
        tracking_value_ids: [
            pyEnv['mail.tracking.value'].create({
                field_id: fieldId,
                old_value_char: 'Berger',
                new_value_char: 'Berger Logistik',
            }),
        ],
    });
    onRpc('mail.message', 'get_route_configurations', () => [
        { id: 1, name: 'New Ticket' },
    ]);
    onRpc('mail.message', 'action_route_message', ({ args }) => {
        expect.step([...args[0]].sort((a, b) => a - b));
        return { type: 'ir.actions.act_window_close' };
    });
    await start();
    await openFormView('res.partner', recordId);
    await click(".o-mail-Message:contains('Delivery delay') [title='Expand']");
    await click(".o-dropdown-item:text('Move')");
    await contains('.mk_move_count', { text: '1 selected' });
    await contains('.o-mail-Message.mk_move_disabled input:disabled');
    await click(".o-mail-Message:contains('Invoice question')", { shiftKey: true });
    await contains('.mk_move_count', { text: '3 selected' });
    await click(".o-mail-Message:contains('Freight charged twice')");
    await contains('.o-mail-Message.mk_move_selected', { count: 2 });
    await click('.mk_move_confirm');
    await click(".mk_move_configuration:text('New Ticket')");
    await expect.waitForSteps([[messageIds[0], messageIds[2]]]);
    press('Escape');
    await contains('.mk_move_bar', { count: 0 });
    await contains('.o-mail-Chatter-sendMessage');
});
