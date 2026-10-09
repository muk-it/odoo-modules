/** @odoo-module */

import { startServer } from '@bus/../tests/helpers/mock_python_environment';

import { Composer } from '@mail/core/common/composer';
import { Command } from '@mail/../tests/helpers/command';
import { start } from '@mail/../tests/helpers/test_utils';

import { patchWithCleanup } from '@web/../tests/helpers/utils';
import { contains, insertText } from '@web/../tests/utils';

QUnit.module('mention_suggestions', {
    beforeEach() {
        patchWithCleanup(Composer.prototype, {
            isEventTrusted() {
                return true;
            },
        });
    },
});

/**
 * Open a conversation answering its mention search with one non-member
 * contact, the way the server override adds the agents to its members.
 *
 * @param {string} channelType the kind of conversation, a group one being
 *  restricted to its members so that a mention cannot leak it
 * @param {boolean} isAgent whether the contact stands in for an AI agent
 * @returns {Promise<void>} resolved once Discuss shows the conversation
 */
async function openConversation(channelType, isAgent) {
    const pyEnv = await startServer();
    const colleagueId = pyEnv['res.partner'].create({ name: 'Chatter Colleague' });
    const channelId = pyEnv['discuss.channel'].create({
        name: 'Talk',
        channel_type: channelType,
        channel_member_ids: [
            Command.create({ partner_id: pyEnv.currentPartnerId }),
            Command.create({ partner_id: colleagueId }),
        ],
    });
    const { openDiscuss } = await start({
        mockRPC(route, args) {
            if (args.method === 'get_mention_suggestions_from_channel') {
                return [
                    {
                        id: 1234,
                        name: 'Chatter Agent',
                        type: 'partner',
                        is_ai_agent: isAgent,
                    },
                ];
            }
        },
    });
    await openDiscuss(channelId);
    await insertText('.o-mail-Composer-input', '@Chatter');
}

QUnit.test(
    'an agent is suggested first in a private conversation it is no member of',
    async (assert) => {
        await openConversation('group', true);
        await contains('.o-mail-Composer-suggestion', { count: 2 });
        const [first, second] = document.querySelectorAll(
            '.o-mail-Composer-suggestion',
        );
        assert.ok(first.textContent.includes('Chatter Agent'));
        assert.ok(second.textContent.includes('Chatter Colleague'));
    },
);

QUnit.test('an ordinary contact is still not suggested there', async () => {
    await openConversation('group', false);
    await contains('.o-mail-Composer-suggestion', { text: 'Chatter Colleague' });
    await contains('.o-mail-Composer-suggestion', { count: 0, text: 'Chatter Agent' });
});

QUnit.test('the patch leaves the suggestions of a public channel alone', async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv['res.partner'].create({ name: 'Chatter Colleague' });
    const channelId = pyEnv['discuss.channel'].create({
        name: 'Open Floor',
        channel_type: 'channel',
        channel_member_ids: [
            Command.create({ partner_id: pyEnv.currentPartnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    const { openDiscuss } = await start();
    await openDiscuss(channelId);
    await insertText('.o-mail-Composer-input', '@Chatter');
    await contains('.o-mail-Composer-suggestion', {
        count: 1,
        text: 'Chatter Colleague',
    });
});
