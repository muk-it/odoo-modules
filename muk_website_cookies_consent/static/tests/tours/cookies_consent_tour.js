/** @odoo-module **/

import { registry } from '@web/core/registry';

// ----------------------------------------------------------
// Helper
// ----------------------------------------------------------

/**
 * Read the decision the browser is holding.
 * @returns {object | null} the stored payload, or null when there is none
 */
function readConsent() {
    const match = document.cookie.match(/(^|; )muk_cookie_consent=([^;]+)/);
    if (!match) {
        return null;
    }
    try {
        return JSON.parse(decodeURIComponent(match[2]));
    } catch {
        return null;
    }
}

/**
 * List the purpose codes the preference centre puts to the visitor.
 * @returns {string[]} the codes of the toggles on offer
 */
function offeredCodes() {
    return [...document.querySelectorAll("input[name='muk_cookie_category']")].map(
        (el) => el.value,
    );
}

/**
 * Fail unless the stored decision granted exactly these purposes.
 * @param {string[]} expected the purpose codes the decision has to hold
 */
function assertGranted(expected) {
    const state = readConsent();
    if (!state) {
        throw new Error('No decision was stored.');
    }
    const granted = [...state.cats].sort().join(',');
    const wanted = [...expected].sort().join(',');
    if (granted !== wanted) {
        throw new Error(`Granted "${granted}" but expected "${wanted}".`);
    }
}

let scrollerEl = null;
let readingPosition = 0;

/**
 * Remember which element the page scrolls, and make it long enough to scroll.
 *
 * Remembered rather than derived again later: the lock hides the scroller's
 * overflow, which is exactly what the detection keys on.
 *
 * @returns {HTMLElement} the scroller the visitor moves
 */
function findTheScroller() {
    const wrapEl = document.getElementById('wrapwrap');
    const overflow = wrapEl && getComputedStyle(wrapEl).overflowY;
    scrollerEl = overflow === 'auto' || overflow === 'scroll' ? wrapEl : null;
    const contentEl = scrollerEl
        ? scrollerEl.querySelector('#wrap') || scrollerEl.firstElementChild
        : document.body;
    contentEl.style.minHeight = '3000px';
    scrollerEl = scrollerEl || document.scrollingElement;
    return scrollerEl;
}

// ----------------------------------------------------------
// Tours
// ----------------------------------------------------------

registry.category('web_tour.tours').add('muk_cookies_reject_all', {
    url: '/',
    steps: () => [
        {
            content: 'Refuse all is offered on the first layer',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Refusing grants nothing beyond the strictly necessary',
            trigger: 'body',
            in_modal: false,
            run: () => {
                assertGranted(['essential']);
                if (readConsent().svcs.length) {
                    throw new Error(
                        'A refusal recorded a service as granted: ' +
                            `"${readConsent().svcs.join(', ')}".`,
                    );
                }
            },
        },
    ],
});

registry.category('web_tour.tours').add('muk_cookies_accept_all', {
    url: '/',
    steps: () => [
        {
            content: 'Accept every purpose from the first layer',
            trigger: '#website_cookies_bar .mk_cookies_accept_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content:
                'Accepting all grants every purpose the banner offered, however ' +
                'many the registry currently makes that',
            trigger: 'body',
            in_modal: false,
            run: () => assertGranted(offeredCodes()),
        },
    ],
});

registry.category('web_tour.tours').add('muk_cookies_customise', {
    url: '/',
    steps: () => [
        {
            content: 'Open the preference centre',
            trigger: '#website_cookies_bar #muk_cookies_customize',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'The strictly necessary toggle cannot be turned off',
            trigger: '#muk_cookie_cat_essential:disabled:checked',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Statistics starts off, as consent may never be pre-ticked',
            trigger: '#muk_cookie_cat_analytics:not(:checked)',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Marketing is left alone',
            trigger: '#muk_cookie_cat_marketing:not(:checked)',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Save the selection',
            trigger: '#muk_cookies_save',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Only the chosen purpose is granted',
            trigger: 'body',
            in_modal: false,
            run: () => assertGranted(['essential', 'analytics']),
        },
    ],
});

