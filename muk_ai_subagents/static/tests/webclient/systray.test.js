import { describe, expect, test } from '@odoo/hoot';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';
import '@muk_ai_subagents/chat/run/chat_patch';

describe.current.tags('muk_ai_subagents');
defineMailModels();

/** Stand in for the chat-window service the systray drives. */
function mockChatWindows() {
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
}

/** Stand in for the bus the systray subscribes to. */
function mockBus() {
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
}

test('the chat list asks only for conversations the user started', async () => {
    const domains = [];
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        domains.push(kwargs.domain);
        return [];
    });
    mockBus();
    mockChatWindows();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    expect(systray.sessionDomain).toInclude(['parent_session_id', '=', false]);
    expect(domains.length).toBe(2);
    for (const domain of domains) {
        expect(
            domain.some(
                (leaf) => Array.isArray(leaf) && leaf[0] === 'parent_session_id',
            ),
        ).toBe(true);
    }
});
