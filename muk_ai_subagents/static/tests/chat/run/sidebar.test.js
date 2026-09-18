import { describe, expect, test } from '@odoo/hoot';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';
import '@muk_ai_subagents/chat/run/chat_patch';

describe.current.tags('muk_ai_subagents');
defineMailModels();

/** Return the chat prototype, which is where the domains are decided. */
function chat() {
    return Object.assign(Object.create(AIChat.prototype), { state: {} });
}

/** Tell whether a domain constrains a field. */
function constrains(domain, field) {
    return domain.some((leaf) => Array.isArray(leaf) && leaf[0] === field);
}

test('the sidebar asks only for conversations the user started', () => {
    expect(constrains(chat().ownSessionsDomain, 'parent_session_id')).toBe(true);
});

test('searching the sidebar never offers a subagent as a chat to open', () => {
    // A subagent is opened from the run it belongs to and nowhere else, so
    // the search has to be narrowed exactly like the list it replaces.
    const domain = chat().sessionSearchDomain('Frist');
    expect(constrains(domain, 'parent_session_id')).toBe(true);
    expect(constrains(domain, 'name')).toBe(true);
});
