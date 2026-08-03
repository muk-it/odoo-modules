import { describe, expect, test } from '@odoo/hoot';
import { browser } from '@web/core/browser/browser';
import { user } from '@web/core/user';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { getRecentSkillNames, recordSkillUse } from '@muk_ai_skills/chat/recent_skills';

describe.current.tags('muk_ai_skills');

test('a use is recorded and read back', () => {
    browser.localStorage.clear();
    recordSkillUse('alpha');
    expect(getRecentSkillNames()).toEqual(['alpha']);
});

test('the newest use comes first and never duplicates', () => {
    browser.localStorage.clear();
    recordSkillUse('alpha');
    recordSkillUse('beta');
    recordSkillUse('alpha');
    expect(getRecentSkillNames()).toEqual(['alpha', 'beta']);
});

test('only the three most recent uses are kept', () => {
    browser.localStorage.clear();
    for (const name of ['a', 'b', 'c', 'd']) {
        recordSkillUse(name);
    }
    expect(getRecentSkillNames()).toEqual(['d', 'c', 'b']);
});

test('a falsy name is ignored', () => {
    browser.localStorage.clear();
    recordSkillUse('alpha');
    recordSkillUse('');
    expect(getRecentSkillNames()).toEqual(['alpha']);
});

test('unreadable storage degrades to an empty list', () => {
    browser.localStorage.clear();
    recordSkillUse('alpha');
    browser.localStorage.setItem(`muk_ai_skills.recent.${user.userId}`, '{not json');
    expect(getRecentSkillNames()).toEqual([]);
});

test('another user on the same browser keeps its own list', () => {
    browser.localStorage.clear();
    recordSkillUse('alpha');
    patchWithCleanup(user, { userId: user.userId + 1 });
    expect(getRecentSkillNames()).toEqual([]);
    recordSkillUse('beta');
    expect(getRecentSkillNames()).toEqual(['beta']);
});
