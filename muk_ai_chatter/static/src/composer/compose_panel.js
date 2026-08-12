import { Component, onMounted, onWillStart, onWillUnmount, useState } from '@odoo/owl';

import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { useSessionChannel } from '@muk_ai/chat/session/session_channel';

import { rememberInsert } from '@muk_ai_chatter/composer/chat_insert';
import { wordDiff } from '@muk_ai_chatter/composer/word_diff';

export const LENGTHS = [
    { id: 'shorter', label: _t('Shorter'), directive: 'Keep it noticeably shorter.' },
    { id: 'as_is', label: _t('As is'), directive: '' },
    { id: 'longer', label: _t('Longer'), directive: 'Take a little more room.' },
];

export const TERMINAL_STATES = ['done', 'stopped', 'error'];

// What can be done to something already written, and what can be written from
// nothing: a skill lands in the right one by the category it carries.
export const REWRITE_CATEGORIES = ['fix', 'rewrite', 'transform'];

export const GENERATE_CATEGORIES = ['generate'];

// Wording for a category that holds more than one skill, where the skills
// themselves are behind the button rather than on it.
export const CATEGORIES = {
    fix: { label: _t('Fix'), icon: 'fa-check' },
    rewrite: { label: _t('Rewrite'), icon: 'fa-pencil' },
    transform: { label: _t('Transform'), icon: 'fa-language' },
    generate: { label: _t('Write'), icon: 'fa-magic' },
};

// Closes whichever helper is on screen. A panel stays open through a click
// elsewhere on purpose, so opening the full composer over a chatter that has
// one — or a second html field in the same view — would otherwise leave two
// helpers stacked, each writing into a different composer.
let closeOpenPanel = null;

export const TONES = [
    { id: 'neutral', label: _t('Neutral'), directive: '' },
    { id: 'formal', label: _t('Formal'), directive: 'Write in a formal register.' },
    {
        id: 'friendly',
        label: _t('Friendly'),
        directive: 'Write in a warm, friendly tone.',
    },
];

/**
 * The writing helper offered inside a composer.
 *
 * What it offers follows what is already written: a selection is rewritten in
 * place, a draft nobody selected is rewritten as a whole, and an empty composer
 * is offered what can be written from the record, with a length and a tone
 * chosen before anything is generated. A rewrite shows what it changed as a
 * diff. Nothing reaches the composer until the user accepts it.
 */
