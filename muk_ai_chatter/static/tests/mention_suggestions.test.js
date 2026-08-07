import { describe, expect, test } from '@odoo/hoot';
import { Command, onRpc, serverState } from '@web/../tests/web_test_helpers';
import {
    contains,
    defineMailModels,
    insertText,
    openDiscuss,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';

import '@muk_ai_chatter/mention/suggestion_service_patch';

describe.current.tags('muk_ai_chatter', 'desktop');
defineMailModels();

/**
 * Answer the conversation mention search with one non-member contact.
 *
 * Stands in for the server override, which adds the agents to the members the
 * base method returns. What is under test is what the client then does with
 * them, so the contact is handed over the same way and nothing else.
 *
 * @param {number} partnerId the contact to suggest
 * @param {string} name the name it is suggested under
 * @param {boolean} isAgent whether it stands in for an AI agent
 */
function suggestOutsider(partnerId, name, isAgent) {
    onRpc('res.partner', 'get_mention_suggestions_from_channel', () => ({
        'res.partner': [{ id: partnerId, name, is_ai_agent: isAgent }],
    }));
}

/**
 * Open a private conversation the given contact is no member of.
 *
 * A group conversation is the case Discuss narrows the `@` list for: only its
 * members may be suggested, so that a mention cannot leak it to an outsider.
 *
 * @returns {Promise<void>} resolved once Discuss shows the conversation
 */
async function openPrivateConversation() {
    const pyEnv = await startServer();
    const channelId = pyEnv['discuss.channel'].create({
        name: 'Private Talk',
        channel_type: 'group',
        channel_member_ids: [Command.create({ partner_id: serverState.partnerId })],
    });
    await start();
    await openDiscuss(channelId);
}

test('an agent is suggested in a private conversation it is no member of', async () => {
    suggestOutsider(1234, 'Chatter Agent', true);
    await openPrivateConversation();
    await insertText('.o-mail-Composer-input', '@Chatter');
    await contains('.o-mail-NavigableList-item', { text: 'Chatter Agent' });
});

test('an ordinary contact is still not suggested there', async () => {
    suggestOutsider(1234, 'Chatter Agent', false);
    await openPrivateConversation();
    await insertText('.o-mail-Composer-input', '@Chatter');
    await contains('.o-mail-NavigableList-item', { count: 0, text: 'Chatter Agent' });
});

test('the patch leaves the suggestions of a public channel alone', async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv['res.partner'].create({ name: 'Chatter Colleague' });
    const channelId = pyEnv['discuss.channel'].create({
        name: 'Open Floor',
        channel_type: 'channel',
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: partnerId }),
        ],
    });
    await start();
    await openDiscuss(channelId);
    await insertText('.o-mail-Composer-input', '@Chatter');
    await contains('.o-mail-NavigableList-item', { text: 'Chatter Colleague' });
    expect('.o-mail-NavigableList-item').toHaveCount(1);
});
