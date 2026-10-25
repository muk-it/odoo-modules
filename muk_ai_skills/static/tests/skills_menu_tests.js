// @odoo-module

import { Component, useState, xml } from '@odoo/owl';

import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { click, getFixture, mount, nextTick } from '@web/../tests/helpers/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import '@muk_ai_skills/chat/composer';
import '@muk_ai_skills/chat/turn_decorators';
import { setSkills } from '@muk_ai_skills/chat/skill_cache';

QUnit.module('muk_ai_skills', {}, function () {
    QUnit.module('skills_menu');

    class ComposerHost extends Component {
        static template = xml`
            <ChatComposer
                value="state.value"
                placeholder="'Message'"
                sessionId="1"
                onInput="(value) => this.state.value = value"
                onSend="() => {}"
                onInvokeSkill="(name, text) => this.props.steps.push(name + ': ' + text)"
            />
        `;
        static components = { ChatComposer };
        static props = ['steps'];
        setup() {
            this.state = useState({ value: '' });
        }
    }

    QUnit.test(
        'a picked skill goes in front of the composer text, one named like a command runs',
        async (assert) => {
            setSkills(1, [
                { name: 'brief', label: 'Brief', icon: 'fa-file-text-o' },
                { name: 'help', label: 'Help', icon: 'fa-question' },
            ]);
            const steps = [];
            const target = getFixture();
            const env = await makeTestEnv();
            const host = await mount(ComposerHost, target, { env, props: { steps } });
            const textarea = target.querySelector('.mk_composer textarea');
            for (const [text, label, value, invoked] of [
                ['only the totals', 'Brief', '/brief only the totals', []],
                ['only the totals', 'Help', '', ['help: only the totals']],
                ['', 'Brief', '/brief ', []],
            ]) {
                host.state.value = text;
                await nextTick();
                await click(target, '.mk_skill_btn');
                await click(
                    [...target.querySelectorAll('.mk_skill')].find(
                        (button) =>
                            button.querySelector('.mk_skill_label').textContent ===
                            label,
                    ),
                );
                assert.containsNone(target, '.mk_skills_panel');
                assert.strictEqual(textarea.value, value);
                assert.deepEqual(steps.splice(0), invoked);
            }
            assert.strictEqual(document.activeElement, textarea);
        },
    );

    QUnit.test('a skill run is labelled with the name of the skill', (assert) => {
        const [turn] = buildRenderedTurns([
            {
                kind: 'tool_call',
                call_id: 's1',
                name: 'invoke_skill',
                arguments: '{"skill_name": "brief"}',
            },
        ]);
        assert.strictEqual(String(turn.blocks[0].label), 'Skill: brief');
    });
});