export class ComposePanel extends Component {
    static template = 'muk_ai_chatter.ComposePanel';
    static props = {
        adapter: Object,
        close: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService('orm');
        this.bus = useService('bus_service');
        this.chatWindow = useService('muk_ai.chat_window');
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
        });
        this.busHandler = (event) => this.onSessionEvent(event);
        this.bus.subscribe('muk_ai.event', this.busHandler);
        // The session is its own bus channel, and the panel is told about a
        // run only for as long as it is subscribed to the one it holds — which
        // is why the id lives in the reactive state rather than on the
        // instance: the subscription follows whatever it is set to.
        useSessionChannel(() => this.state.sessionId);
        // Registered globally: the panel is opened from an editor toolbar as
        // well, and there the focus stays in the editable behind it, so a
        // keydown on the panel itself would never be seen.
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
            if (closeOpenPanel === close) {
                closeOpenPanel = null;
            }
            this.bus.unsubscribe('muk_ai.event', this.busHandler);
            this.discardUnusedSession();
        });
    }

    // ----------------------------------------------------------
    // Getters
    // ----------------------------------------------------------

    get lengths() {
        return LENGTHS;
    }
    get tones() {
        return TONES;
    }
    get hasSelection() {
        return Boolean(this.state.selection);
    }
    /**
     * What a rewrite works on: the selection, or the whole draft when there is
     * none. Somebody who wrote a message and asks to shorten it means that
     * message, not a new one.
     * @returns {string} the text to rewrite, empty when there is nothing yet
     */
    get target() {
        return this.state.selection || this.state.draft;
    }
    get isRewrite() {
        return Boolean(this.target);
    }
    get offered() {
        const wanted = this.isRewrite ? REWRITE_CATEGORIES : GENERATE_CATEGORIES;
        return this.state.skills.filter((skill) => wanted.includes(skill.category));
    }
    /**
     * What the panel offers at rest: one action per category, in order.
     *
     * A category holding a single skill is that skill, named after it — there
     * is nothing to choose once it is picked. A category holding several, and
     * writing from nothing, open a row underneath instead of firing straight
     * away, so the panel stays one line until the user has said what they want.
     *
     * @returns {object[]} the actions, each carrying the skills behind it
     */
    get groups() {
        const order = this.isRewrite ? REWRITE_CATEGORIES : GENERATE_CATEGORIES;
        return order
            .map((category) => {
                const skills = this.offered.filter(
                    (skill) => skill.category === category,
                );
                const alone = skills.length === 1;
                const opens = !alone || category === 'generate';
                return {
                    category,
                    skills,
                    opens,
                    modifiers: category === 'generate',
                    label: alone ? skills[0]?.label : CATEGORIES[category].label,
                    icon: alone ? skills[0]?.icon : CATEGORIES[category].icon,
                };
            })
            .filter((group) => group.skills.length);
    }
    get openGroup() {
        return this.groups.find((group) => group.category === this.state.opened);
    }
    get isRunning() {
        return this.state.phase === 'running';
    }
    get preview() {
        return this.state.phase === 'running'
            ? this.state.streaming
            : this.state.result;
    }
    get diff() {
        if (!this.isRewrite || this.state.phase !== 'preview') {
            return null;
        }
        return wordDiff(this.target, this.state.result);
    }
    /**
     * What the error pill says: the reason, without the provider's plumbing.
     *
     * A failure arrives as one long line — the request, the host, the port,
     * the retry count. The first clause is the part a user can act on; the
     * rest stays in the tooltip for whoever has to report it.
     *
     * @returns {string} a line that fits on the pill
     */
    get errorLabel() {
        const first = (this.state.error || '').split(/[:(]/)[0].trim();
        if (!first) {
            return _t('The run failed.');
        }
        return first.length > 48 ? `${first.slice(0, 48)}…` : first;
    }
    get busyLabel() {
        return this.state.label ? _t('%s…', this.state.label) : _t('Writing…');
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
        if (this.isRewrite) {
            const words = this.target.trim().split(/\s+/).length;
            if (words === 1) {
                return this.hasSelection
                    ? _t('1 selected word')
                    : _t('1 word in your draft');
            }
            return this.hasSelection
                ? _t('%s selected words', words)
                : _t('%s words in your draft', words);
        }
        return _t('Written from this record');
    }
    get quoted() {
        const target = this.target.trim();
        return target.length > 180 ? `${target.slice(0, 180)}…` : target;
    }

    // ----------------------------------------------------------
    // Helper
    // ----------------------------------------------------------

    /**
     * Show why something did not work, in the panel rather than as a dialog.
     * @param {Error} error what the server or the network reported
     */
    reportError(error) {
        this.state.phase = 'error';
        this.state.error = error.data?.message || error.message || String(error);
    }
    /**
     * Open the session the helper answers from, before anything is asked.
     *
     * Opening it with the panel rather than with the first chip is what makes
     * that first click answer straight away.
     *
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
    /**
     * Drop the session again when the panel closes without having used it.
     */
    discardUnusedSession() {
        if (!this.state.sessionId || this.state.asked) {
            return;
        }
        this.orm.silent
            .call('muk_ai.session', 'discard_unused_composer', [[this.state.sessionId]])
            .catch(() => {});
    }
    /**
     * Return the instruction sent for a chip, with the chosen modifiers.
     * @param {string} prompt the instruction the chip carries
     * @returns {string} the instruction the agent receives
     */
    buildPrompt(prompt) {
        const parts = [prompt];
        if (!this.isRewrite) {
            const length = LENGTHS.find((entry) => entry.id === this.state.length);
            const tone = TONES.find((entry) => entry.id === this.state.tone);
            if (length?.directive) {
                parts.push(length.directive);
            }
            if (tone?.directive) {
                parts.push(tone.directive);
            }
        }
        return parts.join(' ');
    }
    /**
     * Accumulate the streamed answer and close the run when it ends.
     * @param {object} event the payload pushed on the muk_ai bus
     */
    onSessionEvent(event) {
        if (!event || event.session_id !== this.state.sessionId || !this.isRunning) {
            return;
        }
        if (event.type === 'text_delta') {
            this.state.streaming += event.payload?.delta || '';
        } else if (event.type === 'state') {
            const state = event.payload?.state;
            if (state === 'done' || state === 'stopped') {
                this.finish();
            } else if (state === 'error') {
                this.state.phase = 'error';
                this.state.error = event.payload?.error || _t('The run failed.');
            }
        }
    }
    /**
     * Read the finished answer back and offer it for review.
     *
     * The state is read along with the text because a run publishes `done`
     * without being over: compacting itself, or emptying a queue of turns,
     * both announce one from the middle of the work. Only a session that has
     * come to rest is offered as an answer.
     *
     * @returns {Promise<void>}
     */
    async finish() {
        let session;
        try {
            [session] = await this.orm.read(
                'muk_ai.session',
                [this.state.sessionId],
                ['last_text', 'state'],
            );
        } catch (error) {
            this.reportError(error);
            return;
        }
        if (!session || !TERMINAL_STATES.includes(session.state)) {
            return;
        }
        const text = (session.last_text || this.state.streaming || '').trim();
        if (!text) {
            this.state.phase = 'error';
            this.state.error = _t('The agent returned nothing.');
            return;
        }
        this.state.result = text;
        this.state.phase = 'preview';
    }

    // ----------------------------------------------------------
    // Actions
    // ----------------------------------------------------------

    /**
     * Ask for one rewrite or one draft and stream what comes back.
     * @param {string} label wording shown while it runs
     * @param {string} prompt the instruction the chip carries
     * @returns {Promise<void>}
     */
    async run(label, prompt) {
        if (this.isRunning) {
            return;
        }
        if (!this.state.sessionId && !(await this.openSession())) {
            return;
        }
        this.state.label = label;
        this.state.asked = prompt;
        this.state.opened = '';
        this.state.streaming = '';
        this.state.result = '';
        this.state.error = '';
        this.state.phase = 'running';
        const instruction = this.buildPrompt(prompt);
        try {
            // The part to rewrite is sent as the selection even when the user
            // selected nothing: picking "shorten" with a message already
            // written means that message.
            await this.orm.call('muk_ai.session', 'update_compose_context', [
                [this.state.sessionId],
                this.props.adapter.getDraft(),
                this.isRewrite ? this.target : '',
            ]);
            await this.orm.call('muk_ai.session', 'send_message', [
                [this.state.sessionId],
                instruction,
            ]);
        } catch (error) {
            this.reportError(error);
        }
    }
    setLength(id) {
        this.state.length = id;
    }
    setTone(id) {
        this.state.tone = id;
    }
    onSkillClick(skill) {
        this.run(skill.label, skill.body);
    }
    /**
     * Run what was picked, or reveal what there is to pick.
     * @param {object} group one entry of {@link groups}
     */
    onGroupClick(group) {
        if (!group.opens) {
            this.onSkillClick(group.skills[0]);
            return;
        }
        this.state.opened = this.state.opened === group.category ? '' : group.category;
    }
    onCustomKeydown(ev) {
        if (ev.key === 'Enter') {
            this.onCustomSubmit();
        }
    }
    onCustomSubmit() {
        const asked = this.state.custom.trim();
        if (asked) {
            this.state.custom = '';
            this.run(_t('Writing'), asked);
        }
    }
    /**
     * Put an answer where the user was writing.
     *
     * Over the selection when there was one, over the whole message when the
     * request was to rewrite it, and at the cursor otherwise.
     *
     * @param {string} text what the agent wrote
     */
    applyText(text) {
        if (this.hasSelection) {
            this.props.adapter.applySelection(text);
        } else if (this.isRewrite) {
            this.props.adapter.replaceDraft(text);
        } else {
            this.props.adapter.applyDraft(text);
        }
    }
    onAccept() {
        this.applyText(this.state.result);
        this.props.close?.();
    }
    onDiscard() {
        this.state.phase = 'idle';
        this.state.result = '';
        this.state.streaming = '';
    }
    /**
     * Stop a run the user no longer wants to wait for.
     * @returns {Promise<void>}
     */
    async onCancel() {
        this.state.phase = 'idle';
        this.state.streaming = '';
        if (this.state.sessionId) {
            await this.orm.silent
                .call('muk_ai.session', 'action_stop', [[this.state.sessionId]])
                .catch(() => {});
        }
    }
    onRetry() {
        if (this.state.asked) {
            this.run(this.state.label, this.state.asked);
        }
    }
    /**
     * Hand the session to the chat window, where the user can keep talking.
     *
     * The way back is handed over with it: the panel closes, so without it a
     * user who talked the draft through in the chat window would be left
     * copying it out by hand. Where an answer goes is decided here, while the
     * panel still knows what was selected.
     *
     * @returns {Promise<void>}
     */
    async onOpenInChat() {
        if (!this.state.sessionId) {
            return;
        }
        const sessionId = this.state.sessionId;
        const chatWindow = this.chatWindow;
        const notification = this.notification;
        const adapter = this.props.adapter;
        const apply = (text) => this.applyText(text);
        await this.orm.call('muk_ai.session', 'detach_from_composer', [[sessionId]]);
        rememberInsert(sessionId, (text) => {
            // The chat outlives the message: somebody who sends or drops it
            // and keeps talking has nowhere left to put an answer, and
            // writing into an editor that is gone throws at them instead.
            if (!adapter.isAlive()) {
                notification.add(
                    _t('The message you were writing is no longer open.'),
                    { type: 'warning' },
                );
                return;
            }
            apply(text);
            chatWindow.close(sessionId);
        });
        chatWindow.open(sessionId);
        this.props.close?.();
    }
}
