import { describe, expect, test } from '@odoo/hoot';

import { findSkill, getSkills, setSkills } from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');

function reset() {
    setSkills(1, []);
    setSkills(2, []);
}

test('getSkills returns empty for an unknown or falsy session', () => {
    reset();
    expect(getSkills(1)).toEqual([]);
    expect(getSkills(null)).toEqual([]);
});

test('getSkills returns skills for that session only', () => {
    reset();
    setSkills(1, [{ name: 'alpha', description: 'A' }]);
    setSkills(2, [{ name: 'beta', description: 'B' }]);
    expect(getSkills(1).map((s) => s.name)).toEqual(['alpha']);
    expect(getSkills(2).map((s) => s.name)).toEqual(['beta']);
});

test('setSkills coerces non-array to empty array', () => {
    reset();
    setSkills(1, null);
    expect(getSkills(1)).toEqual([]);
    setSkills(1, 'oops');
    expect(getSkills(1)).toEqual([]);
});

test('a refreshed session replaces its previous skills', () => {
    reset();
    setSkills(1, [{ name: 'alpha' }]);
    expect(getSkills(1)).toHaveLength(1);
    setSkills(1, [{ name: 'beta' }]);
    expect(getSkills(1).map((s) => s.name)).toEqual(['beta']);
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
