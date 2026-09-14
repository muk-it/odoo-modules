import { describe, expect, test } from '@odoo/hoot';

import { skillScopeSatisfied } from '@muk_ai_skills/chat/scope';

describe.current.tags('muk_ai_skills');

const RECORD = { kind: 'record', model: 'res.partner', id: 7, has_chatter: true };
const PLAIN_RECORD = {
    kind: 'record',
    model: 'res.currency',
    id: 1,
    has_chatter: false,
};
const LIST = { kind: 'list', model: 'res.partner' };

test('a skill without a scope runs anywhere', () => {
    const skill = { scope: 'any' };
    expect(skillScopeSatisfied(skill, null)).toBe(true);
    expect(skillScopeSatisfied(skill, LIST)).toBe(true);
    expect(skillScopeSatisfied(skill, RECORD)).toBe(true);
});

test('a context skill takes a record or a list but not an empty chat', () => {
    const skill = { scope: 'context' };
    expect(skillScopeSatisfied(skill, null)).toBe(false);
    expect(skillScopeSatisfied(skill, LIST)).toBe(true);
    expect(skillScopeSatisfied(skill, RECORD)).toBe(true);
});

test('a record skill refuses a list, including an unsaved form', () => {
    const skill = { scope: 'record' };
    expect(skillScopeSatisfied(skill, LIST)).toBe(false);
    expect(
        skillScopeSatisfied(skill, {
            kind: 'list',
            model: 'res.partner',
            view_type: 'form',
        }),
    ).toBe(false);
    expect(skillScopeSatisfied(skill, RECORD)).toBe(true);
});

test('a chatter skill needs a record whose model has one', () => {
    const skill = { scope: 'chatter' };
    expect(skillScopeSatisfied(skill, RECORD)).toBe(true);
    expect(skillScopeSatisfied(skill, PLAIN_RECORD)).toBe(false);
});

test('a context pinned before the flag existed stays available', () => {
    const skill = { scope: 'chatter' };
    expect(
        skillScopeSatisfied(skill, { kind: 'record', model: 'res.partner', id: 7 }),
    ).toBe(true);
});

test('a model restriction narrows every scope', () => {
    const skill = { scope: 'any', models: ['res.partner'] };
    expect(skillScopeSatisfied(skill, RECORD)).toBe(true);
    expect(
        skillScopeSatisfied(skill, { kind: 'record', model: 'res.users', id: 1 }),
    ).toBe(false);
    expect(skillScopeSatisfied(skill, null)).toBe(false);
});
