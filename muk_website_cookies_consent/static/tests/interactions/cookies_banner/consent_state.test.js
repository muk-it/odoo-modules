import { describe, expect, test } from '@odoo/hoot';

import {
    allOptionalGranted,
    buildConsentState,
    isWithdrawal,
    keptContextualServices,
    matchStoredCookies,
} from '@muk_website_cookies_consent/interactions/cookies_banner/consent_state';

describe.current.tags('muk_website_cookies_consent');

const STORED_COOKIES = '_ga=1; _ga_ABC=2; frontend_lang=en_US; my_ga=3';

/**
 * Build the payload a decision would store, varying one thing at a time.
 * @param {object} [overrides] the arguments that differ from a plain decision
 * @returns {object} the payload the banner would write
 */
function decision(overrides = {}) {
    return buildConsentState({
        categories: ['essential'],
        action: 'custom',
        source: 'banner',
        previous: null,
        purposeServices: [],
        contextualNames: ['youtube', 'vimeo'],
        disclosure: { pv: '3', rh: 'abc123', lang: 'de_DE' },
        now: 1700000000,
        uid: 'uid-1',
        ...overrides,
    });
}

// ----------------------------------------------------------
// The payload one decision stores
// ----------------------------------------------------------

test('the payload carries the disclosure the visitor was actually shown', () => {
    const state = decision();
    expect(state.pv).toBe(3);
    expect(state.rh).toBe('abc123');
    expect(state.lang).toBe('de_DE');
    expect(state.v).toBe(1);
});

test('the payload keeps the first consent timestamp and stamps the latest', () => {
    const state = decision({ previous: { ts: 1600000000, ans: 1 } });
    expect(state.ts).toBe(1600000000);
    expect(state.rts).toBe(1700000000);
});

test('the payload starts its own timestamp when nothing is in force', () => {
    expect(decision().ts).toBe(1700000000);
});

test('the payload sorts services and never repeats one', () => {
    const state = decision({
        purposeServices: ['linkedin', 'ga4'],
        extraServices: ['ga4'],
    });
    expect(state.svcs).toEqual(['ga4', 'linkedin']);
});

// ----------------------------------------------------------
// Answering the banner
// ----------------------------------------------------------

test('a decision in the dialog answers the banner', () => {
    expect(decision({ source: 'banner' }).ans).toBe(1);
});

test('allowing an embed in place answers nothing', () => {
    expect(decision({ source: 'embed' }).ans).toBe(0);
});

test('an answer already given still stands', () => {
    const state = decision({ source: 'embed', previous: { ans: 1 } });
    expect(state.ans).toBe(1);
});

// ----------------------------------------------------------
// Services granted on an embed itself
// ----------------------------------------------------------

test('an embed grant survives a later decision in the dialog', () => {
    const state = decision({
        categories: ['essential', 'analytics'],
        previous: { svcs: ['youtube'], ans: 1 },
    });
    expect(state.svcs).toEqual(['youtube']);
});

test('an embed grant is taken back by refusing everything', () => {
    const state = decision({
        action: 'reject_all',
        previous: { svcs: ['youtube'], ans: 1 },
    });
    expect(state.svcs).toEqual([]);
});

test('an embed grant is taken back by withdrawing', () => {
    const state = decision({
        action: 'withdraw',
        previous: { svcs: ['youtube'], ans: 1 },
    });
    expect(state.svcs).toEqual([]);
});

test('an embed grant cannot be resurrected once its payload is not honoured', () => {
    const state = decision({ previous: null, source: 'embed' });
    expect(state.svcs).toEqual([]);
    expect(state.ans).toBe(0);
});

test('a service riding on a purpose is not kept as a contextual grant', () => {
    const kept = keptContextualServices({ svcs: ['linkedin', 'youtube'] }, ['youtube']);
    expect(kept).toEqual(['youtube']);
});

test('nothing is kept when nothing was in force', () => {
    expect(keptContextualServices(null, ['youtube'])).toEqual([]);
});

// ----------------------------------------------------------
// What counts as taking consent away
// ----------------------------------------------------------

test('refusing all and withdrawing take consent away', () => {
    expect(isWithdrawal('reject_all')).toBe(true);
    expect(isWithdrawal('withdraw')).toBe(true);
});

test('accepting and choosing do not take consent away', () => {
    expect(isWithdrawal('accept_all')).toBe(false);
    expect(isWithdrawal('custom')).toBe(false);
});

// ----------------------------------------------------------
// Core's single optional flag
// ----------------------------------------------------------

test('the optional flag is only claimed when every purpose was granted', () => {
    const offered = ['essential', 'analytics', 'marketing'];
    expect(allOptionalGranted(offered, offered)).toBe(true);
});

test('the optional flag is withheld when one purpose was refused', () => {
    const offered = ['essential', 'analytics', 'marketing'];
    expect(allOptionalGranted(offered, ['essential', 'analytics'])).toBe(false);
});

test('the optional flag ignores the strictly necessary purpose', () => {
    expect(allOptionalGranted(['essential'], [])).toBe(true);
});

// ----------------------------------------------------------
// Matching the cookies a declaration covers
// ----------------------------------------------------------

test('a pattern reaches the family it names', () => {
    expect(matchStoredCookies(STORED_COOKIES, '^_ga')).toEqual(['_ga', '_ga_ABC']);
});

test('a pattern is anchored, so it cannot reach past its own purpose', () => {
    expect(matchStoredCookies(STORED_COOKIES, '_ga')).toEqual(['_ga', '_ga_ABC']);
});

test('an unparseable pattern matches nothing instead of throwing', () => {
    expect(matchStoredCookies(STORED_COOKIES, '^(unclosed')).toEqual([]);
});

test('an empty jar matches nothing', () => {
    expect(matchStoredCookies('', '^_ga')).toEqual([]);
});
