import { describe, expect, test } from '@odoo/hoot';

import { resolveChatSkill } from '@muk_ai_skills/chat/chat';
import { setSkills } from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');

test('resolveChatSkill routes a non-built-in skill head', () => {
    setSkills(7, [{ name: 'alpha' }]);
    expect(resolveChatSkill(7, 'alpha').name).toBe('alpha');
    setSkills(7, []);
});

test('resolveChatSkill lets a built-in command win over a same-named skill', () => {
    setSkills(7, [{ name: 'help' }, { name: 'clear' }, { name: 'compact' }]);
    expect(resolveChatSkill(7, 'help')).toBe(null);
    expect(resolveChatSkill(7, 'CLEAR')).toBe(null);
    expect(resolveChatSkill(7, 'compact')).toBe(null);
    setSkills(7, []);
});

test('resolveChatSkill returns null for an unknown skill head', () => {
    setSkills(7, []);
    expect(resolveChatSkill(7, 'nope')).toBe(null);
});
