// @odoo-module

import { reactive } from '@odoo/owl';

/**
 * Skills of the open sessions, keyed by session id. Reactive so a component
 * that reads it through `useState` re-renders once the fetch resolves.
 */
export const skillStore = reactive({});

/**
 * Store the visible skills for a session, coercing a non-array to an empty list.
 * @param {number} sessionId the session id to key the cache by
 * @param {Array} skills the skill descriptors to cache
 */
export function setSkills(sessionId, skills) {
    skillStore[sessionId] = Array.isArray(skills) ? skills : [];
}

/**
 * Return the cached skills for a specific session.
 * @param {number} sessionId the session id to look up
 * @returns {Array} the session's skills, or an empty list
 */
export function getSkills(sessionId) {
    if (!sessionId) {
        return [];
    }
    return skillStore[sessionId] || [];
}

/**
 * Find a cached skill for a session by its case-insensitive technical name.
 * @param {number} sessionId the session id to look up
 * @param {string} name the technical name to match
 * @returns {object|null} the matching skill, or null when none matches
 */
export function findSkill(sessionId, name) {
    const skills = getSkills(sessionId);
    const lowered = (name || '').toLowerCase();
    return skills.find((s) => (s.name || '').toLowerCase() === lowered) || null;
}

const panelRequests = new Set();

/**
 * Ask the composer of a chat not opened yet to show its skills panel.
 * @param {number} sessionId the chat
 */
export function requestSkillsPanel(sessionId) {
    panelRequests.add(sessionId);
}

/**
 * Take the request to show the skills panel of a chat, if there is one.
 * @param {number} sessionId the chat
 * @returns {boolean} true when the panel was asked for
 */
export function takeSkillsPanelRequest(sessionId) {
    return panelRequests.delete(sessionId);
}
