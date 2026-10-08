import { advanceTime, animationFrame, expect, mockDate, test } from '@odoo/hoot';
import { contains, mountWebClient } from '@web/../tests/web_test_helpers';

import { defineAIModels, emit } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const notice = (state, values = {}) => ({
    session_id: 2,
    state,
    session_name: 'Monthly report',
    message: 'Finished',
    at: '2026-01-01 09:59:30',
    ...values,
});

test('a finished chat toasts with a button opening it on the page', async () => {
    mockDate('2026-01-01 10:00:00', 0);
    await mountWebClient();
    await emit('muk_ai.session_notification', notice('done'));
    expect('.o_notification').toHaveText(/^Monthly report\. Finished\s+Open$/);
    await contains('.o_notification button:contains(Open)').click();
    await animationFrame();
    expect('.o_action_manager .mk_chat .mk_main_title').toHaveText('Other');
});

test('a chat waiting for its owner keeps its toast until the chat is shown', async () => {
    mockDate('2026-01-01 10:00:00', 0);
    await mountWebClient();
    await emit(
        'muk_ai.session_notification',
        notice('waiting', { message: 'Needs your approval before running a tool' }),
    );
    await emit(
        'muk_ai.session_notification',
        notice('error', { message: 'Stopped: quota exceeded' }),
    );
    expect('.o_notification').toHaveCount(2);
    await advanceTime(10000);
    expect('.o_notification').toHaveCount(2);
    await contains('.o_notification:first button:contains(Open)').click();
    await animationFrame();
    expect('.o_notification').toHaveCount(0);
});
