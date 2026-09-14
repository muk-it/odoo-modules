import { describe, expect, test } from '@odoo/hoot';
import { queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

import { setSkills } from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');
defineMailModels();

function makeParent({ value = '', sessionId = 42, viewContext = null } = {}) {
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="props.value"
                sessionId="props.sessionId"
                viewContext="props.viewContext"
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
    Parent.props = {
        value: { type: String },
        sessionId: { type: Number },
        viewContext: { optional: true },
    };
    return { Parent, props: { value, sessionId, viewContext } };
}

function reset() {
    setSkills(42, []);
    setSkills(99, []);
}

test("another session's skills do not leak into this composer", async () => {
    reset();
    setSkills(99, [{ name: 'alpha', description: 'Do alpha.' }]);
    const { Parent, props } = makeParent({ value: '/al', sessionId: 42 });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/alpha'))).toBe(false);
});

test('the composer session skills appear in the slash menu', async () => {
    reset();
    setSkills(42, [
        { name: 'alpha', description: 'Do alpha.' },
        { name: 'beta', description: 'Do beta.' },
    ]);
    const { Parent, props } = makeParent({ value: '/', sessionId: 42 });
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
    const { Parent, props } = makeParent({ value: '/al', sessionId: 42 });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/alpha'))).toBe(true);
    expect(labels.some((l) => l.includes('/beta'))).toBe(false);
});

test('skill description renders as the slash menu hint', async () => {
    reset();
    setSkills(42, [{ name: 'alpha', description: 'Do alpha things.' }]);
    const { Parent, props } = makeParent({ value: '/al', sessionId: 42 });
    await mountWithCleanup(Parent, { props });
    const item = queryFirst('.mk_slash_item');
    expect(item).not.toBe(null);
    expect(item.textContent).toMatch(/Do alpha things\./);
});

test('skills do not duplicate a built-in slash command of the same name', async () => {
    reset();
    setSkills(42, [{ name: 'help', description: 'Hijack attempt.' }]);
    const { Parent, props } = makeParent({ value: '/help', sessionId: 42 });
    await mountWithCleanup(Parent, { props });
    const helpItems = queryAll('.mk_slash_item').filter((el) =>
        el.textContent.includes('/help'),
    );
    expect(helpItems.length).toBe(1);
});

test('non-slash input is unaffected by skills', async () => {
    reset();
    setSkills(42, [{ name: 'alpha', description: 'Do alpha.' }]);
    const { Parent, props } = makeParent({ value: 'hello', sessionId: 42 });
    await mountWithCleanup(Parent, { props });
    expect('.mk_slash_item').toHaveCount(0);
});

test('a record skill is offered only once a record is pinned', async () => {
    reset();
    setSkills(42, [
        { name: 'note', label: 'Note', description: 'Note it.', scope: 'record' },
    ]);
    const { Parent, props } = makeParent({
        value: '/no',
        viewContext: { kind: 'list', model: 'res.partner' },
    });
    await mountWithCleanup(Parent, { props });
    const onList = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(onList.some((l) => l.includes('/note'))).toBe(false);

    const pinned = makeParent({
        value: '/no',
        viewContext: { kind: 'record', model: 'res.partner', id: 1 },
    });
    await mountWithCleanup(pinned.Parent, { props: pinned.props });
    const onRecord = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(onRecord.some((l) => l.includes('/note'))).toBe(true);
});

test('a chatter skill is withheld on a record whose model has none', async () => {
    reset();
    setSkills(42, [
        { name: 'reply', label: 'Reply', description: 'Reply.', scope: 'chatter' },
    ]);
    const { Parent, props } = makeParent({
        value: '/re',
        viewContext: {
            kind: 'record',
            model: 'res.currency',
            id: 1,
            has_chatter: false,
        },
    });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_slash_item').map((el) => el.textContent);
    expect(labels.some((l) => l.includes('/reply'))).toBe(false);
});
