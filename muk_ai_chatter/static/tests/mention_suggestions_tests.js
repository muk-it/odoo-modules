/** @odoo-module */

import { start, startServer } from '@mail/../tests/helpers/test_utils';

import { contains } from '@web/../tests/utils';

const AGENT = { id: 1234, name: 'Chatter Agent', active: false, is_ai_agent: true };

/**
 * Answer the agent search the way the server does, recording who asked, and
 * report no AI session on a record's chatter.
 * @param {number[]} asked collects the channel ids the agents were asked for
 * @returns {Function} the mockRPC handler
 */
function agentSearch(asked) {
    return (route, args) => {
        if (args.method === 'get_ai_mention_suggestions') {
            asked.push(args.kwargs.channel_id);
            return [{ ...AGENT }];
        }
        if (args.method === 'get_ai_sessions_summary') {
            return { [args.args[0][0]]: { entries: [], total: 0 } };
        }
    };
}

/**
 * Return the names the open suggestion list shows, in order.
 * @returns {string[]} the suggested names
 */
function suggestedNames() {
    return [...document.querySelectorAll('.o_ComposerSuggestionView_part1')].map(
        (el) => el.textContent,
    );
}

QUnit.module('muk_ai_chatter', {}, function () {
    QUnit.module('mention_suggestions');

    QUnit.test(
        'an agent is suggested first in a private conversation it is no member of',
        async (assert) => {
            const pyEnv = await startServer();
            const colleagueId = pyEnv['res.partner'].create({
                name: 'Chatter Colleague',
            });
            pyEnv['res.users'].create({ partner_id: colleagueId });
            const channelId = pyEnv['mail.channel'].create({
                name: 'Talk',
                channel_type: 'group',
                channel_member_ids: [
                    [0, 0, { partner_id: pyEnv.currentPartnerId }],
                    [0, 0, { partner_id: colleagueId }],
                ],
            });
            const asked = [];
            const { insertText, messaging, openDiscuss } = await start({
                discuss: { params: { default_active_id: channelId } },
                mockRPC: agentSearch(asked),
            });
            messaging.currentUser.update({ isInternalUser: true });
            await openDiscuss();
            await insertText('.o_ComposerTextInput_textarea', '@Chatter');
            await contains('.o_ComposerSuggestionView', { count: 2 });
            assert.deepEqual([...new Set(asked)], [channelId]);
            assert.deepEqual(suggestedNames(), ['Chatter Agent', 'Chatter Colleague']);
        },
    );

    QUnit.test('the chatter of a record suggests no agent', async (assert) => {
        const pyEnv = await startServer();
        const recordId = pyEnv['res.partner'].create({ name: 'Chatter Record' });
        pyEnv['res.partner'].create({ name: 'Chatter Colleague' });
        const asked = [];
        const { click, insertText, messaging, openFormView } = await start({
            mockRPC: agentSearch(asked),
        });
        messaging.currentUser.update({ isInternalUser: true });
        await openFormView({ res_model: 'res.partner', res_id: recordId });
        await click('.o_ChatterTopbar_buttonSendMessage');
        await insertText('.o_ComposerTextInput_textarea', '@Chatter');
        await contains('.o_ComposerSuggestionView', { text: 'Chatter Colleague' });
        assert.deepEqual(asked, []);
        assert.notOk(suggestedNames().includes('Chatter Agent'));
        assert.ok(suggestedNames().includes('Chatter Colleague'));
    });
});
