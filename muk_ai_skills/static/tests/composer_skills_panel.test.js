import { describe, expect, test } from '@odoo/hoot';
import { click, edit, queryAll } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, useState, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { browser } from '@web/core/browser/browser';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

import { setSkills } from '@muk_ai_skills/chat/skill_cache';

describe.current.tags('muk_ai_skills');
defineMailModels();

const SKILLS = [
    { name: 'alpha', label: 'Alpha', description: 'Do alpha.', icon: 'fa-bolt' },
    { name: 'beta', label: 'Beta', description: 'Do beta.', icon: 'fa-cogs' },
];

/**
 * Mount a composer wired to a session and collect the skills it invokes.
 * @param {object} options the composer value and session id to mount with
 * @returns {Array<string>} the technical names the composer asked to invoke
 */
async function mountComposer({ value = '', sessionId = 42 } = {}) {
    const invoked = [];
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="state.value"
                sessionId="props.sessionId"
                placeholder="'type'"
                canSend="false"
                canStop="false"
                canAttach="true"
                attachments="[]"
                onInput="(value) => this.state.value = value"
                onSend="() => {}"
                onAttachFiles="() => {}"
                onInvokeSkill="(name) => props.invoked.push(name)"
            />
        `;
        setup() {
            this.state = useState({ value: this.props.value });
        }
    }
    Parent.props = {
        value: { type: String },
        sessionId: { type: Number },
        invoked: { type: Array },
    };
    await mountWithCleanup(Parent, { props: { value, sessionId, invoked } });
    return invoked;
}

function reset() {
    setSkills(42, []);
    browser.localStorage.clear();
}

test('the skills button opens the panel', async () => {
    reset();
    setSkills(42, SKILLS);
    await mountComposer();
    expect('.mk_skills_panel').toHaveCount(0);
    await click('.mk_skill_btn');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(1);
});

test('the skills button stays hidden when the session has no skill', async () => {
    reset();
    setSkills(42, []);
    await mountComposer();
    expect('.mk_skill_btn').toHaveCount(0);
});

test('the button appears once the skills resolve after mount', async () => {
    reset();
    setSkills(42, []);
    await mountComposer();
    expect('.mk_skill_btn').toHaveCount(0);
    setSkills(42, SKILLS);
    await animationFrame();
    expect('.mk_skill_btn').toHaveCount(1);
});

test('opening the panel takes the caret out of the composer', async () => {
    reset();
    setSkills(42, SKILLS);
    await mountComposer();
    await click('.mk_composer_row textarea');
    expect('.mk_composer_row textarea').toBeFocused();
    await click('.mk_skill_btn');
    await animationFrame();
    expect('.mk_composer_row textarea').not.toBeFocused();
});

test('picking a skill invokes it and closes the panel', async () => {
    reset();
    setSkills(42, SKILLS);
    const invoked = await mountComposer();
    await click('.mk_skill_btn');
    await animationFrame();
    await click(queryAll('.mk_skill')[1]);
    await animationFrame();
    expect(invoked).toEqual(['beta']);
    expect('.mk_skills_panel').toHaveCount(0);
});

test('picking a skill leaves the composer draft alone', async () => {
    reset();
    setSkills(42, SKILLS);
    await mountComposer({ value: 'half written message' });
    await click('.mk_skill_btn');
    await animationFrame();
    await click(queryAll('.mk_skill')[0]);
    await animationFrame();
    expect('.mk_composer_row textarea').toHaveValue('half written message');
});

test('the panel yields to the slash popover while a command is typed', async () => {
    reset();
    setSkills(42, SKILLS);
    await mountComposer({ value: '/he' });
    await click('.mk_skill_btn');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(0);
    expect(queryAll('.mk_slash_item').length).toBeGreaterThan(0);
});

test('a slash command closes the panel instead of parking it behind', async () => {
    reset();
    setSkills(42, SKILLS);
    await mountComposer();
    await click('.mk_skill_btn');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(1);
    await click('.mk_composer_row textarea');
    await edit('/he');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(0);
    await edit('');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(0);
    expect('.mk_composer_row textarea').toBeFocused();
});
