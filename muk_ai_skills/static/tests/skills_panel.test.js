import { describe, expect, test } from '@odoo/hoot';
import {
    click,
    edit,
    press,
    queryAll,
    queryAllTexts,
    queryFirst,
} from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { browser } from '@web/core/browser/browser';

import { recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { SkillsPanel } from '@muk_ai_skills/chat/skills_panel';

describe.current.tags('muk_ai_skills');
defineMailModels();

const SKILLS = [
    { name: 'alpha', label: 'Alpha', description: 'Do alpha.', icon: 'fa-bolt' },
    { name: 'beta', label: 'Beta', description: 'Do beta.', icon: 'fa-cogs' },
];

/**
 * Mount the panel on its own and collect what it selects and closes.
 * @param {object} options the skills to list and whether to focus the search
 * @returns {object} the `picked` names and `closed` flags, both live arrays
 */
async function mountPanel({
    skills = SKILLS,
    lockedSkills = [],
    autofocus = true,
} = {}) {
    const picked = [];
    const closed = [];
    await mountWithCleanup(SkillsPanel, {
        props: {
            skills,
            lockedSkills,
            autofocus,
            onSelect: (name) => picked.push(name),
            onClose: () => closed.push(true),
        },
    });
    return { picked, closed };
}

function reset() {
    browser.localStorage.clear();
}

test('every visible skill is listed', async () => {
    reset();
    await mountPanel();
    expect(queryAllTexts('.mk_skill_label')).toEqual(['Alpha', 'Beta']);
});

test('the search field filters the entries', async () => {
    reset();
    await mountPanel();
    await click('.mk_skills_search input');
    await edit('bet');
    await animationFrame();
    expect(queryAllTexts('.mk_skill_label')).toEqual(['Beta']);
});

test('a filter matching no skill renders the empty state', async () => {
    reset();
    await mountPanel();
    await click('.mk_skills_search input');
    await edit('nothing_matches');
    await animationFrame();
    expect('.mk_skill').toHaveCount(0);
    expect(queryFirst('.mk_skills_empty')).not.toBe(null);
});

test('clicking an entry selects it by technical name', async () => {
    reset();
    const { picked } = await mountPanel();
    await click(queryAll('.mk_skill')[1]);
    await animationFrame();
    expect(picked).toEqual(['beta']);
});

test('arrow keys move the active entry and enter runs it', async () => {
    reset();
    const { picked } = await mountPanel();
    await press('ArrowDown');
    await animationFrame();
    expect(queryAll('.mk_skill')[1]).toHaveClass('active');
    await press('Enter');
    await animationFrame();
    expect(picked).toEqual(['beta']);
});

test('a shrinking entry list resets the active index so enter still runs', async () => {
    reset();
    const { picked } = await mountPanel();
    await press('ArrowDown');
    await animationFrame();
    await click('.mk_skills_search input');
    await edit('alpha');
    await animationFrame();
    await press('Enter');
    await animationFrame();
    expect(picked).toEqual(['alpha']);
});

test('escape asks the owner to close the panel', async () => {
    reset();
    const { picked, closed } = await mountPanel();
    await press('Escape');
    await animationFrame();
    expect(closed).toEqual([true]);
    expect(picked).toEqual([]);
});

test('the search field takes the caret when autofocus is asked for', async () => {
    reset();
    await mountPanel({ autofocus: true });
    expect('.mk_skills_search input').toBeFocused();
});

test('without autofocus the panel itself takes focus, not the search field', async () => {
    reset();
    await mountPanel({ autofocus: false });
    expect('.mk_skills_search input').not.toBeFocused();
    expect('.mk_skills_panel').toBeFocused();
});

test('arrows and enter still work when the search field is not focused', async () => {
    reset();
    const { picked } = await mountPanel({ autofocus: false });
    await press('ArrowDown');
    await animationFrame();
    expect(queryAll('.mk_skill')[1]).toHaveClass('active');
    await press('Enter');
    await animationFrame();
    expect(picked).toEqual(['beta']);
});

test('a recently used skill is listed first under its own group', async () => {
    reset();
    recordSkillUse('beta');
    await mountPanel();
    expect(queryAllTexts('.mk_skill_label')).toEqual(['Beta', 'Alpha']);
    expect(queryAllTexts('.mk_skills_group')).toEqual(['Recently used', 'All skills']);
});

test('a withheld skill is listed apart, inert, and says what it needs', async () => {
    await mountPanel({
        skills: [SKILLS[0]],
        lockedSkills: [{ ...SKILLS[1], requirement: 'needs a record open' }],
    });
    expect('.mk_skill_locked').toHaveCount(1);
    expect('.mk_skill_locked').toHaveAttribute('disabled');
    expect(queryFirst('.mk_skill_locked .mk_skill_preview')).toHaveText(
        'needs a record open',
    );
    expect(queryAll('.mk_skills_group').at(-1)).toHaveText('Once something is open');
});

test('the keyboard never reaches a withheld skill', async () => {
    const { picked } = await mountPanel({
        skills: [SKILLS[0]],
        lockedSkills: [{ ...SKILLS[1], requirement: 'needs a record open' }],
    });
    await press('ArrowDown');
    await press('Enter');
    expect(picked).toEqual(['alpha']);
});

test('the empty state stays away while a withheld skill is listed', async () => {
    await mountPanel({
        skills: [],
        lockedSkills: [{ ...SKILLS[1], requirement: 'needs a record open' }],
    });
    expect('.mk_skills_empty').toHaveCount(0);
    expect('.mk_skill_locked').toHaveCount(1);
});
