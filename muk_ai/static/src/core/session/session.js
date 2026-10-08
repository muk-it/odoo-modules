import { EventBus, markRaw, proxy } from '@odoo/owl';

import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { SelectCreateDialog } from '@web/views/view_dialogs/select_create_dialog';

import { fileToBase64 } from '@muk_ai/core/attachment/attachment';
import { runClientAction } from '@muk_ai/core/client_tools/client_tools';
import { buildRenderedTurns } from '@muk_ai/core/session/turns';
import { formatError } from '@muk_ai/core/utils/utils';

const BUSY = ['running', 'compacting'];
const COMPACT_WARN_RATIO = 0.65;
export const COMPACT_AUTO_RATIO = 0.8;
const STREAM_IDLE_MS = 3000;
const PAGE_SIZE = 100;

/**
 * Slash commands the composer offers, keyed by `/name`, as
 * `{hint, run(session, args), destructive?, opensPicker?, sequence?}`.
 */
export const slashCommands = registry.category('muk_ai.slash_commands');

/**
 * Routes a message is offered to before it is sent, as
 * `async (session, text) => boolean`; a route returning true has taken it.
 */
export const sessionSendRoutes = registry.category('muk_ai.session_send_routes');

/**
 * Handlers of bus event types the core does not handle, as
 * `(payload, session) => void`.
 */
export const sessionEventHandlers = registry.category('muk_ai.session_event_handlers');

/**
 * Session methods that steer the chat. They do nothing on a chat the user may
 * only read, so no surface and no extension needs a guard of its own.
 */
const WRITE_ACTIONS = [
    'send',
    'stop',
    'attach',
    'detach',
    'setAgent',
    'switchAgent',
    'regenerate',
    'cancelQueued',
    'unpin',
    'clear',
    'compact',
    'stopCompact',
    'setApprovalMode',
    'setReasoningEffort',
    'approveTool',
    'approveForSession',
    'rejectTool',
    'answerWithOption',
    'respondYesno',
    'undoToEvent',
    'forkAtEvent',
    'openHandoverPicker',
];

let clientKeySeq = 0;

/**
 * Serialize a value with sorted keys, so equal events give equal strings.
 * @param {*} value the value
 * @returns {string} the canonical JSON
 */
