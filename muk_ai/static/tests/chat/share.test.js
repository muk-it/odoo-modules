import { animationFrame, expect, queryAllTexts, runAllTimers, test } from '@odoo/hoot';
import {
    contains,
    mountWithCleanup,
    MockServer,
    onRpc,
} from '@web/../tests/web_test_helpers';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import {
    defineAIModels,
    getChat,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

async function mountShareBar(values = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session } });
    return session;
}

async function makeColleagues() {
    await getChat();
    const env = MockServer.env;
    return ['Marc Demo', 'Joel Willis'].map((name) =>
        env['res.users'].create({
            partner_id: env['res.partner'].create({ name }),
            login: name,
        }),
    );
}

test('the bar states who can read the chat and offers to change it to its owner only', async () => {
    const [marc, joel] = await makeColleagues();
    const session = await mountShareBar();
    for (const [values, summary, button, faces] of [
        [{ share_user_ids: [] }, 'Only you can read this chat', 'Share', 0],
        [{ share_user_ids: [marc] }, '1 person can read this chat', 'Manage', 1],
        [{ share_user_ids: [marc, joel] }, '2 people can read this chat', 'Manage', 2],
        [
            { share_user_ids: [marc], can_write: false },
            '1 person can read this chat',
            null,
            1,
        ],
    ]) {
        Object.assign(session.data, { can_write: true, ...values });
        await animationFrame();
        expect('.mk_share_bar > span:not(.mk_share_faces)').toHaveText(summary);
        expect('.mk_share_faces img').toHaveCount(faces);
        expect(queryAllTexts('.mk_share_edit')).toEqual(button ? [button] : []);
    }
});

test.tags('desktop');
test('the dialog adds and removes readers and saves only a change', async () => {
    const [marc, joel] = await makeColleagues();
    onRpc('muk_ai.session', 'write', ({ args }) =>
        expect.step(JSON.stringify(args[1])),
    );
    await mountShareBar({ share_user_ids: [marc] });
    await contains('.mk_share_edit').click();
    expect(queryAllTexts('.modal .o_tag')).toEqual(['Marc Demo']);
    expect('.modal-footer .btn-primary').toHaveProperty('disabled', true);
    await contains('.modal .o-autocomplete--input').edit('Joel', { confirm: false });
    await runAllTimers();
    await contains('.o-autocomplete--dropdown-item:contains(Joel Willis)').click();
    expect('.modal-footer .btn-primary').toHaveProperty('disabled', false);
    expect('.modal-footer .btn-secondary').toHaveText('Discard');
    await contains('.modal .o_tag:contains(Marc Demo) .o_delete', {
        visible: false,
    }).click();
    await contains('.modal-footer .btn-primary').click();
    expect.verifySteps([JSON.stringify({ share_user_ids: [[6, 0, [joel]]] })]);
    expect('.modal').toHaveCount(0);
    expect('.mk_share_bar').toHaveText(/1 person can read this chat/);
});
