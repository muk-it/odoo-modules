import { expect, test } from '@odoo/hoot';

import { Store } from '@mail/core/common/store_service';

import '@muk_web_chatter/chatter/store_service';

function makeStore() {
    return Object.assign(Object.create(Store.prototype), {
        getMentionsFromText: () => ({
            partners: [],
            roles: [],
            specialMentions: [],
        }),
        fillPartnersMentionToken: () => {},
    });
}

function makeRecipient(id, { share = false, hasUser = true } = {}) {
    return {
        id: `recipient-${id}`,
        partner_id: {
            id,
            main_user_id: hasUser ? { share } : undefined,
        },
    };
}

function makeThread(recipients) {
    return {
        id: 42,
        model: 'res.partner',
        recipients,
        suggestedRecipients: [],
        additionalRecipients: [],
    };
}

function makePostData(extra) {
    return {
        attachments: [],
        cannedResponseIds: [],
        emailAddSignature: false,
        isNote: true,
        mentionedChannels: [],
        mentionedPartners: [],
        mentionedRoles: [],
        ...extra,
    };
}

async function getParams({ notifyInternalFollowers, recipients }) {
    return makeStore().getMessagePostParams({
        body: 'hello',
        postData: makePostData({ notifyInternalFollowers }),
        thread: makeThread(recipients),
    });
}

test.tags('muk_web_chatter');
test('internal note post adds non-shared follower partners as recipients', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        recipients: [makeRecipient(11), makeRecipient(12)],
    });
    expect(params.post_data.partner_ids).toEqual([11, 12]);
    expect(params.post_data.subtype_xmlid).toBe('mail.mt_note');
    expect(params.thread_id).toBe(42);
});

test.tags('muk_web_chatter');
test('internal note post skips shared portal followers', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        recipients: [
            makeRecipient(11, { share: true }),
            makeRecipient(12, { share: false }),
        ],
    });
    expect(params.post_data.partner_ids).toEqual([12]);
});

test.tags('muk_web_chatter');
test('internal note post skips followers without a user account', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        recipients: [makeRecipient(11, { hasUser: false }), makeRecipient(12)],
    });
    expect(params.post_data.partner_ids).toEqual([12]);
});

test.tags('muk_web_chatter');
test('internal note post leaves the payload untouched without any internal follower', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        recipients: [makeRecipient(11, { share: true })],
    });
    expect(params.post_data.partner_ids).toBe(undefined);
});

test.tags('muk_web_chatter');
test('internal note post handles a thread without recipients', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        recipients: undefined,
    });
    expect(params.post_data.partner_ids).toBe(undefined);
});

test.tags('muk_web_chatter');
test('plain note post does not add any follower as recipient', async () => {
    const params = await getParams({
        notifyInternalFollowers: false,
        recipients: [makeRecipient(11), makeRecipient(12)],
    });
    expect(params.post_data.partner_ids).toBe(undefined);
});

test.tags('muk_web_chatter');
test('internal note post merges with mentioned partners without duplicating', async () => {
    const store = Object.assign(makeStore(), {
        getMentionsFromText: () => ({
            partners: [{ id: 11 }],
            roles: [],
            specialMentions: [],
        }),
    });
    const params = await store.getMessagePostParams({
        body: 'hello @Internal',
        postData: makePostData({ notifyInternalFollowers: true }),
        thread: makeThread([makeRecipient(11), makeRecipient(12)]),
    });
    expect(params.post_data.partner_ids).toEqual([11, 12]);
});
