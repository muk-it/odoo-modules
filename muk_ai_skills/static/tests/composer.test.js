import { describe, expect, test } from '@odoo/hoot';
import { queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

import {
    clearSkills,
    setActiveSessionId,
    setSkills,
} from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');
defineMailModels();


function makeParent({ value = '' } = {}) {
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="props.value"
                placeholder="'type'"
                canSend="false"
                canStop="false"
                canAttach="true"
                attachments="[]"
                onInput="() => {}"
                onSend="() => {}"
                onAttachFiles="() => {}"
            />
        `;
    }
    Parent.props = { value: { type: String } };
    return { Parent, props: { value } };
}


function reset() {
    clearSkills(42);
    setActiveSessionId(null);
}


test('skills do not appear when no active session is set', async () => {
    reset();
    setSkills(42, [{ name: 'alpha', description: 'Do alpha.' }]);
    const { Parent, props } = makeParent({ value: '/al' });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/alpha'))).toBe(false);
});


test('active-session skills appear in the slash menu', async () => {
    reset();
    setSkills(42, [
        { name: 'alpha', description: 'Do alpha.' },
        { name: 'beta', description: 'Do beta.' },
    ]);
    setActiveSessionId(42);
    const { Parent, props } = makeParent({ value: '/' });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/alpha'))).toBe(true);
    expect(labels.some((l) => l.includes('/beta'))).toBe(true);
});


test('skill entries are filtered by typed prefix', async () => {
    reset();
    setSkills(42, [
        { name: 'alpha', description: 'A.' },
        { name: 'beta', description: 'B.' },
    ]);
    setActiveSessionId(42);
    const { Parent, props } = makeParent({ value: '/al' });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/alpha'))).toBe(true);
    expect(labels.some((l) => l.includes('/beta'))).toBe(false);
});


test('skill description renders as the slash menu hint', async () => {
    reset();
    setSkills(42, [{ name: 'alpha', description: 'Do alpha things.' }]);
    setActiveSessionId(42);
    const { Parent, props } = makeParent({ value: '/al' });
    await mountWithCleanup(Parent, { props });
    const item = queryFirst('.mk_slash_item');
    expect(item).not.toBe(null);
    expect(item.textContent).toMatch(/Do alpha things\./);
});


test('skills do not duplicate a built-in slash command of the same name', async () => {
    reset();
    setSkills(42, [{ name: 'help', description: 'Hijack attempt.' }]);
    setActiveSessionId(42);
    const { Parent, props } = makeParent({ value: '/help' });
    await mountWithCleanup(Parent, { props });
    const helpItems = queryAll('.mk_slash_item').filter((el) =>
        el.textContent.includes('/help'),
    );
    expect(helpItems.length).toBe(1);
});


test('non-slash input is unaffected by skills', async () => {
    reset();
    setSkills(42, [{ name: 'alpha', description: 'Do alpha.' }]);
    setActiveSessionId(42);
    const { Parent, props } = makeParent({ value: 'hello' });
    await mountWithCleanup(Parent, { props });
    expect('.mk_slash_item').toHaveCount(0);
});
