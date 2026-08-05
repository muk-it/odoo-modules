import { beforeEach, expect, test } from '@odoo/hoot';

import { allowTranslations } from '@web/../tests/web_test_helpers';

import { Composer } from '@mail/core/common/composer';

import '@muk_web_chatter/chatter/composer';

beforeEach(() => allowTranslations());

function makeComposer({ type, notifyInternalFollowers, message = null }) {
    return Object.assign(Object.create(Composer.prototype), {
        props: {
            type,
            notifyInternalFollowers,
            composer: {
                message,
                targetThread: null,
                attachments: [],
                mentionedChannels: [],
                mentionedPartners: [],
                mentionedRoles: [],
                cannedResponses: [],
            },
        },
    });
}

test.tags('muk_web_chatter');
test('internal note composer relabels the send button', async () => {
    const internal = makeComposer({ type: 'note', notifyInternalFollowers: true });
    const note = makeComposer({ type: 'note', notifyInternalFollowers: false });
    expect(internal.SEND_TEXT.toString()).toBe('Send');
    expect(note.SEND_TEXT.toString()).toBe('Log');
});

test.tags('muk_web_chatter');
test('internal note composer uses a dedicated placeholder', async () => {
    const internal = makeComposer({ type: 'note', notifyInternalFollowers: true });
    const note = makeComposer({ type: 'note', notifyInternalFollowers: false });
    expect(internal.placeholder.toString()).toBe(
        'Send a message to internal followers...',
    );
    expect(note.placeholder.toString()).toBe('');
});

test.tags('muk_web_chatter');
test('composer keeps the core labels for a message even with the flag set', async () => {
    const message = makeComposer({ type: 'message', notifyInternalFollowers: true });
    expect(message.SEND_TEXT.toString()).toBe('Send');
    expect(message.placeholder.toString()).toBe('');
});

test.tags('muk_web_chatter');
test('composer keeps the core edit label when editing a message', async () => {
    const editing = makeComposer({
        type: 'note',
        notifyInternalFollowers: false,
        message: { id: 1 },
    });
    expect(editing.SEND_TEXT.toString()).toBe('Save editing');
});

test.tags('muk_web_chatter');
test('composer forwards the internal followers flag in the post data', async () => {
    const internal = makeComposer({ type: 'note', notifyInternalFollowers: true });
    expect(internal.postData.notifyInternalFollowers).toBe(true);
    expect(internal.postData.isNote).toBe(true);
});

test.tags('muk_web_chatter');
test('composer defaults the internal followers flag to false when unset', async () => {
    const plain = makeComposer({ type: 'note', notifyInternalFollowers: undefined });
    expect(plain.postData.notifyInternalFollowers).toBe(false);
});

test.tags('muk_web_chatter');
test('composer drops the internal followers flag for a message', async () => {
    const message = makeComposer({ type: 'message', notifyInternalFollowers: true });
    expect(message.postData.notifyInternalFollowers).toBe(false);
});

test.tags('muk_web_chatter');
test('internal note carries the notification flag to the full composer', async () => {
    const internal = makeComposer({ type: 'note', notifyInternalFollowers: true });
    expect(internal.fullComposerAdditionalContext).toEqual({
        mail_notify_internal_followers: true,
    });
});

test.tags('muk_web_chatter');
test('plain note keeps the core context of the full composer', async () => {
    const note = makeComposer({ type: 'note', notifyInternalFollowers: false });
    expect(note.fullComposerAdditionalContext).toEqual({});
});
