const cache = new Map();
let activeSessionId = null;

export function setSkills(sessionId, skills) {
    cache.set(sessionId, Array.isArray(skills) ? skills : []);
}

export function clearSkills(sessionId) {
    cache.delete(sessionId);
}

export function getActiveSkills() {
    if (activeSessionId === null) {
        return [];
    }
    return cache.get(activeSessionId) || [];
}

export function setActiveSessionId(sessionId) {
    activeSessionId = sessionId || null;
}

export function findSkill(sessionId, name) {
    const skills = cache.get(sessionId) || [];
    const lowered = (name || '').toLowerCase();
    return skills.find((s) => (s.name || '').toLowerCase() === lowered) || null;
}