registry.category('web_tour.tours').add('muk_cookies_embed', {
    url: '/muk-cookies-embed',
    steps: () => [
        {
            content: 'Refuse everything optional',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'The refused embed still names its provider',
            trigger: '.mk_cookies_placeholder .mk_cookies_allow_embed',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: 'body:not(:has(.mk_cookies_placeholder))',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'The embed is released, and nothing is left covering it',
            trigger: 'body',
            in_modal: false,
            run: () => {
                const iframeEl = document.querySelector('.media_iframe_video iframe');
                if (!iframeEl.src.includes('youtube.com')) {
                    throw new Error('The allowed embed was not restored.');
                }
                if (iframeEl.classList.contains('d-none')) {
                    throw new Error('The allowed embed is still hidden.');
                }
                if (document.querySelector('.mk_cookies_placeholder')) {
                    throw new Error('A placeholder outlived the service it asked for.');
                }
            },
        },
        {
            content:
                'One embed grants that service, and no purpose beyond the necessary',
            trigger: 'body',
            in_modal: false,
            run: () => {
                assertGranted(['essential']);
                if (!readConsent().svcs.includes('youtube')) {
                    throw new Error('The service the visitor allowed was not stored.');
                }
                if (!readConsent().ans) {
                    throw new Error('The refusal that came first was undone.');
                }
            },
        },
        {
            content: 'Come back to the choice, to decide again with the embed allowed',
            trigger: '.mk_cookies_footer .mk_cookies_reopen',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Open the preference centre',
            trigger: '#website_cookies_bar #muk_cookies_customize',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Grant statistics',
            trigger: '#muk_cookie_cat_analytics:not(:checked)',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Save the selection',
            trigger: '#muk_cookies_save',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Deciding in the dialog leaves the embed the visitor allowed',
            trigger: 'body',
            in_modal: false,
            run: () => {
                assertGranted(['essential', 'analytics']);
                if (!readConsent().svcs.includes('youtube')) {
                    throw new Error('A later decision revoked an allowed embed.');
                }
            },
        },
        {
            content: 'Refusing everything does take the embed back',
            trigger: '.mk_cookies_footer .mk_cookies_reopen',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Refuse all from the reopened banner',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'A refusal clears the embeds allowed in place',
            trigger: 'body',
            in_modal: false,
            run: () => {
                assertGranted(['essential']);
                if (readConsent().svcs.length) {
                    throw new Error('Refusing everything left a service granted.');
                }
            },
        },
    ],
});

registry.category('web_tour.tours').add('muk_cookies_clearing', {
    url: '/',
    steps: () => [
        {
            content: 'Arrive carrying cookies a refusal has to take away',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: () => {
                document.cookie = '_ga=GA1.1.deadbeef;path=/';
                document.cookie = '_ga_ABC123=GS1.1.session;path=/';
                document.cookie = '_gid=GA1.2.cafe;path=/';
                document.cookie = 'frontend_lang=en_US;path=/';
                if (!document.cookie.includes('_ga=')) {
                    throw new Error('The browser under test did not keep the cookie.');
                }
            },
        },
        {
            content: 'Refuse everything optional',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'The refused purposes lose their declared cookies',
            trigger: 'body',
            in_modal: false,
            run: () => {
                const left = ['_ga', '_gid', '_ga_ABC123'].filter((name) =>
                    document.cookie.match(new RegExp(`(^|; )${name}=`)),
                );
                if (left.length) {
                    throw new Error(
                        `Refusing left ${left.join(
                            ', ',
                        )} in place, so it took nothing away.`,
                    );
                }
            },
        },
        {
            content:
                'Including the per-property names only a declared pattern could reach',
            trigger: 'body',
            in_modal: false,
            run: () => {
                if (document.cookie.includes('_ga_ABC123')) {
                    throw new Error('A pattern-declared cookie outlived the refusal.');
                }
                if (!document.cookie.includes('frontend_lang')) {
                    throw new Error(
                        'A strictly necessary cookie was cleared, which refusing must not do.',
                    );
                }
            },
        },
    ],
});

