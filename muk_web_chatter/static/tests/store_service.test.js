import { expect, test } from '@odoo/hoot';

import { Store } from '@mail/core/common/store_service';

import '@muk_web_chatter/core/common/store_service';

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

async function getParams({
    notifyInternalFollowers,
    additionalRecipients = [],
    isCcEnabled = false,
}) {
    return makeStore().getMessagePostParams({
        body: 'hello',
        postData: makePostData({ notifyInternalFollowers, isCcEnabled }),
        thread: {
            id: 42,
            model: 'res.partner',
            suggestedRecipients: [],
            additionalRecipients,
        },
    });
}

test.tags('muk_web_chatter');
test('internal note post asks the server to notify the internal followers', async () => {
    const params = await getParams({ notifyInternalFollowers: true });
    expect(params.context.mail_notify_internal_followers).toBe(true);
    expect(params.post_data.subtype_xmlid).toBe('mail.mt_note');
    expect(params.post_data.partner_ids).toBe(undefined);
    expect(params.thread_id).toBe(42);
});

test.tags('muk_web_chatter');
test('internal note post carries the partners tagged on it', async () => {
    const params = await getParams({
        notifyInternalFollowers: true,
        additionalRecipients: [
            { persona: { id: 7 }, recipient_type: 'to' },
            { email: 'guest@example.com', recipient_type: 'to' },
        ],
    });
    expect(params.post_data.subtype_xmlid).toBe('mail.mt_note');
    expect(params.post_data.partner_ids).toEqual([7]);
    expect(params.post_data.partner_emails).toEqual(['guest@example.com']);
});

test.tags('muk_web_chatter');
test('internal note post keeps the cc recipients out until cc is enabled', async () => {
    const recipients = [{ persona: { id: 9 }, recipient_type: 'cc' }];
    const without = await getParams({
        notifyInternalFollowers: true,
        additionalRecipients: recipients,
    });
    expect(without.post_data.partner_cc_ids).toBe(undefined);
    const withCc = await getParams({
        notifyInternalFollowers: true,
        additionalRecipients: recipients,
        isCcEnabled: true,
    });
    expect(withCc.post_data.partner_cc_ids).toEqual([9]);
});

test.tags('muk_web_chatter');
test('plain note post leaves the context and the recipients untouched', async () => {
    const params = await getParams({
        notifyInternalFollowers: false,
        additionalRecipients: [{ persona: { id: 7 }, recipient_type: 'to' }],
    });
    expect(params.context).toBe(undefined);
    expect(params.post_data.partner_ids).toBe(undefined);
});
