/** @odoo-module **/

import {
    allOptionalGranted,
    buildConsentState,
    isWithdrawal,
    keptContextualServices,
    matchStoredCookies,
} from '@muk_website_cookies_consent/snippets/cookies_banner/consent_state';

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

QUnit.module('muk_website_cookies_consent', {}, function () {
    QUnit.module('the payload one decision stores');

    QUnit.test(
        'the payload carries the disclosure the visitor was actually shown',
        function (assert) {
            const state = decision();
            assert.strictEqual(state.pv, 3);
            assert.strictEqual(state.rh, 'abc123');
            assert.strictEqual(state.lang, 'de_DE');
            assert.strictEqual(state.v, 1);
        },
    );

    QUnit.test(
        'the payload keeps the first consent timestamp and stamps the latest',
        function (assert) {
            const state = decision({ previous: { ts: 1600000000, ans: 1 } });
            assert.strictEqual(state.ts, 1600000000);
            assert.strictEqual(state.rts, 1700000000);
        },
    );

    QUnit.test(
        'the payload starts its own timestamp when nothing is in force',
        function (assert) {
            assert.strictEqual(decision().ts, 1700000000);
        },
    );

    QUnit.test('the payload sorts services and never repeats one', function (assert) {
        const state = decision({
            purposeServices: ['linkedin', 'ga4'],
            extraServices: ['ga4'],
        });
        assert.deepEqual(state.svcs, ['ga4', 'linkedin']);
    });

    QUnit.module('answering the banner');

    QUnit.test('a decision in the dialog answers the banner', function (assert) {
        assert.strictEqual(decision({ source: 'banner' }).ans, 1);
    });

    QUnit.test('allowing an embed in place answers nothing', function (assert) {
        assert.strictEqual(decision({ source: 'embed' }).ans, 0);
    });

    QUnit.test('an answer already given still stands', function (assert) {
        const state = decision({ source: 'embed', previous: { ans: 1 } });
        assert.strictEqual(state.ans, 1);
    });

    QUnit.module('services granted on an embed itself');

    QUnit.test(
        'an embed grant survives a later decision in the dialog',
        function (assert) {
            const state = decision({
                categories: ['essential', 'analytics'],
                previous: { svcs: ['youtube'], ans: 1 },
            });
            assert.deepEqual(state.svcs, ['youtube']);
        },
    );

    QUnit.test(
        'an embed grant is taken back by refusing everything',
        function (assert) {
            const state = decision({
                action: 'reject_all',
                previous: { svcs: ['youtube'], ans: 1 },
            });
            assert.deepEqual(state.svcs, []);
        },
    );

    QUnit.test('an embed grant is taken back by withdrawing', function (assert) {
        const state = decision({
            action: 'withdraw',
            previous: { svcs: ['youtube'], ans: 1 },
        });
        assert.deepEqual(state.svcs, []);
    });

    QUnit.test(
        'an embed grant cannot be resurrected once its payload is not honoured',
        function (assert) {
            const state = decision({ previous: null, source: 'embed' });
            assert.deepEqual(state.svcs, []);
            assert.strictEqual(state.ans, 0);
        },
    );

    QUnit.test(
        'a service riding on a purpose is not kept as a contextual grant',
        function (assert) {
            const kept = keptContextualServices({ svcs: ['linkedin', 'youtube'] }, [
                'youtube',
            ]);
            assert.deepEqual(kept, ['youtube']);
        },
    );

    QUnit.test('nothing is kept when nothing was in force', function (assert) {
        assert.deepEqual(keptContextualServices(null, ['youtube']), []);
    });

    QUnit.module('what counts as taking consent away');

    QUnit.test('refusing all and withdrawing take consent away', function (assert) {
        assert.strictEqual(isWithdrawal('reject_all'), true);
        assert.strictEqual(isWithdrawal('withdraw'), true);
    });

    QUnit.test('accepting and choosing do not take consent away', function (assert) {
        assert.strictEqual(isWithdrawal('accept_all'), false);
        assert.strictEqual(isWithdrawal('custom'), false);
    });

    QUnit.module("core's single optional flag");

    QUnit.test(
        'the optional flag is only claimed when every purpose was granted',
        function (assert) {
            const offered = ['essential', 'analytics', 'marketing'];
            assert.strictEqual(allOptionalGranted(offered, offered), true);
        },
    );

    QUnit.test(
        'the optional flag is withheld when one purpose was refused',
        function (assert) {
            const offered = ['essential', 'analytics', 'marketing'];
            assert.strictEqual(
                allOptionalGranted(offered, ['essential', 'analytics']),
                false,
            );
        },
    );

    QUnit.test(
        'the optional flag ignores the strictly necessary purpose',
        function (assert) {
            assert.strictEqual(allOptionalGranted(['essential'], []), true);
        },
    );

    QUnit.module('matching the cookies a declaration covers');

    QUnit.test('a pattern reaches the family it names', function (assert) {
        assert.deepEqual(matchStoredCookies(STORED_COOKIES, '^_ga'), [
            '_ga',
            '_ga_ABC',
        ]);
    });

    QUnit.test(
        'a pattern is anchored, so it cannot reach past its own purpose',
        function (assert) {
            assert.deepEqual(matchStoredCookies(STORED_COOKIES, '_ga'), [
                '_ga',
                '_ga_ABC',
            ]);
        },
    );

    QUnit.test(
        'an unparseable pattern matches nothing instead of throwing',
        function (assert) {
            assert.deepEqual(matchStoredCookies(STORED_COOKIES, '^(unclosed'), []);
        },
    );

    QUnit.test('an empty jar matches nothing', function (assert) {
        assert.deepEqual(matchStoredCookies('', '^_ga'), []);
    });
});
