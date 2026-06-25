const cache = new Map();
let activeSessionId = null;

/**
 * Store the visible skills for a session, coercing a non-array to an empty list.
 * @param {number} sessionId the session id to key the cache by
 * @param {Array} skills the skill descriptors to cache
 */
export function setSkills(sessionId, skills) {
    cache.set(sessionId, Array.isArray(skills) ? skills : []);
}

/**
 * Drop the cached skills for a session.
 * @param {number} sessionId the session id to evict
 */
export function clearSkills(sessionId) {
    cache.delete(sessionId);
}

/**
 * Return the cached skills for the currently active session.
 * @returns {Array} the active session's skills, or an empty list
 */
export function getActiveSkills() {
    if (activeSessionId === null) {
        return [];
    }
    return cache.get(activeSessionId) || [];
}

/**
 * Mark a session as active for `getActiveSkills`, or clear it when falsy.
 * @param {number} sessionId the session id to activate
 */
export function setActiveSessionId(sessionId) {
    activeSessionId = sessionId || null;
}

/**
 * Find a cached skill for a session by its case-insensitive technical name.
 * @param {number} sessionId the session id to look up
 * @param {string} name the technical name to match
 * @returns {object|null} the matching skill, or null when none matches
 */
export function findSkill(sessionId, name) {
    const skills = cache.get(sessionId) || [];
    const lowered = (name || '').toLowerCase();
    return skills.find((s) => (s.name || '').toLowerCase() === lowered) || null;
}
