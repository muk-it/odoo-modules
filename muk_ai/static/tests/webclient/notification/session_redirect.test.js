import { describe, expect, test } from '@odoo/hoot';

import {
    AI_SESSION_MODEL,
    aiSessionChatAction,
} from '@muk_ai/webclient/notification/session_redirect';

describe.current.tags('muk_ai');

test('aiSessionChatAction targets the chat client action for the session', () => {
    expect(aiSessionChatAction(7)).toEqual({
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params: { session_id: 7 },
    });
});

test('the AI session model constant matches the session model name', () => {
    expect(AI_SESSION_MODEL).toBe('muk_ai.session');
});
