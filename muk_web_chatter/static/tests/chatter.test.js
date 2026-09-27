import { describe, expect, test } from '@odoo/hoot';

import { browser } from '@web/core/browser/browser';
import { mockService, onRpc, patchWithCleanup } from '@web/../tests/web_test_helpers';

import {
    click,
    contains,
    defineMailModels,
    insertText,
    onRpcBefore,
    openFormView,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';

describe.current.tags('desktop');
defineMailModels();

async function createFollowedRecord() {
    const pyEnv = await startServer();
    const [colleagueId, portalId, contactId, customerId] = pyEnv['res.partner'].create([
        { name: 'Colleague', email: 'colleague@example.com' },
        { name: 'Portal', email: 'portal@example.com' },
        { name: 'Contact', email: 'contact@example.com' },
        { name: 'Customer', email: 'customer@example.com' },
    ]);
    pyEnv['res.users'].create([
        { partner_id: colleagueId, share: false },
        { partner_id: portalId, share: true },
    ]);
    patchWithCleanup(pyEnv['res.fake'], {
        _message_get_suggested_recipients() {
            return super
                ._message_get_suggested_recipients(...arguments)
                .map((recipient) => ({ partner_id: false, ...recipient }));
        },
    });
    const recordId = pyEnv['res.fake'].create({
        email_cc: 'lead@example.com',
        partner_ids: [customerId],
    });
    pyEnv['mail.followers'].create(
        [colleagueId, portalId, contactId].map((partnerId) => ({
            partner_id: partnerId,
            is_active: true,
            res_id: recordId,
            res_model: 'res.fake',
        })),
    );
    return { pyEnv, recordId };
}

function stepMessagePost() {
    onRpcBefore('/mail/message/post', ({ context, post_data }) =>
        expect.step({
            notify: context?.mail_notify_internal_followers ?? false,
            subtype: post_data.subtype_xmlid,
            partners: post_data.partner_ids ?? [],
            emails: post_data.partner_emails ?? [],
            ccPartners: post_data.partner_cc_ids ?? [],
        }),
    );
}

function note(notify, { partners = [], emails = [], ccPartners = [] } = {}) {
    return { notify, subtype: 'mail.mt_note', partners, emails, ccPartners };
}

async function postNote(body) {
    await insertText('.o-mail-Composer-input', body);
    await click('.o-mail-Composer-send:enabled');
    await contains(`.o-mail-Message-body:text(${body})`);
}

async function tagRecipient(email, input = '.o-mail-RecipientsInput input') {
    await insertText(input, email);
    await click(`.dropdown-item:text(Create ${email})`);
}

test.tags('muk_web_chatter');
test('an internal note addresses the internal followers only', async () => {
    const { recordId } = await createFollowedRecord();
    stepMessagePost();
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await contains(
        ".o-mail-Composer-input[placeholder='Send a message to internal followers...']",
    );
    await contains(
        '.o-mail-RecipientsInput .o_tag_badge_text:text(1 Internal Follower)',
    );
    await contains('.o-mail-RecipientsInput .o_tag_badge_text', { count: 1 });
    await contains('.o-mail-Composer-send:text(Send)');
    await postNote('Internal update');
    await expect.waitForSteps([note(true)]);
});

test.tags('muk_web_chatter');
test('an internal note hides the badge without internal followers', async () => {
    const pyEnv = await startServer();
    const recordId = pyEnv['res.fake'].create({});
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await contains(
        ".o-mail-RecipientsInput input[placeholder='Internal followers only']",
    );
    await contains('.o-mail-RecipientsInput .o_tag_badge_text', { count: 0 });
});

test.tags('muk_web_chatter');
test('an internal note sends the partners tagged on it', async () => {
    const { pyEnv, recordId } = await createFollowedRecord();
    const supplierId = pyEnv['res.partner'].create({
        name: 'Supplier',
        email: 'supplier@example.com',
    });
    stepMessagePost();
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await tagRecipient('supplier@example.com');
    await contains('.o-mail-RecipientsInput .o_tag_badge_text:text(Supplier)');
    await click('.btn:text(Cc)');
    await tagRecipient('cc@example.com', "input[placeholder='Cc recipients']");
    await postNote('Internal update');
    const [ccId] = pyEnv['res.partner'].search([['email', '=', 'cc@example.com']]);
    await expect.waitForSteps([
        note(true, { partners: [supplierId], ccPartners: [ccId] }),
    ]);
});

test.tags('muk_web_chatter');
test('an internal note keeps an address typed without a partner', async () => {
    const { recordId } = await createFollowedRecord();
    onRpc('/mail/partner/from_email', () => []);
    stepMessagePost();
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await tagRecipient('guest@example.com');
    await contains('.o-mail-RecipientsInput .o_tag_badge_text:text(guest@example.com)');
    await contains('.o-mail-RecipientsInput .o_tag_badge_text:text(lead@example.com)', {
        count: 0,
    });
    await postNote('Internal update');
    await expect.waitForSteps([note(true, { emails: ['guest@example.com'] })]);
});

test.tags('muk_web_chatter');
test('the note and external buttons keep the core composers', async () => {
    const { recordId } = await createFollowedRecord();
    stepMessagePost();
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await click('button:text(Note)');
    await contains('.o-mail-RecipientsInput', { count: 0 });
    await contains('.o-mail-Composer-send:text(Log)');
    await postNote('Plain note');
    await click('button:text(External)');
    await contains('.o-mail-RecipientsInput .o_tag_badge_text:text(Customer)');
    await contains('.o-mail-RecipientsInput .o_tag_badge_text:text(lead@example.com)');
    await expect.waitForSteps([note(false)]);
});

test.tags('muk_web_chatter');
test('clicking the active internal button closes the composer', async () => {
    const pyEnv = await startServer();
    const recordId = pyEnv['res.fake'].create({});
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await contains('.o-mail-Composer');
    await click('button:text(Internal)');
    await contains('.o-mail-Composer', { count: 0 });
});

test.tags('muk_web_chatter');
test('the full composer of an internal note notifies the internal followers', async () => {
    const { recordId } = await createFollowedRecord();
    mockService('action', {
        async doAction(action) {
            if (action?.res_model === 'res.fake') {
                return super.doAction(...arguments);
            }
            expect.step(action.context.mail_notify_internal_followers ?? false);
        },
    });
    await start();
    await openFormView('res.fake', recordId);
    await click('button:text(Internal)');
    await click("button[title='Open Full Composer']");
    await expect.waitForSteps([true]);
    await click('button:text(Note)');
    await click("button[title='Open Full Composer']");
    await expect.waitForSteps([false]);
});

test.tags('muk_web_chatter');
test('the notifications toggle hides notification messages and remembers it', async () => {
    const pyEnv = await startServer();
    const recordId = pyEnv['res.fake'].create({});
    pyEnv['mail.message'].create(
        [
            ['A comment', 'comment'],
            ['Stage changed', 'notification'],
        ].map(([body, messageType]) => ({
            body,
            message_type: messageType,
            model: 'res.fake',
            res_id: recordId,
        })),
    );
    await start();
    await openFormView('res.fake', recordId);
    await contains('.o-mail-Message', { count: 2 });
    await click("button[title='Show/Hide Notifications']");
    await contains('.o-mail-Message', { count: 1 });
    await contains('.o-mail-Message-body:text(A comment)');
    await openFormView('res.fake', recordId);
    await contains('.o-mail-Message', { count: 1 });
    await click("button[title='Show/Hide Notifications']");
    await contains('.o-mail-Message', { count: 2 });
    expect(browser.localStorage.getItem('muk_web_chatter.notifications')).toBe('true');
});
