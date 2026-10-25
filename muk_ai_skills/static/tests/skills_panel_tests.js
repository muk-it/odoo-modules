// @odoo-module

import { Component, useState, xml } from '@odoo/owl';

import { hotkeyService } from '@web/core/hotkeys/hotkey_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import {
    click,
    editInput,
    getFixture,
    mount,
    nextTick,
} from '@web/../tests/helpers/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { sessionSlashCommands } from '@muk_ai/chat/session/use_ai_session';

import { setSkills } from '@muk_ai_skills/chat/skill_cache';

/** A chat holding the composer text, recording the skills it runs. */
class Host extends Component {
    static template = xml`
        <ChatComposer
            value="state.value"
            placeholder="'Ask'"
            sessionId="1"
            onInput="(value) => this.state.value = value"
            onSend="() => {}"
            onInvokeSkill="(name, text) => this.props.invoked.push([name, text])"
        />`;
    static components = { ChatComposer };
    static props = ['invoked'];
    setup() {
        this.state = useState({ value: '' });
    }
}

QUnit.module('skills_panel');

QUnit.test(
    'a skill picked from the panel goes before the composer text, a command runs at once',
    async (assert) => {
        registry.category('services').add('hotkey', hotkeyService);
        sessionSlashCommands.add('/brief', { name: '/brief', hint: 'Brief' });
        setSkills(1, [
            { name: 'summary', label: 'Summary', icon: 'fa-list' },
            { name: 'brief', label: 'Brief', icon: 'fa-bolt' },
        ]);
        const target = getFixture();
        const invoked = [];
        try {
            await mount(Host, target, { env: await makeTestEnv(), props: { invoked } });
            const textarea = target.querySelector('.mk_composer textarea');
            for (const [label, value, runs] of [
                ['Summary', '/summary only the totals', []],
                ['Brief', '', [['brief', 'only the totals']]],
            ]) {
                await editInput(target, '.mk_composer textarea', 'only the totals');
                await click(target, '.mk_skill_btn');
                const skill = [...target.querySelectorAll('.mk_skill')].find((button) =>
                    button.textContent.includes(label),
                );
                await click(skill);
                await nextTick();
                assert.strictEqual(textarea.value, value);
                assert.deepEqual(invoked, runs);
                assert.strictEqual(document.activeElement === textarea, !runs.length);
            }
        } finally {
            sessionSlashCommands.remove('/brief');
            setSkills(1, []);
        }
    },
);
