/** @odoo-module */

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from '@odoo/owl';

import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { _lt, _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';
import { sprintf } from '@web/core/utils/strings';

import { useSessionChannel } from '@muk_ai/chat/session/session_channel';
import { busSubscribe, busUnsubscribe } from '@muk_ai/core/compat/bus';

import { rememberInsert } from '@muk_ai_chatter/composer/insert_button/insert_button';
import { wordDiff } from '@muk_ai_chatter/composer/word_diff/word_diff';

export const LENGTHS = [
    { id: 'shorter', label: _lt('Shorter'), directive: 'Keep it noticeably shorter.' },
    { id: 'as_is', label: _lt('As is'), directive: '' },
    { id: 'longer', label: _lt('Longer'), directive: 'Take a little more room.' },
];

export const TONES = [
    { id: 'neutral', label: _lt('Neutral'), directive: '' },
    { id: 'formal', label: _lt('Formal'), directive: 'Write in a formal register.' },
    {
        id: 'friendly',
        label: _lt('Friendly'),
        directive: 'Write in a warm, friendly tone.',
    },
];

export const TERMINAL_STATES = ['done', 'stopped', 'error'];

export const REWRITE_CATEGORIES = ['fix', 'rewrite', 'transform'];

export const CATEGORIES = {
    fix: { label: _lt('Fix'), icon: 'fa-check' },
    rewrite: { label: _lt('Rewrite'), icon: 'fa-pencil' },
    transform: { label: _lt('Transform'), icon: 'fa-language' },
    generate: { label: _lt('Write'), icon: 'fa-magic' },
};

let closeOpenPanel = null;

/**
 * The writing helper of a composer. A selection is reworded in place, a
 * draft as a whole, and an empty composer is offered what can be written from
 * the record, with a length and a tone. A rewrite is shown as a diff, and
 * nothing reaches the composer until it is accepted. One panel is open at a
 * time.
 */
export class ComposePanel extends Component {
    static template = 'muk_ai_chatter.ComposePanel';
    static props = { adapter: Object, close: { type: Function, optional: true } };
    lengths = LENGTHS;
    tones = TONES;
    setup() {
        this.orm = useService('orm');
        this.bus = this.env.services.bus_service;
        this.chatWindow = useService('muk_ai.chat_window');
        this.action = useService('action');
        this.notification = useService('notification');
        this.state = useState({
            sessionId: null,
            phase: 'idle',
            skills: [],
            selection: this.props.adapter.getSelection(),
            draft: this.props.adapter.getDraft().trim(),
            label: '',
            result: '',
            streaming: '',
            error: '',
            length: 'as_is',
            tone: 'neutral',
            custom: '',
            asked: '',
            opened: '',
            customAsked: '',
            saveOpen: false,
            saveLabel: '',
            savedLabel: '',
            saving: false,
            createOpen: false,
            createLabel: '',
            createBody: '',
            createCategory: '',
        });
        this.saveLabelRef = useRef('saveLabel');
        this.createLabelRef = useRef('createLabel');
        useEffect(
            (input) => input?.focus(),
            () => [this.saveLabelRef.el],
        );
        useEffect(
            (input) => input?.focus(),
            () => [this.createLabelRef.el],
        );
        useSessionChannel(() => this.state.sessionId);
        const onEvent = (event) => this.onSessionEvent(event);
        busSubscribe(this.bus, 'muk_ai.event', onEvent);
        useHotkey('escape', () => this.props.close?.(), {
            bypassEditableProtection: true,
            global: true,
        });
        onWillStart(async () => {
            try {
                this.state.skills = await this.orm.call(
                    'muk_ai.skill',
                    'fetch_skills',
                    ['composer'],
                );
            } catch (error) {
                this.reportError(error);
            }
            await this.openSession();
        });
        const close = () => this.props.close?.();
        onMounted(() => {
            if (closeOpenPanel && closeOpenPanel !== close) {
                closeOpenPanel();
            }
            closeOpenPanel = close;
        });
        onWillUnmount(() => {
            busUnsubscribe(this.bus, 'muk_ai.event', onEvent);
            if (closeOpenPanel === close) {
                closeOpenPanel = null;
            }
            if (this.state.sessionId && !this.state.asked) {
                this.orm.silent
                    .call('muk_ai.session', 'discard_unused_composer', [
                        [this.state.sessionId],
                    ])
                    .catch(() => {});
            }
        });
    }
    get hasSelection() {
        return Boolean(this.state.selection);
    }
    get target() {
        return this.state.selection || this.state.draft;
    }
    get isRewrite() {
        return Boolean(this.target);
    }
    /**
     * What the panel offers at rest: one action per category. A category of
     * one skill is that skill, several open a row; writing from nothing shows
     * its row at once.
     * @returns {object[]} the actions, each carrying the skills behind it
     */
    get groups() {
        const order = this.isRewrite ? REWRITE_CATEGORIES : ['generate'];
        return order
            .map((category) => {
                const skills = this.state.skills.filter(
                    (skill) => skill.category === category,
                );
                const alone = skills.length === 1 && category !== 'generate';
                return {
                    category,
                    skills,
                    opens: !alone,
                    modifiers: category === 'generate',
                    label: alone ? skills[0].label : CATEGORIES[category].label,
                    icon: alone ? skills[0].icon : CATEGORIES[category].icon,
                };
            })
            .filter((group) => group.skills.length);
    }
    get openGroup() {
        if (!this.isRewrite) {
            return this.groups[0];
        }
        return this.groups.find((group) => group.category === this.state.opened);
    }
    get isRunning() {
        return this.state.phase === 'running';
    }
    get diff() {
        if (!this.isRewrite || this.state.phase !== 'preview') {
            return null;
        }
        return wordDiff(this.target, this.state.result);
    }
    get errorLabel() {
        const first = (this.state.error || '').split(/[:(]/)[0].trim();
        if (!first) {
            return _t('The run failed.');
        }
        return first.length > 48 ? `${first.slice(0, 48)}...` : first;
    }
    get busyLabel() {
        return this.state.label
            ? sprintf(_t('%s...'), this.state.label)
            : _t('Writing...');
    }
    get title() {
        if (this.hasSelection) {
            return _t('Rewrite the selection');
        }
        return this.isRewrite ? _t('Rewrite your message') : _t('Write a message');
    }
    get subtitle() {
        if (this.state.phase === 'preview') {
            return this.isRewrite
                ? _t('Nothing is replaced until you say so')
                : _t('Nothing is inserted until you say so');
        }
        if (!this.isRewrite) {
            return _t('Written from this record');
        }
        const words = this.target.trim().split(/\s+/).length;
        if (this.hasSelection) {
            return words === 1
                ? _t('1 selected word')
                : sprintf(_t('%s selected words'), words);
        }
        return words === 1
            ? _t('1 word in your draft')
            : sprintf(_t('%s words in your draft'), words);
    }
    get quoted() {
        const target = this.target.trim();
        return target.length > 180 ? `${target.slice(0, 180)}...` : target;
    }
    get canOfferSave() {
        return Boolean(this.state.customAsked) && !this.state.savedLabel;
    }
    get customPlaceholder() {
        return this.isRewrite
            ? _t('Describe what should change...')
            : _t('Describe what to write...');
    }
    reportError(error) {
        this.state.phase = 'error';
        this.state.error = error.data?.message || error.message || String(error);
    }
    /**
     * Open the session the helper answers from, so the first chip answers at
     * once.
     * @returns {Promise<boolean>} whether a session is available
     */
    async openSession() {
        if (this.state.sessionId) {
            return true;
        }
        const record = this.props.adapter.getRecord();
        try {
            const snapshot = await this.orm.call(
                'muk_ai.session',
                'open_for_composer',
                [],
                {
                    interface_key: this.props.adapter.interfaceKey,
                    res_model: record.resModel || false,
                    res_id: record.resId || false,
                    draft: this.props.adapter.getDraft(),
                    selection: this.state.selection,
                },
            );
            this.state.sessionId = snapshot.id;
            return true;
        } catch (error) {
            this.reportError(error);
            return false;
        }
    }
    buildPrompt(prompt) {
        if (this.isRewrite) {
            return prompt;
        }
        const length = LENGTHS.find((entry) => entry.id === this.state.length);
        const tone = TONES.find((entry) => entry.id === this.state.tone);
        return [prompt, length.directive, tone.directive].filter(Boolean).join(' ');
    }
    /**
     * Stream the answer of the session this panel holds while it runs, and
     * offer it once the run ends.
     * @param {object} event the payload pushed on the muk_ai bus
     */
    onSessionEvent(event) {
        if (event.session_id !== this.state.sessionId || !this.isRunning) {
            return;
        }
        if (event.type === 'text_delta') {
            this.state.streaming += event.payload.delta || '';
        } else if (
            event.type === 'state' &&
            TERMINAL_STATES.includes(event.payload.state)
        ) {
            this.finish();
        }
    }
    /**
     * Offer the answer of a run that came to rest. A `done` announced from
     * the middle of a run, while compacting, is not one.
     */
    async finish() {
        let values;
        try {
            [values] = await this.orm.read(
                'muk_ai.session',
                [this.state.sessionId],
                ['last_text', 'state', 'error_message'],
            );
        } catch (error) {
            return this.reportError(error);
        }
        if (!TERMINAL_STATES.includes(values.state)) {
            return;
        }
        const text = (values.last_text || '').trim();
        if (values.state === 'error' || !text) {
            this.state.phase = 'error';
            this.state.error =
                values.state === 'error'
                    ? values.error_message || ''
                    : _t('The agent returned nothing.');
            return;
        }
        Object.assign(this.state, { result: text, phase: 'preview' });
    }
    /**
     * Ask for one rewrite or one draft, the target sent as the selection even
     * when nothing was selected.
     * @param {string} label wording shown while it runs
     * @param {string} prompt the instruction the chip carries
     */
    async run(label, prompt) {
        if (this.isRunning || !(await this.openSession())) {
            return;
        }
        Object.assign(this.state, {
            label,
            asked: prompt,
            opened: '',
            saveOpen: false,
            savedLabel: '',
            result: '',
            streaming: '',
            error: '',
            phase: 'running',
        });
        const ids = [this.state.sessionId];
        try {
            await this.orm.call('muk_ai.session', 'update_compose_context', [
                ids,
                this.props.adapter.getDraft(),
                this.isRewrite ? this.target : '',
            ]);
            await this.orm.call('muk_ai.session', 'send_message', [
                ids,
                this.buildPrompt(prompt),
            ]);
        } catch (error) {
            this.reportError(error);
        }
    }
    onSkillClick(skill) {
        this.state.customAsked = '';
        this.run(skill.label, skill.body);
    }
    onGroupClick(group) {
        if (!group.opens) {
            return this.onSkillClick(group.skills[0]);
        }
        this.state.opened = this.state.opened === group.category ? '' : group.category;
    }
    onCustomSubmit() {
        const asked = this.state.custom.trim();
        if (asked) {
            Object.assign(this.state, { custom: '', customAsked: asked });
            this.run(_t('Writing'), asked);
        }
    }
    /**
     * Put an answer over the selection, over the whole message when that was
     * the target, and at the cursor otherwise. A selection keeps its spacing.
     * @param {string} text what the agent wrote
     */
    applyText(text) {
        const adapter = this.props.adapter;
        if (this.hasSelection) {
            const [, before, after] =
                this.state.selection.match(/^(\s*)[\s\S]*?(\s*)$/);
            adapter.applySelection(before + text + after);
        } else if (this.isRewrite) {
            adapter.replaceDraft(text);
        } else {
            adapter.applyDraft(text);
        }
    }
    onAccept() {
        this.applyText(this.state.result);
        this.props.close?.();
    }
    onDiscard() {
        Object.assign(this.state, { phase: 'idle', result: '' });
    }
    onCancel() {
        this.state.phase = 'idle';
        this.orm.silent
            .call('muk_ai.session', 'action_stop', [[this.state.sessionId]])
            .catch(() => {});
    }
    onRetry() {
        if (this.state.asked) {
            this.run(this.state.label, this.state.asked);
        }
    }
    onKeydown(ev, confirm, cancel) {
        if (ev.key === 'Enter' && ev.target.tagName !== 'TEXTAREA') {
            confirm();
        } else if (ev.key === 'Escape' && cancel) {
            ev.stopPropagation();
            cancel();
        }
    }
    /**
     * Save the free-text instruction behind the answer as a chip, generating
     * when asked over an empty composer and rewriting otherwise.
     */
    async onSaveConfirm() {
        const label = this.state.saveLabel.trim();
        const category = this.isRewrite ? 'rewrite' : 'generate';
        if (
            label &&
            (await this.saveQuickAction(label, this.state.customAsked, category))
        ) {
            Object.assign(this.state, { saveOpen: false, savedLabel: label });
        }
    }
    async onCreateConfirm() {
        const label = this.state.createLabel.trim();
        const body = this.state.createBody.trim();
        if (
            label &&
            body &&
            (await this.saveQuickAction(label, body, this.state.createCategory))
        ) {
            this.state.createOpen = false;
        }
    }
    onOpenSave() {
        Object.assign(this.state, { saveOpen: true, saveLabel: '' });
    }
    onOpenCreate() {
        Object.assign(this.state, {
            createOpen: true,
            createLabel: '',
            createBody: '',
            createCategory: this.isRewrite ? 'rewrite' : 'generate',
        });
    }
    /**
     * Create a quick action and offer it as a chip straight away.
     * @returns {Promise<boolean>} whether it was saved
     */
    async saveQuickAction(label, body, category) {
        if (this.state.saving) {
            return false;
        }
        this.state.saving = true;
        try {
            this.state.skills.push(
                await this.orm.call('muk_ai.skill', 'save_composer_prompt', [
                    label,
                    body,
                    category,
                ]),
            );
            return true;
        } catch (error) {
            this.notification.add(error.data?.message || error.message, {
                type: 'danger',
            });
            return false;
        } finally {
            this.state.saving = false;
        }
    }
    onOpenSkillsOverview() {
        this.props.close?.();
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: _t('Skills'),
            res_model: 'muk_ai.skill',
            views: [
                [false, 'list'],
                [false, 'form'],
            ],
        });
    }
    /**
     * Hand the session to a chat window, along with the way back into the
     * composer for its answers.
     */
    async onOpenInChat() {
        const { sessionId } = this.state;
        if (!sessionId) {
            return;
        }
        const { adapter } = this.props;
        await this.orm.call('muk_ai.session', 'detach_from_composer', [[sessionId]]);
        rememberInsert(sessionId, (text) => {
            if (!adapter.isAlive()) {
                this.notification.add(
                    _t('The message you were writing is no longer open.'),
                    { type: 'warning' },
                );
                return;
            }
            this.applyText(text);
            this.chatWindow.close(sessionId);
        });
        this.chatWindow.open(sessionId);
        this.props.close?.();
    }
}
