import { expect, test } from '@odoo/hoot';

import { Thread } from '@mail/core/common/thread';

import '@muk_web_chatter/core/common/thread';

const MESSAGES = [
    { id: 1, message_type: 'comment' },
    { id: 2, message_type: 'notification' },
    { id: 3, message_type: 'user_notification' },
    { id: 4, message_type: 'comment' },
];

function makeThread({ inChatter, order = 'asc' }) {
    return Object.assign(Object.create(Thread.prototype), {
        env: { inChatter },
        resetCount: () => 0,
        state: { mountedAndLoaded: true },
        props: {
            order,
            thread: { messages: MESSAGES, phantomMessages: [] },
        },
    });
}

test.tags('muk_web_chatter');
test('the thread shows every message while the toggle is on', async () => {
    const thread = makeThread({ inChatter: { showNotificationMessages: true } });
    expect(thread.orderedMessages.map((message) => message.id)).toEqual([1, 2, 3, 4]);
});

test.tags('muk_web_chatter');
test('the thread hides both notification types while the toggle is off', async () => {
    const thread = makeThread({ inChatter: { showNotificationMessages: false } });
    expect(thread.orderedMessages.map((message) => message.id)).toEqual([1, 4]);
});

test.tags('muk_web_chatter');
test('the thread filters after the core ordering, not before', async () => {
    const thread = makeThread({
        inChatter: { showNotificationMessages: false },
        order: 'desc',
    });
    expect(thread.orderedMessages.map((message) => message.id)).toEqual([4, 1]);
});

test.tags('muk_web_chatter');
test('a thread outside a chatter keeps every message', async () => {
    const thread = makeThread({ inChatter: undefined });
    expect(thread.orderedMessages.map((message) => message.id)).toEqual([1, 2, 3, 4]);
});

test.tags('muk_web_chatter');
test('the thread leaves the core list untouched', async () => {
    const thread = makeThread({ inChatter: { showNotificationMessages: false } });
    thread.orderedMessages;
    expect(MESSAGES.map((message) => message.id)).toEqual([1, 2, 3, 4]);
});
