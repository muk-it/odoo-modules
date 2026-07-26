import { describe, expect, test } from '@odoo/hoot';

import { Store } from '@mail/core/common/store_service';
import { Thread } from '@mail/core/common/thread_model';
import { MessagingMenu } from '@mail/core/public_web/messaging_menu';
import '@mail/core/web/thread_model_patch';

import '@muk_ai/webclient/notification/session_redirect';

describe.current.tags('muk_ai');

const CHAT_ACTION_7 = {
    type: 'ir.actions.client',
    tag: 'muk_ai.chat',
    params: { session_id: 7 },
};

/**
 * Build a bare instance of a patched prototype wired to a recording action service.
 * @param {object} proto prototype carrying the patched methods
 * @param {object} [own] own properties to set on the instance
 * @returns {object} { instance, actions } where actions collects doAction payloads
 */
function withActionService(proto, own = {}) {
    const actions = [];
    const instance = Object.assign(Object.create(proto), own);
    instance.env = {
        services: {
            action: {
                doAction: (action) => {
                    actions.push(action);
                    return Promise.resolve();
                },
            },
        },
    };
    return { instance, actions };
}

// ----------------------------------------------------------
// Store.openDocument
// ----------------------------------------------------------

test('openDocument sends an AI session to the chat client action', () => {
    const { instance, actions } = withActionService(Store.prototype);
    instance.openDocument({ id: 7, model: 'muk_ai.session' });
    expect(actions).toEqual([CHAT_ACTION_7]);
});

test('openDocument still opens the form view of any other model', () => {
    const { instance, actions } = withActionService(Store.prototype);
    instance.openDocument({ id: 4, model: 'res.partner' });
    expect(actions).toEqual([
        {
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            views: [[false, 'form']],
            res_id: 4,
        },
    ]);
});

// ----------------------------------------------------------
// Thread.openRecordActionRequest
// ----------------------------------------------------------

test('an AI session thread requests the chat action instead of a form view', () => {
    const thread = Object.assign(Object.create(Thread.prototype), {
        id: 7,
        model: 'muk_ai.session',
    });
    expect(thread.openRecordActionRequest).toEqual(CHAT_ACTION_7);
});

test('any other thread keeps requesting its own form view', () => {
    const thread = Object.assign(Object.create(Thread.prototype), {
        id: 3,
        model: 'discuss.channel',
    });
    expect(thread.openRecordActionRequest).toEqual({
        type: 'ir.actions.act_window',
        res_id: 3,
        res_model: 'discuss.channel',
        views: [[false, 'form']],
    });
});

// ----------------------------------------------------------
// MessagingMenu.onClickInboxMsg
// ----------------------------------------------------------

test('an unread AI inbox message opens the chat and is marked done', () => {
    const { instance, actions } = withActionService(MessagingMenu.prototype);
    const doneCalls = [];
    const msg = {
        thread: { id: 7, model: 'muk_ai.session' },
        setDone: () => doneCalls.push(actions.length),
    };
    instance.onClickInboxMsg(false, msg);
    expect(actions).toEqual([CHAT_ACTION_7]);
    expect(doneCalls).toEqual([1]);
});

test('an unread non-AI inbox message still routes to Discuss', () => {
    const store = { inbox: { highlightMessage: null } };
    const { instance, actions } = withActionService(MessagingMenu.prototype, { store });
    const msg = { thread: { id: 3, model: 'discuss.channel' }, setDone: () => {} };
    instance.onClickInboxMsg(false, msg);
    expect(actions).toEqual([
        {
            tag: 'mail.action_discuss',
            type: 'ir.actions.client',
            context: { active_id: 'mail.box_inbox' },
        },
    ]);
    expect(store.inbox.highlightMessage).toBe(msg);
});

test('marking an AI inbox message as read does not open the chat', () => {
    const { instance, actions } = withActionService(MessagingMenu.prototype);
    let done = false;
    const msg = {
        thread: { id: 7, model: 'muk_ai.session' },
        setDone: () => {
            done = true;
        },
    };
    instance.onClickInboxMsg(true, msg);
    expect(actions).toEqual([]);
    expect(done).toBe(true);
});