registry.category('web_tour.tours').add('muk_cookies_layers', {
    url: '/',
    steps: () => [
        {
            content: 'The way back to the choice is offered in the footer',
            trigger: '.mk_cookies_footer .mk_cookies_reopen',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Read part way down a page long enough to scroll',
            trigger: 'body',
            in_modal: false,
            run: () => {
                findTheScroller().scrollTop = 400;
                readingPosition = Math.round(scrollerEl.scrollTop);
                if (!readingPosition) {
                    throw new Error('The page under test does not scroll.');
                }
            },
        },
        {
            content: 'Open the preference centre',
            trigger: '#website_cookies_bar #muk_cookies_customize',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'A layer that claims to block the page stops it scrolling',
            trigger: 'body.mk_cookies_locked',
            in_modal: false,
            run: () => {
                const held =
                    scrollerEl === document.scrollingElement
                        ? document.body.style.top === `-${readingPosition}px`
                        : getComputedStyle(scrollerEl).overflowY === 'hidden';
                if (!held) {
                    throw new Error(
                        'The page can still be scrolled behind the dialog.',
                    );
                }
                if (Math.round(scrollerEl.scrollTop) !== readingPosition) {
                    throw new Error('The page was not held where the visitor left it.');
                }
            },
        },
        {
            content: 'Leave the layer again',
            trigger: '#muk_cookies_back',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'And closing it puts them back where they were reading',
            trigger: 'body:not(.mk_cookies_locked)',
            in_modal: false,
            run: () => {
                if (Math.abs(scrollerEl.scrollTop - readingPosition) > 2) {
                    throw new Error(
                        `Closing the dialog moved the page to ${scrollerEl.scrollTop}.`,
                    );
                }
                scrollerEl.scrollTop = 0;
            },
        },
        {
            content: 'Open the preference centre once more',
            trigger: '#website_cookies_bar #muk_cookies_customize',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'The detail view takes over and becomes its own dialog',
            trigger: '#website_cookies_bar .modal.mk_cookies_expanded',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Its heading labels the dialog',
            trigger:
                "#website_cookies_bar .modal[aria-labelledby='muk_cookies_prefs_title']",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Covering the page is where claiming modality becomes true',
            trigger: "#website_cookies_bar .modal[aria-modal='true']",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Both choices are offered here too, at equal weight',
            trigger:
                "#website_cookies_bar [data-layer='preferences'] .mk_cookies_reject_all",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Go back to the first layer',
            trigger: '#muk_cookies_back',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'The first layer is shown again',
            trigger: "#website_cookies_bar [data-layer='notice']:not(.d-none)",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'And the dialog is labelled by its own heading again',
            trigger:
                "#website_cookies_bar .modal[aria-labelledby='muk_cookies_title']:not(.mk_cookies_expanded)",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'The notice claims no modality: the page stays usable behind it',
            trigger: '#website_cookies_bar .modal:not([aria-modal])',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Open the detail view once more, to leave it with the keyboard',
            trigger: '#website_cookies_bar #muk_cookies_customize',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Escape leaves the layer it opened',
            trigger: '#website_cookies_bar .modal.mk_cookies_expanded',
            in_modal: false,
            run: () => {
                // dispatched natively: this branch's key helper only fires
                // jQuery handlers, and the dialog listens for the real event
                document.querySelector('#website_cookies_bar .modal').dispatchEvent(
                    new KeyboardEvent('keydown', {
                        key: 'Escape',
                        bubbles: true,
                    }),
                );
            },
        },
        {
            content: 'The first layer is back',
            trigger: "#website_cookies_bar [data-layer='notice']:not(.d-none)",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'And dismissing a layer decided nothing, in either direction',
            trigger: 'body',
            in_modal: false,
            run: () => {
                if (readConsent()) {
                    throw new Error('Escape must never store a decision.');
                }
            },
        },
        {
            content: 'Refuse everything, so the banner has to be reopened',
            trigger: '#website_cookies_bar .mk_cookies_reject_all',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Wait for the page the decision reloaded',
            trigger: "body:has(#website_cookies_bar[data-muk-cookie-ask='0'])",
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content:
                'And the floating button is offered once the banner is closed, ' +
                'where a bar at the bottom no longer covers it',
            trigger: '.mk_cookies_float.mk_cookies_reopen',
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        {
            content: 'Come back to the choice from the footer',
            trigger: '.mk_cookies_footer .mk_cookies_reopen',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'Reopening moves focus into the dialog, not onto the link',
            trigger: '#website_cookies_bar .modal.show',
            in_modal: false,
            run: () => {
                const modalEl = document.querySelector('#website_cookies_bar .modal');
                if (!modalEl.contains(document.activeElement)) {
                    throw new Error(
                        'Focus stayed outside the reopened dialog, on ' +
                            `"${document.activeElement?.textContent?.trim()}".`,
                    );
                }
                const floatEl = document.querySelector('.mk_cookies_float');
                if (floatEl && getComputedStyle(floatEl).display !== 'none') {
                    throw new Error(
                        'The floating button is still reachable behind the open ' +
                            'dialog, where a bar at the bottom covers it.',
                    );
                }
                window.mukCookieStamp = readConsent().rts;
            },
        },
        {
            content: 'A decision already in force can be left exactly as it is',
            trigger: '#muk_cookies_dismiss:not(.d-none)',
            in_modal: false,
            run: () => {
                document.querySelector('#website_cookies_bar .modal').dispatchEvent(
                    new KeyboardEvent('keydown', {
                        key: 'Escape',
                        bubbles: true,
                    }),
                );
            },
        },
        {
            content: 'Escape closes the reopened banner and decides nothing',
            trigger: '.mk_cookies_float.mk_cookies_reopen',
            in_modal: false,
            run: () => {
                if (document.querySelector('#website_cookies_bar .modal.show')) {
                    throw new Error('Escape left the reopened banner on screen.');
                }
                assertGranted(['essential']);
                if (readConsent().rts !== window.mukCookieStamp) {
                    throw new Error('Looking at a choice rewrote it.');
                }
            },
        },
        {
            content: 'Come back once more, to leave with the pointer instead',
            trigger: '.mk_cookies_footer .mk_cookies_reopen',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'The way out is offered to a visitor who never presses a key',
            trigger: '#muk_cookies_dismiss:not(.d-none)',
            in_modal: false,
            run: 'click',
        },
        {
            content: 'And that leaves both the banner closed and the choice standing',
            trigger: '.mk_cookies_float.mk_cookies_reopen',
            in_modal: false,
            run: () => {
                if (document.querySelector('#website_cookies_bar .modal.show')) {
                    throw new Error('The banner stayed open after being dismissed.');
                }
                assertGranted(['essential']);
                if (readConsent().rts !== window.mukCookieStamp) {
                    throw new Error('Closing the banner rewrote the decision.');
                }
                if (!document.activeElement?.closest('.mk_cookies_reopen')) {
                    throw new Error(
                        'Focus was dropped instead of returned to the control ' +
                            'that opened the banner.',
                    );
                }
            },
        },
    ],
});
