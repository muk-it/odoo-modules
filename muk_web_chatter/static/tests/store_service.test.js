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

async function getParams(notifyInternalFollowers) {
    return makeStore().getMessagePostParams({
        body: 'hello',
        postData: makePostData({ notifyInternalFollowers }),
        thread: {
            id: 42,
            model: 'res.partner',
            suggestedRecipients: [],
            additionalRecipients: [],
        },
    });
}

test.tags('muk_web_chatter');
test('internal note post asks the server to notify the internal followers', async () => {
    const params = await getParams(true);
    expect(params.context.mail_notify_internal_followers).toBe(true);
    expect(params.post_data.subtype_xmlid).toBe('mail.mt_note');
    expect(params.post_data.partner_ids).toBe(undefined);
    expect(params.thread_id).toBe(42);
});

test.tags('muk_web_chatter');
test('plain note post leaves the context untouched', async () => {
    const params = await getParams(false);
    expect(params.context).toBe(undefined);
});
