import { browser } from '@web/core/browser/browser';
import { user } from '@web/core/user';

const LIMIT = 3;

/**
 * Return the storage key holding the recent skills of the logged-in user.
 *
 * The list stays browser-local to keep the panel free of round trips, so the
 * key carries the uid: two accounts sharing a browser profile keep their own.
 * @returns {string} the localStorage key for the current user
 */
function storageKey() {
    return `muk_ai_skills.recent.${user.userId}`;
}

/**
 * Return the technical names of the skills invoked most recently, newest first.
 * @returns {Array<string>} the stored names, or an empty list when unreadable
 */
export function getRecentSkillNames() {
    try {
        const stored = JSON.parse(browser.localStorage.getItem(storageKey()) || '[]');
        return Array.isArray(stored) ? stored.filter((n) => typeof n === 'string') : [];
    } catch {
        return [];
    }
}

/**
 * Record a skill invocation so the chat panel can surface it as recent.
 * @param {string} name the technical name of the invoked skill
 */
export function recordSkillUse(name) {
    if (!name) {
        return;
    }
    const names = [name, ...getRecentSkillNames().filter((n) => n !== name)];
    try {
        browser.localStorage.setItem(
            storageKey(),
            JSON.stringify(names.slice(0, LIMIT)),
        );
    } catch {
        // a full or unavailable storage only costs the recent group
    }
}
