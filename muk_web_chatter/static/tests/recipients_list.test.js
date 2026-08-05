import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { queryAll, queryOne } from '@odoo/hoot-dom';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    allowTranslations,
    contains,
    mountWithCleanup,
} from '@web/../tests/web_test_helpers';

import { RecipientsList } from '@muk_web_chatter/core/recipients_list/recipients_list';

describe.current.tags('desktop');
defineMailModels();

beforeEach(() => allowTranslations());

function makeRecipient(id, { name, email, share = false, hasUser = true } = {}) {
    return {
        id: `recipient-${id}`,
        partner_id: {
            id,
            name: name ?? `Partner ${id}`,
            email,
            main_user_id: hasUser ? { share } : undefined,
        },
    };
}

async function mountRecipientsList(recipients, internalOnly) {
    await mountWithCleanup(RecipientsList, {
        props: { thread: { followers: [], recipients }, internalOnly },
    });
}

async function mountInternalRecipientsList(followers, recipients = []) {
    await mountWithCleanup(RecipientsList, {
        props: { thread: { followers, recipients }, internalOnly: true },
    });
}

function getSummaryEntries() {
    return queryAll('span[title]').map((el) => ({
        text: el.textContent,
        title: el.getAttribute('title'),
    }));
}

test.tags('muk_web_chatter');
test('recipients summary shows the email local part and the full address as title', async () => {
    await mountRecipientsList([
        makeRecipient(1, { name: 'Alice', email: 'alice@example.com' }),
    ]);
    expect(getSummaryEntries()).toEqual([
        { text: 'alice', title: 'alice@example.com' },
    ]);
});

test.tags('muk_web_chatter');
test('recipients summary falls back to the partner name without an email', async () => {
    await mountRecipientsList([makeRecipient(1, { name: 'Alice', email: false })]);
    expect(getSummaryEntries()).toEqual([{ text: 'Alice', title: 'no email address' }]);
});

test.tags('muk_web_chatter');
test('recipients summary keeps a malformed email verbatim', async () => {
    await mountRecipientsList([makeRecipient(1, { name: 'Alice', email: 'alice' })]);
    expect(getSummaryEntries()).toEqual([{ text: 'alice', title: 'alice' }]);
});

test.tags('muk_web_chatter');
test('recipients summary escapes html in names and emails', async () => {
    await mountRecipientsList([
        makeRecipient(1, { name: '<b>Bold</b>', email: false }),
    ]);
    expect(queryOne('span[title]').innerHTML).toBe('&lt;b&gt;Bold&lt;/b&gt;');
});

test.tags('muk_web_chatter');
test('recipients summary shows no more button for three recipients', async () => {
    await mountRecipientsList([
        makeRecipient(1, { email: 'a@example.com' }),
        makeRecipient(2, { email: 'b@example.com' }),
        makeRecipient(3, { email: 'c@example.com' }),
    ]);
    expect('span[title]').toHaveCount(3);
    expect('button[title="Show all recipients"]').toHaveCount(0);
});

test.tags('muk_web_chatter');
test('recipients summary truncates to three and counts the remainder', async () => {
    await mountRecipientsList([
        makeRecipient(1, { email: 'a@example.com' }),
        makeRecipient(2, { email: 'b@example.com' }),
        makeRecipient(3, { email: 'c@example.com' }),
        makeRecipient(4, { email: 'd@example.com' }),
        makeRecipient(5, { email: 'e@example.com' }),
    ]);
    expect('span[title]').toHaveCount(3);
    expect('button[title="Show all recipients"]').toHaveCount(1);
    expect(queryOne('.text-truncate.text-muted')).toHaveText(/2 more/);
});

test.tags('muk_web_chatter');
test('recipients summary drops entries without a partner', async () => {
    await mountRecipientsList([
        makeRecipient(1, { email: 'a@example.com' }),
        { id: 'recipient-no-partner', partner_id: undefined },
    ]);
    expect('span[title]').toHaveCount(1);
});

test.tags('muk_web_chatter');
test('recipients summary keeps only internal users when internalOnly is set', async () => {
    await mountInternalRecipientsList([
        makeRecipient(1, { email: 'internal@example.com' }),
        makeRecipient(2, { email: 'portal@example.com', share: true }),
        makeRecipient(3, { email: 'nouser@example.com', hasUser: false }),
    ]);
    expect(getSummaryEntries()).toEqual([
        { text: 'internal', title: 'internal@example.com' },
    ]);
});

test.tags('muk_web_chatter');
test('internal summary reads the followers instead of the message recipients', async () => {
    await mountInternalRecipientsList(
        [makeRecipient(1, { email: 'follower@example.com' })],
        [makeRecipient(2, { email: 'recipient@example.com' })],
    );
    expect(getSummaryEntries()).toEqual([
        { text: 'follower', title: 'follower@example.com' },
    ]);
});

test.tags('muk_web_chatter');
test('recipients summary keeps every partner when internalOnly is not set', async () => {
    await mountRecipientsList(
        [
            makeRecipient(1, { email: 'internal@example.com' }),
            makeRecipient(2, { email: 'portal@example.com', share: true }),
        ],
        false,
    );
    expect('span[title]').toHaveCount(2);
});

test.tags('muk_web_chatter');
test('recipients popover lists every recipient and toggles closed', async () => {
    await mountRecipientsList([
        makeRecipient(1, { email: 'a@example.com' }),
        makeRecipient(2, { email: 'b@example.com' }),
        makeRecipient(3, { email: 'c@example.com' }),
        makeRecipient(4, { name: 'No Mail', email: false }),
    ]);
    await contains('button[title="Show all recipients"]').click();
    expect('.o_popover .text-nowrap').toHaveCount(4);
    expect(queryAll('.o_popover .text-nowrap').at(-1)).toHaveText('No Mail');
    await contains('button[title="Show all recipients"]').click();
    expect('.o_popover').toHaveCount(0);
});
