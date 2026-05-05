import { describe, expect, test } from '@odoo/hoot';

import {
    clearSkills,
    findSkill,
    getActiveSkills,
    setActiveSessionId,
    setSkills,
} from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');


function reset() {
    clearSkills(1);
    clearSkills(2);
    setActiveSessionId(null);
}


test('getActiveSkills returns empty when no active session set', () => {
    reset();
    expect(getActiveSkills()).toEqual([]);
});


test('getActiveSkills returns skills for the active session only', () => {
    reset();
    setSkills(1, [{ name: 'alpha', description: 'A' }]);
    setSkills(2, [{ name: 'beta', description: 'B' }]);
    setActiveSessionId(1);
    const active = getActiveSkills();
    expect(active.map((s) => s.name)).toEqual(['alpha']);
    setActiveSessionId(2);
    expect(getActiveSkills().map((s) => s.name)).toEqual(['beta']);
});


test('setSkills coerces non-array to empty array', () => {
    reset();
    setSkills(1, null);
    setActiveSessionId(1);
    expect(getActiveSkills()).toEqual([]);
    setSkills(1, 'oops');
    expect(getActiveSkills()).toEqual([]);
});


test('clearSkills drops the entry for that session', () => {
    reset();
    setSkills(1, [{ name: 'alpha' }]);
    setActiveSessionId(1);
    expect(getActiveSkills()).toHaveLength(1);
    clearSkills(1);
    expect(getActiveSkills()).toEqual([]);
});


test('setActiveSessionId(null) yields empty active list', () => {
    reset();
    setSkills(1, [{ name: 'alpha' }]);
    setActiveSessionId(1);
    expect(getActiveSkills()).toHaveLength(1);
    setActiveSessionId(null);
    expect(getActiveSkills()).toEqual([]);
});


test('findSkill matches case-insensitively', () => {
    reset();
    setSkills(1, [
        { name: 'alpha', description: 'A' },
        { name: 'beta_skill', description: 'B' },
    ]);
    expect(findSkill(1, 'ALPHA').name).toBe('alpha');
    expect(findSkill(1, 'Beta_Skill').name).toBe('beta_skill');
});


test('findSkill returns null when not found or session unknown', () => {
    reset();
    setSkills(1, [{ name: 'alpha' }]);
    expect(findSkill(1, 'gamma')).toBe(null);
    expect(findSkill(99, 'alpha')).toBe(null);
    expect(findSkill(1, '')).toBe(null);
});
