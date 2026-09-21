import { beforeEach, expect, test } from '@odoo/hoot';

import { allowTranslations } from '@web/../tests/web_test_helpers';

import { RecipientsInput } from '@mail/core/web/recipients_input';

import '@muk_web_chatter/core/web/recipients_input';

beforeEach(() => allowTranslations());

function makeFollower(id, email, share) {
    return {
        partner_id: {
            id,
            email,
            name: `Partner ${id}`,
            main_user_id: share === undefined ? false : { share },
        },
    };
}

function makeInput({ notifyInternalFollowers, followers = [], recipientType = 'to' }) {
    return Object.assign(Object.create(RecipientsInput.prototype), {
        env: { inChatter: { notifyInternalFollowers } },
        props: {
            recipientType,
            thread: {
                followers,
                recipients: [],
                recipientsCount: followers.length,
                suggestedRecipients: [],
                additionalRecipients: [],
                getPersonaName: (partner) => partner.name,
            },
        },
    });
}

test.tags('muk_web_chatter');
test('the badge counts only the internal followers of an internal note', async () => {
    const input = makeInput({
        notifyInternalFollowers: true,
        followers: [
            makeFollower(1, 'one@example.com', false),
            makeFollower(2, 'two@example.com', true),
            makeFollower(3, 'three@example.com'),
        ],
    });
    expect(input.internalFollowers).toHaveLength(1);
    expect(input.followersBadge.text.toString()).toBe('1 Internal Follower');
    expect(input.followersBadge.tooltip).toBe('Partner 1 <one@example.com>');
});

test.tags('muk_web_chatter');
test('the badge falls back to the core one outside an internal note', async () => {
    const input = makeInput({
        notifyInternalFollowers: false,
        followers: [makeFollower(1, 'one@example.com', false)],
    });
    expect(input.followersBadge.text.toString()).toBe('1 Follower');
});

test.tags('muk_web_chatter');
test('the badge hides when an internal note has no internal follower', async () => {
    const input = makeInput({
        notifyInternalFollowers: true,
        followers: [makeFollower(2, 'two@example.com', true)],
    });
    expect(input.showFollowersBadge).toBe(false);
    expect(
        makeInput({
            notifyInternalFollowers: false,
            followers: [makeFollower(2, 'two@example.com', true)],
        }).showFollowersBadge,
    ).toBe(true);
});

test.tags('muk_web_chatter');
test('the badge never shows on the cc row', async () => {
    const input = makeInput({
        notifyInternalFollowers: true,
        recipientType: 'cc',
        followers: [makeFollower(1, 'one@example.com', false)],
    });
    expect(input.showFollowersBadge).toBe(false);
});

test.tags('muk_web_chatter');
test('an internal note drops the suggested recipients from its tags', async () => {
    const input = makeInput({ notifyInternalFollowers: true });
    const suggested = { partner_id: 5, name: 'Customer', recipient_type: 'to' };
    const added = { partner_id: 6, name: 'Colleague', recipient_type: 'to' };
    Object.assign(input.props.thread, {
        suggestedRecipients: [suggested],
        additionalRecipients: [added],
    });
    expect(input.getAllMailThreadRecipients()).toEqual([added]);
    expect(input.getTagsFromMailThread().map((tag) => tag.resId)).toEqual([6]);
});

test.tags('muk_web_chatter');
test('a message keeps the suggested recipients in its tags', async () => {
    const input = makeInput({ notifyInternalFollowers: false });
    const suggested = { partner_id: 5, name: 'Customer', recipient_type: 'to' };
    Object.assign(input.props.thread, { suggestedRecipients: [suggested] });
    expect(input.getAllMailThreadRecipients()).toEqual([suggested]);
    expect(input.getTagsFromMailThread().map((tag) => tag.resId)).toEqual([5]);
});

test.tags('muk_web_chatter');
test('the placeholder names the internal followers', async () => {
    const input = makeInput({ notifyInternalFollowers: true });
    input.props.placeholder = 'Followers only';
    expect(input.getPlaceholder().toString()).toBe('Internal followers only');
});