function canonical(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map(canonical).join(',')}]`;
    }
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
}

/**
 * Identify an event by its content, ignoring what only the server or the
 * client adds to it.
 * @param {object} entry the event
 * @returns {string} the content key
 */
function contentKey(entry) {
    const {
        at: _at,
        event_id: _id,
        sequence: _seq,
        _clientKey: _key,
        ...rest
    } = entry || {};
    return canonical(rest);
}

/**
 * Identify an event, by its id once the server stored it.
 * @param {object} entry the event
 * @returns {string} the dedupe key
 */
function eventKey(entry) {
    return entry?.event_id != null ? `id:${entry.event_id}` : contentKey(entry);
}

const HANDLERS = {
    log(payload, session) {
        session.receive(payload);
    },
    text_delta({ delta }, session) {
        if (delta) {
            session.state.streamingText += delta;
            session.bumpStream();
        }
    },
    reasoning_delta({ delta }, session) {
        if (delta) {
            session.state.streamingReasoning += delta;
            session.bumpStream();
        }
    },
    tool_call_start({ call_id, name }, session) {
        const tools = session.state.streamingTools;
        if (call_id && !tools.some((tool) => tool.callId === call_id)) {
            tools.push({ callId: call_id, name: name || '', args: '' });
            session.bumpStream();
        }
    },
    tool_call_args_delta({ call_id, delta }, session) {
        const tool = session.state.streamingTools.find(
            (item) => item.callId === call_id,
        );
        if (tool && delta) {
            tool.args += delta;
            session.bumpStream();
        }
    },
    state(payload, session) {
        const { state, ask, error, ...values } = payload;
        const data = session.data;
        Object.assign(data, values);
        if (state) {
            data.state = state;
            if (!('resume_at' in payload) && state !== 'waiting_schedule') {
                data.resume_at = '';
            }
            if (state === 'running') {
                data.error_message = null;
                session.bumpStream();
            } else {
                session.clearStream();
            }
        }
        if (ask) {
            data.pending_ask = ask;
        } else if (state && state !== 'waiting') {
            data.pending_ask = null;
        }
        if (error) {
            data.error_message = error;
        }
    },
    rename({ name }, session) {
        if (name) {
            session.data.name = name;
        }
    },
    agent_switched({ agent_id, agent_name, ...values }, session) {
        Object.assign(session.data, values, {
            agent_id: agent_id ? [agent_id, agent_name] : false,
        });
    },
    ui_action({ action }, session) {
        if (action && typeof action === 'object') {
            session.chat.runAction(session, action);
        }
    },
    record_written({ model, id }, session) {
        session.chat.reloadThread(model, id);
    },
    view_context({ view_context }, session) {
        session.data.view_context = view_context || null;
    },
    queue({ pending }, session) {
        session.data.pending_user_messages = pending || [];
    },
    compact_delta({ event_id, delta }, session) {
        if (event_id != null && delta) {
            session.updateEvent(event_id, 'compact_progress', (entry) => ({
                ...entry,
                streamed_text: (entry.streamed_text || '') + delta,
            }));
            session.bumpStream();
        }
    },
    compact_update({ event_id, patch }, session) {
        if (event_id != null) {
            session.updateEvent(event_id, 'compact_progress', (entry) => ({
                ...entry,
                ...patch,
            }));
        }
    },
};

/**
 * One AI chat as the client holds it: the server's values in `data`, the
 * transcript and what is typed in `state`, and the actions on the chat.
 *
 * The chat plugin keeps one per chat, so every surface showing it shares the
 * transcript, the draft and the attachments waiting to be sent.
 */
export class AISession {
    constructor(chat, id) {
        this.chat = chat;
        this.id = id;
        this.bus = new EventBus();
        this.holders = 0;
        this.ready = null;
        this.resending = false;
        this.turnsFor = null;
        this.turnsCache = [];
        this.keys = new Set();
        this.loadSeq = 0;
        this.buffer = null;
        this.idleTimer = null;
        this.data = proxy({
            id,
            name: '',
            state: 'new',
            can_write: false,
            user_id: false,
            share_user_ids: [],
            agent_id: false,
            pending_ask: null,
            view_context: null,
            error_message: null,
            pending_user_messages: [],
            reasoning_effort_options: [],
            turn_usage: {},
            resume_at: '',
        });
        this.state = proxy({
            loading: true,
            missing: false,
            events: markRaw([]),
            hasMoreOlder: false,
            oldestSequence: null,
            loadingOlder: false,
            input: '',
            attachments: [],
            streamingText: '',
            streamingReasoning: '',
            streamingTools: [],
            streamIdle: false,
            compactWarned: false,
        });
        for (const name of WRITE_ACTIONS) {
            const action = this[name].bind(this);
            this[name] = (...args) => (this.readonly ? undefined : action(...args));
        }
    }
    get readonly() {
        return !this.state.loading && !this.data.can_write;
    }
    get busy() {
        return BUSY.includes(this.data.state);
    }
    get queueing() {
        return (
            this.busy ||
            (this.data.state === 'waiting' && !!this.data.pending_ask?.queues_input)
        );
    }
    get canSend() {
        const { input, attachments, loading } = this.state;
        return !this.readonly && !loading && !!(input.trim() || attachments.length);
    }
    get canAttach() {
        return !this.readonly && !this.state.loading && this.data.state !== 'running';
    }
    get canStop() {
        return !this.readonly && this.data.state === 'running';
    }
    get canRegenerate() {
        return (
            !this.readonly &&
            !this.busy &&
            this.data.state !== 'waiting' &&
            this.state.events.some((entry) =>
                ['user_message', 'answer'].includes(entry.kind),
            )
        );
    }
    get awaitingApproval() {
        return (
            this.data.state === 'waiting' && this.data.pending_ask?.kind === 'approval'
        );
    }
    get agentName() {
        return this.data.agent_id ? this.data.agent_id[1] : '';
    }
    get ownerName() {
        return this.data.user_id ? this.data.user_id[1] : '';
    }
    get turns() {
        const events = this.state.events;
        if (events !== this.turnsFor) {
            this.turnsFor = events;
            this.turnsCache = buildRenderedTurns(events);
        }
        return this.turnsCache;
    }
    get latestReasoningLine() {
        const lines = this.state.streamingReasoning
            .split(/\n+/)
            .map((line) =>
                line
                    .replace(/^[#*\->\s]+/, '')
                    .replace(/\*+\s*$/, '')
                    .trim(),
            )
            .filter(Boolean);
        return lines.at(-1) || '';
    }
    /**
     * Load the snapshot of the chat into `ready`, replaying the bus events
     * that arrived meanwhile. A chat that cannot be read is flagged `missing`.
     */
    load() {
        const seq = ++this.loadSeq;
        const buffer = (this.buffer = []);
        this.state.loading = true;
        this.ready = this.chat.orm.silent
            .call('muk_ai.session', 'get_snapshot', [this.id])
            .catch(() => null)
            .then((snapshot) => {
                if (seq !== this.loadSeq) {
                    return;
                }
                this.buffer = null;
                this.state.missing = !snapshot;
                this.applySnapshot(snapshot);
                for (const event of buffer) {
                    this.onBusEvent(event);
                }
                this.state.loading = false;
            });
    }
    /**
     * Merge a snapshot: its values into `data`, its window of the newest
     * events over the transcript held, keeping the older events loaded before.
     * @param {object} snapshot what a session RPC answered
     */
    applySnapshot(snapshot) {
        if (snapshot?.id !== this.id) {
            return;
        }
        const { events, has_more_older, oldest_sequence, ...values } = snapshot;
        Object.assign(this.data, values);
        const state = this.state;
        if (events && (events.length || this.data.state !== 'running')) {
            const ownKeys = new Map(
                state.events
                    .filter((entry) => entry._clientKey)
                    .map((entry) => [eventKey(entry), entry._clientKey]),
            );
            const incoming = events.map((entry) => {
                const key =
                    ownKeys.get(`id:${entry.event_id}`) ||
                    ownKeys.get(contentKey(entry));
                return key ? { ...entry, _clientKey: key } : entry;
            });
            const older =
                oldest_sequence == null
                    ? []
                    : state.events.filter((entry) => entry.sequence < oldest_sequence);
            state.events = markRaw([...older, ...incoming]);
            if (!older.length) {
                state.oldestSequence = oldest_sequence ?? null;
                state.hasMoreOlder = !!has_more_older;
            }
            this.keys = new Set(state.events.map(eventKey));
        }
        const streaming =
            state.streamingText ||
            state.streamingReasoning ||
            state.streamingTools.length;
        if (!(this.data.state === 'running' && streaming)) {
            this.clearStream();
        }
    }
    /**
     * Dispatch one `muk_ai.event` bus notification of this chat.
     * @param {object} event `{type, payload}`
     */
    onBusEvent(event) {
        if (this.buffer) {
            this.buffer.push(event);
            return;
        }
        const handle =
            HANDLERS[event.type] || sessionEventHandlers.get(event.type, null);
        handle?.(event.payload || {}, this);
    }
    /**
     * Add a logged event, replacing the optimistic copy it confirms.
     * @param {object} entry the event
     */
    receive(entry) {
        const key = eventKey(entry);
        if (this.keys.has(key)) {
            return;
        }
        this.keys.add(key);
        const twin = contentKey(entry);
        const events = [...this.state.events];
        const index = events.findIndex(
            (item) =>
                item._clientKey && item.event_id == null && contentKey(item) === twin,
        );
        if (index >= 0) {
            events[index] = { ...entry, _clientKey: events[index]._clientKey };
        } else {
            events.push(entry);
        }
        this.state.events = markRaw(events);
        if (entry.kind === 'text') {
            Object.assign(this.state, { streamingText: '', streamingReasoning: '' });
        } else if (entry.kind === 'tool_call') {
            this.state.streamingTools = this.state.streamingTools.filter(
                (tool) => tool.callId !== entry.call_id,
            );
        } else if (entry.kind === 'client_action' && this.holders && !this.readonly) {
            runClientAction(this.chat, this.id, entry);
        }
        if (['text', 'tool_call', 'tool_result'].includes(entry.kind)) {
            this.bumpStream();
        }
    }
    /**
     * Rewrite one logged event in place.
     * @param {number} eventId the event id
     * @param {string} kind the event kind
     * @param {Function} update `(entry) => entry`
     */
    updateEvent(eventId, kind, update) {
        this.state.events = markRaw(
            this.state.events.map((entry) =>
                entry.event_id === eventId && entry.kind === kind
                    ? update(entry)
                    : entry,
            ),
        );
    }
    /**
     * Append an event that exists in this client only.
     * @param {object} entry the event
     */
    pushEvent(entry) {
        this.keys.add(eventKey(entry));
        this.state.events = markRaw([...this.state.events, entry]);
    }
    /**
     * Show a slash command and what it answered in the transcript.
     * @param {string} name the command
     * @param {object} [extra] `summary` or `message`
     */
    appendCommand(name, extra = {}) {
        this.pushEvent({ kind: 'command', name, ...extra });
    }
    bumpStream() {
        this.state.streamIdle = false;
        clearTimeout(this.idleTimer);
        if (this.busy) {
            this.idleTimer = setTimeout(
                () => (this.state.streamIdle = this.busy),
                STREAM_IDLE_MS,
            );
        }
    }
    clearStream() {
        clearTimeout(this.idleTimer);
        Object.assign(this.state, {
            streamingText: '',
            streamingReasoning: '',
            streamingTools: [],
            streamIdle: false,
        });
    }
    /**
     * Load the page of events before the oldest one held.
     */
    async loadMoreEvents() {
        const state = this.state;
        if (state.loadingOlder || !state.hasMoreOlder) {
            return;
        }
        const seq = this.loadSeq;
        state.loadingOlder = true;
        try {
            const page = await this.chat.orm.call(
                'muk_ai.session',
                'fetch_events',
                [this.id],
                {
                    limit: PAGE_SIZE,
                    before_sequence: state.oldestSequence,
                },
            );
            if (seq === this.loadSeq) {
                const known = new Set(state.events.map(eventKey));
                const older = page.events.filter(
                    (entry) => !known.has(eventKey(entry)),
                );
                state.events = markRaw([...older, ...state.events]);
                state.oldestSequence = page.oldest_sequence ?? state.oldestSequence;
                state.hasMoreOlder = !!page.has_more_older;
                this.keys = new Set(state.events.map(eventKey));
            }
        } finally {
            state.loadingOlder = false;
        }
    }
    /**
     * Call a method of this chat, merging the snapshot it answers.
     * @param {string} method the method of `muk_ai.session`
     * @param {Array} args its arguments after the session id
     * @param {string} failure what to report when it fails
     * @param {object} [kwargs] its keyword arguments
     * @returns {Promise<*>} the answer, undefined when it failed
     */
    async run(method, args, failure, kwargs = {}) {
        try {
            const result = await this.callSession(method, args, kwargs);
            this.applySnapshot(result);
            return result;
        } catch (error) {
            this.chat.notification.add(_t('%s: %s', failure, formatError(error)), {
                type: 'danger',
            });
        }
    }
    /**
     * Call a method of this chat.
     * @param {string} method the method of `muk_ai.session`
     * @param {Array} [args] its arguments after the session id
     * @param {object} [kwargs] its keyword arguments
     * @returns {Promise<*>} what it returned
     */
    callSession(method, args = [], kwargs = {}) {
        return this.chat.orm.call('muk_ai.session', method, [this.id, ...args], kwargs);
    }
    /**
     * Send what is typed: to a route that claims it, to the slash command it
     * names, into the queue while a turn runs, or as the next message.
     */
    async send() {
        if (!this.canSend) {
            return;
        }
        const text = this.state.input;
        for (const route of sessionSendRoutes.getAll()) {
            if (await route(this, text)) {
                this.state.input = '';
                this.bus.trigger('sent');
                return;
            }
        }
        const command = this.parseCommand(text);
        if (command) {
            this.state.input = '';
            await command.entry.run(this, command.args);
            this.bus.trigger('sent');
            return;
        }
        const attachments = this.state.attachments;
        Object.assign(this.state, { input: '', attachments: [] });
        this.bus.trigger('sent');
        if (this.queueing) {
            return this.enqueue(text, attachments);
        }
        await this.autoCompact();
        const data = this.data;
        const previous = { state: data.state, pending_ask: data.pending_ask };
        const answering =
            data.state === 'waiting' && data.pending_ask?.kind === 'question';
        const optimistic = answering
            ? {
                  kind: 'answer',
                  answer: text,
                  question: data.pending_ask.text,
                  attachments,
              }
            : { kind: 'user_message', content: text, attachments };
        optimistic._clientKey = `ck${++clientKeySeq}`;
        this.pushEvent(optimistic);
        this.clearStream();
        Object.assign(data, {
            state: 'running',
            pending_ask: null,
            error_message: null,
        });
        const method = answering
            ? 'answer'
            : !data.iteration_count && this.state.events.length <= 1
              ? 'start'
              : 'send_message';
        const drop = () => {
            this.keys.delete(eventKey(optimistic));
            this.state.events = markRaw(
                this.state.events.filter((entry) => entry !== optimistic),
            );
        };
        try {
            const snapshot = await this.callSession(method, [text], {
                attachment_ids: attachments.map((attachment) => attachment.id),
            });
            if (snapshot?.queue_rejected_state) {
                drop();
                return this.resend(snapshot, text, attachments);
            }
            this.applySnapshot(snapshot);
        } catch (error) {
            if (answering) {
                drop();
                Object.assign(data, previous);
            } else {
                data.state = 'error';
            }
            data.error_message = formatError(error);
        }
    }
    /**
     * Queue a message behind the running turn, showing it at once.
     * @param {string} text the message
     * @param {Array} attachments its attachment descriptors
     */
    async enqueue(text, attachments) {
        const entry = { content: text, attachment_ids: attachments.map((a) => a.id) };
        const pending = this.data.pending_user_messages;
        this.data.pending_user_messages = [...pending, entry];
        const remove = () =>
            (this.data.pending_user_messages = this.data.pending_user_messages.filter(
                (item) => item !== entry,
            ));
        try {
            const snapshot = await this.callSession('enqueue_message', [text], {
                attachment_ids: entry.attachment_ids,
            });
            if (snapshot?.queue_rejected_state) {
                remove();
                return this.resend(snapshot, text, attachments);
            }
            this.applySnapshot(snapshot);
        } catch (error) {
            remove();
            this.chat.notification.add(
                _t('%s: %s', _t('Failed to queue message'), formatError(error)),
                { type: 'danger' },
            );
        }
    }
    /**
     * Send again a message the server refused to queue because the turn ended
     * meanwhile, keeping any draft typed since.
     * @param {object} snapshot the snapshot that refused it
     * @param {string} text the message
     * @param {Array} attachments its attachment descriptors
     */
    async resend(snapshot, text, attachments) {
        this.applySnapshot(snapshot);
        if (this.resending) {
            return;
        }
        const draft = { input: this.state.input, attachments: this.state.attachments };
        Object.assign(this.state, { input: text, attachments });
        this.resending = true;
        try {
            await this.send();
        } finally {
            this.resending = false;
        }
        if (draft.input) {
            Object.assign(this.state, draft);
        }
    }
    /**
     * Find the slash command a message names.
     * @param {string} text the message
     * @returns {object|null} `{name, args, entry}`, null when it names none
     */
    parseCommand(text) {
        const [word, ...rest] = text.trim().split(/\s+/);
        const name = word.toLowerCase();
        const entry = word.startsWith('/') && slashCommands.get(name, null);
        return entry ? { name, args: rest.join(' '), entry } : null;
    }
    /**
     * Warn when the context window fills up and compact before it overflows.
     */
    async autoCompact() {
        const { context_window: window, last_input_tokens: tokens } = this.data;
        const ratio = window && tokens ? tokens / window : 0;
        const percent = Math.round(ratio * 100);
        if (ratio >= COMPACT_AUTO_RATIO) {
            await this.compact();
            this.chat.notification.add(
                _t('Auto-compacted: context window was %s%% full.', percent),
                { type: 'info' },
            );
        } else if (ratio >= COMPACT_WARN_RATIO && !this.state.compactWarned) {
            this.state.compactWarned = true;
            this.chat.notification.add(
                _t(
                    'Context window at %s%%. Type /compact to free room before continuing.',
                    percent,
                ),
                { type: 'warning' },
            );
        }
    }
    stop() {
        return this.run('action_stop', [], _t('Failed to stop session'));
    }
    regenerate() {
        if (this.busy || this.data.state === 'waiting') {
            return;
        }
        return this.run('regenerate_last_turn', [], _t('Failed to regenerate'));
    }
    async cancelQueued(index) {
        const pending = this.data.pending_user_messages;
        this.data.pending_user_messages = pending.filter(
            (_item, position) => position !== index,
        );
        if (
            !(await this.run(
                'cancel_queued',
                [index],
                _t('Failed to cancel queued message'),
            ))
        ) {
            this.data.pending_user_messages = pending;
        }
    }
    unpin() {
        if (!this.data.view_context) {
            this.chat.notification.add(_t('No view context is pinned.'), {
                type: 'info',
            });
            return;
        }
        return this.run('unpin_view_context', [], _t('Failed to clear view context'));
    }
    clear() {
        if (this.data.state === 'running') {
            this.chat.notification.add(
                _t('Stop the running session before clearing.'),
                {
                    type: 'warning',
                },
            );
            return;
        }
        return this.run('clear', [], _t('Failed to clear session'));
    }
    compact() {
        if (this.data.state === 'running') {
            this.chat.notification.add(
                _t('Stop the running session before compacting.'),
                {
                    type: 'warning',
                },
            );
            return;
        }
        return this.run('compact', [], _t('Failed to compact conversation'));
    }
    stopCompact() {
        if (this.data.state === 'compacting') {
            return this.run('stop_compact', [], _t('Failed to stop compaction'));
        }
    }
    setApprovalMode(mode) {
        return this.run(
            'set_approval_mode',
            [mode || false],
            _t('Failed to set approval mode'),
        );
    }
    setReasoningEffort(effort) {
        return this.run(
            'set_reasoning_effort',
            [effort || false],
            _t('Failed to set reasoning effort'),
        );
    }
    approveTool() {
        if (this.awaitingApproval) {
            return this.run('approve_tool', [], _t('Failed to approve tool'));
        }
    }
    approveForSession() {
        if (this.awaitingApproval) {
            return this.run('approve_for_session', [], _t('Failed to approve tool'));
        }
    }
    rejectTool(reason = '') {
        if (this.awaitingApproval) {
            return this.run('reject_tool', [], _t('Failed to reject tool'), { reason });
        }
    }
    /**
     * Answer the question asked with one of its options.
     * @param {string} option the option picked
     */
    answerWithOption(option) {
        if (option && this.data.state !== 'running') {
            this.state.input = option;
            return this.send();
        }
    }
    /**
     * Answer a yes/no card: decide a pending approval, or answer a question.
     * @param {string} decision `approve`, `session` or `reject`
     */
    respondYesno(decision) {
        if (this.data.pending_ask?.kind === 'approval') {
            const methods = { approve: 'approveTool', session: 'approveForSession' };
            return this[methods[decision] || 'rejectTool']();
        }
        return this.answerWithOption(decision === 'reject' ? 'Reject' : 'Approve');
    }
    /**
     * Pick the agent of this chat.
     * @param {number|null} agentId the agent, null for the defaults
     */
    async setAgent(agentId) {
        try {
            await this.chat.orm.write('muk_ai.session', [this.id], {
                agent_id: agentId || false,
            });
            const agents = await this.chat.loadAgents();
            const agent = agents.find((item) => item.id === agentId);
            this.data.agent_id = agent ? [agent.id, agent.name] : false;
        } catch (error) {
            this.chat.notification.add(
                _t('%s: %s', _t('Failed to change agent'), formatError(error)),
                { type: 'danger' },
            );
        }
    }
    /**
     * Switch to the agent whose name matches what was typed after `/agent`.
     * @param {string} query the name, or part of it
     */
    async switchAgent(query) {
        const agents = await this.chat.loadAgents();
        const name = query.trim().toLowerCase();
        const target =
            agents.find((agent) => agent.name.toLowerCase() === name) ||
            (name && agents.find((agent) => agent.name.toLowerCase().includes(name)));
        if (target) {
            return this.setAgent(target.id);
        }
        this.chat.notification.add(
            agents.length
                ? _t('No agent matches "%s". Type /agent to pick from the list.', query)
                : _t('No agents available to switch to.'),
            { type: 'warning' },
        );
    }
    /**
     * Upload files to be sent with the next message.
     * @param {File[]} files the files
     */
    async attach(files) {
        if (!files.length) {
            return;
        }
        try {
            const payloads = await Promise.all(files.map(fileToBase64));
            const uploaded = await this.callSession('upload_attachments', [payloads]);
            this.state.attachments = [...this.state.attachments, ...uploaded];
        } catch (error) {
            this.chat.notification.add(
                _t('%s: %s', _t('Attachment upload failed'), formatError(error)),
                { type: 'danger' },
            );
        }
    }
    /**
     * Drop an attachment waiting to be sent.
     * @param {number} attachmentId the attachment
     */
    async detach(attachmentId) {
        this.state.attachments = this.state.attachments.filter(
            (a) => a.id !== attachmentId,
        );
        await this.callSession('discard_attachments', [[attachmentId]]).catch(() => {});
    }
    /**
     * Rewind the chat to before an event, once the user confirmed.
     * @param {number} eventId the first event removed
     */
    async undoToEvent(eventId) {
        if (this.busy || this.data.state === 'waiting') {
            this.chat.notification.add(_t('Stop the session before rewinding.'), {
                type: 'warning',
            });
            return;
        }
        const events = this.state.events;
        const index = events.findIndex((entry) => entry.event_id === eventId);
        const confirmed = await new Promise((resolve) =>
            this.chat.dialog.add(ConfirmationDialog, {
                title: _t('Rewind conversation'),
                body: _t(
                    'Remove this message and the %s event(s) that follow from the conversation? This cannot be undone.',
                    events.length - index - 1,
                ),
                confirmLabel: _t('Rewind'),
                cancelLabel: _t('Cancel'),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            }),
        );
        if (confirmed) {
            await this.run('undo_to_event', [eventId], _t('Failed to rewind'));
        }
    }
    /**
     * Branch the chat into a new one holding the history up to an event.
     * @param {number} eventId the last event copied
     * @returns {Promise<number|undefined>} the new chat, undefined on failure
     */
    async forkAtEvent(eventId) {
        if (this.busy) {
            this.chat.notification.add(_t('Stop the session before forking.'), {
                type: 'warning',
            });
            return;
        }
        const newId = await this.run('fork_at_event', [eventId], _t('Failed to fork'));
        if (newId) {
            this.chat.notification.add(_t('Forked into a new session.'), {
                type: 'success',
            });
            this.chat.events.trigger('created', { id: newId, from: this.id });
        }
        return newId;
    }
    /**
     * Pick a colleague and hand the chat over to them.
     * @param {string} [query] a name to narrow the picker to
     */
    openHandoverPicker(query = '') {
        if (this.busy) {
            this.chat.notification.add(_t('Stop the session before handing it over.'), {
                type: 'warning',
            });
            return;
        }
        const domain = [
            ['share', '=', false],
            ['active', '=', true],
            ['id', '!=', this.data.user_id?.[0] || false],
            ...(query ? [['name', 'ilike', query]] : []),
        ];
        this.chat.dialog.add(SelectCreateDialog, {
            resModel: 'res.users',
            title: _t('Hand over chat to...'),
            domain,
            noCreate: true,
            multiSelect: false,
            context: {
                list_view_ref: 'muk_ai.view_res_users_list_handover',
                kanban_view_ref: 'muk_ai.view_res_users_kanban_handover',
                search_view_ref: 'muk_ai.view_res_users_search_handover',
            },
            onSelected: async ([userId]) => {
                if (
                    userId &&
                    (await this.run(
                        'action_handover',
                        [userId],
                        _t('Failed to hand over'),
                    ))
                ) {
                    this.chat.notification.add(_t('Chat handed over.'), {
                        type: 'success',
                    });
                    this.chat.forget(this.id);
                }
            },
        });
    }
    /**
     * Open the view the chat is pinned to.
     */
    openPinnedContext() {
        const context = this.data.view_context;
        if (!context?.model) {
            return;
        }
        const record = context.kind === 'record';
        const action = {
            type: 'ir.actions.act_window',
            res_model: context.model,
            views: [[false, record ? 'form' : context.view_type || 'list']],
        };
        if (record) {
            action.res_id = context.id;
        } else if (Array.isArray(context.domain)) {
            action.domain = context.domain;
        }
        this.chat.runAction(this, action);
    }
    /**
     * Ask the surfaces showing this chat to open the artifacts panel.
     * @param {string} tab the artifact type
     * @param {*} [itemId] the item to single out in it
     */
    focusArtifact(tab, itemId = null) {
        this.bus.trigger('artifact', { tab, itemId });
    }
}

slashCommands
    .add('/help', {
        hint: _t('Show available slash commands'),
        run: (session) =>
            session.appendCommand('/help', {
                summary: slashCommands
                    .getEntries()
                    .map(([name, command]) => `**${name}**: ${command.hint}`)
                    .join('\n\n'),
            }),
    })
    .add('/compact', {
        hint: _t('Summarize and collapse older turns to free context'),
        run: (session) => session.compact(),
    })
    .add('/clear', {
        hint: _t('Start a fresh conversation in this session'),
        destructive: true,
        run: (session) => session.clear(),
    })
    .add('/unpin', {
        hint: _t('Clear the view context pinned to this session'),
        run: (session) => session.unpin(),
    })
    .add('/agent', {
        hint: _t('Switch the active agent'),
        opensPicker: true,
        run: (session, args) => session.switchAgent(args),
    })
    .add('/handover', {
        hint: _t('Transfer this chat to another user'),
        run: (session, args) => session.openHandoverPicker(args),
    });
