export const CONSENT_STATE_VERSION = 1;
export const ESSENTIAL = 'essential';

/**
 * Return the services of a previous payload that were granted in place.
 *
 * Those are separate decisions taken on the embed itself, so a later choice in
 * the dialog must not silently revoke them. Services that ride on a purpose are
 * left out: they follow the purposes being saved now.
 *
 * @param {object | null} previous the payload currently in force, if any
 * @param {Iterable<string>} contextualNames services asked for in place
 * @returns {string[]}
 */
export function keptContextualServices(previous, contextualNames) {
    const contextual = new Set(contextualNames);
    return (previous?.svcs || []).filter((name) => contextual.has(name));
}

/**
 * Return whether a decision takes something away rather than granting it.
 *
 * @param {string} action
 * @returns {boolean}
 */
export function isWithdrawal(action) {
    return action === 'reject_all' || action === 'withdraw';
}

/**
 * Build the payload for one decision.
 *
 * `previous` must be null whenever the server is asking again, because a
 * payload it no longer honours may not carry anything forward: reusing its
 * grants would put back exactly what the invalidation withdrew. An embed
 * allowed in place answers nothing that was asked, so it leaves `ans` clear
 * unless an earlier answer still stands, and a withdrawal drops the services
 * granted in place because taking them back is the point of it.
 *
 * @param {object} options
 * @param {string[]} options.categories granted purpose codes
 * @param {string} options.action accept_all, reject_all, custom or withdraw
 * @param {string} options.source where the decision was made
 * @param {object | null} options.previous the payload still in force, if any
 * @param {string[]} options.purposeServices services following those purposes
 * @param {string[]} [options.extraServices] services granted individually
 * @param {string[]} [options.contextualNames] services asked for in place
 * @param {object} [options.disclosure] pv, rh and lang as rendered
 * @param {number} options.now seconds since the epoch
 * @param {string} options.uid reference shared by one browser's decisions
 * @returns {object} the payload to store
 */
export function buildConsentState({
    categories,
    action,
    source,
    previous,
    purposeServices,
    extraServices = [],
    contextualNames = [],
    disclosure = {},
    now,
    uid,
}) {
    const services = isWithdrawal(action)
        ? [...purposeServices, ...extraServices]
        : [
              ...purposeServices,
              ...extraServices,
              ...keptContextualServices(previous, contextualNames),
          ];
    return {
        v: CONSENT_STATE_VERSION,
        uid,
        ans: source === 'embed' && !previous?.ans ? 0 : 1,
        cats: categories,
        svcs: [...new Set(services)].sort(),
        pv: parseInt(disclosure.pv || '1'),
        rh: disclosure.rh || '',
        ts: previous?.ts || now,
        rts: now,
        lang: disclosure.lang || '',
    };
}

/**
 * Return whether every optional purpose on offer was granted.
 *
 * Core's own cookie carries a single optional flag, and it may only claim full
 * consent when nothing was refused.
 *
 * @param {string[]} offered every purpose the dialog put to the visitor
 * @param {string[]} granted the purposes being saved
 * @returns {boolean}
 */
export function allOptionalGranted(offered, granted) {
    return offered
        .filter((code) => code !== ESSENTIAL)
        .every((code) => granted.includes(code));
}

/**
 * Return the names in a cookie string matching a declared pattern.
 *
 * Anchored, so a loose declaration cannot reach past its own purpose, and an
 * unparseable pattern matches nothing rather than throwing at the visitor.
 *
 * @param {string} cookieString the value of `document.cookie`
 * @param {string} pattern a regular expression from a declaration
 * @returns {string[]}
 */
export function matchStoredCookies(cookieString, pattern) {
    let regex;
    try {
        regex = new RegExp(`^(?:${pattern})`);
    } catch {
        return [];
    }
    return (cookieString || '')
        .split(';')
        .map((part) => part.split('=')[0].trim())
        .filter((name) => name && regex.test(name));
}
