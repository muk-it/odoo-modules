// @odoo-module

import { markup, onWillUnmount, useEnv, useState } from '@odoo/owl';

import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { SelectCreateDialog } from '@web/views/view_dialogs/select_create_dialog';

import { fileToBase64 } from '@muk_ai/core/attachment/file_helpers';
import { renderMarkdown as renderMarkdownToHtml } from '@muk_ai/core/markdown/markdown';
import { busSubscribe, busUnsubscribe } from '@muk_ai/core/compat/bus';
import { formatError } from '@muk_ai/chat/utils';

import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import { useOpenSession } from '@muk_ai/chat/session/open_sessions';
import { useSessionChannel } from '@muk_ai/chat/session/session_channel';

/**
 * Session fields an addon needs in the client state, beyond the core's own.
 *
 * Each entry is `{field, apply}`: the field is read with the session, and
 * `apply(state, record)` copies it in once the core fields have landed.
 */
export const sessionStateFields = registry.category('muk_ai.session_state_fields');

export const SESSION_READ_FIELDS = [
    'id',
    'name',
    'state',
    'pending_ask',
    'view_context',
    'last_text',
    'error_message',
    'iteration_count',
    'total_input_tokens',
    'total_output_tokens',
    'last_input_tokens',
    'context_window',
    'user_id',
    'share_user_ids',
    'agent_id',
    'total_cost',
    'override_approval_mode',
    'effective_approval_mode',
    'override_reasoning_effort',
    'effective_reasoning_effort',
    'reasoning_effort_options',
    'agent_reasoning_effort',
    'pending_user_messages',
    'can_write',
];

export const SLASH_COMMANDS = [
    {
        name: '/help',
        hint: 'Show available slash commands',
    },
    {
        name: '/compact',
        hint: 'Summarize and collapse older turns to free context',
    },
    {
        name: '/clear',
        hint: 'Start a fresh conversation in this session',
        destructive: true,
    },
    {
        name: '/unpin',
        hint: 'Clear the view context pinned to this session',
    },
    {
        name: '/agent',
        hint: 'Switch the active agent',
        opensPicker: true,
    },
    {
        name: '/handover',
        hint: 'Transfer this chat to another user',
    },
];

export const sessionSlashCommands = registry.category('muk_ai.slash_commands');

/**
 * Return every slash command the composer should offer, core and addon.
 * @returns {Array} `{name, hint}` entries
 */
export function allSlashCommands() {
    return [...SLASH_COMMANDS, ...sessionSlashCommands.getAll()];
}

/**
 * Build a send route answering slash commands with a single session call.
 *
 * The core's slash dispatcher is a fixed chain an addon cannot extend, so an
 * addon command rides the send routes instead.
 * @param {object} commands map of `/command` to the session method it calls
 * @returns {Function} a route for `sessionSendRoutes`
 */
export function commandRoute(commands) {
    return async ({ state, orm, appendCommand }, text) => {
        const [name, ...rest] = (text || '').trim().split(/\s+/);
        // The core's parser lowercases too, so /Remember is the same command.
        const method = commands[name.toLowerCase()];
        if (!method) {
            return false;
        }
        if (state.sessionId) {
            const summary = await orm.call('muk_ai.session', method, [
                state.sessionId,
                rest.join(' '),
            ]);
            appendCommand(name, { summary });
        }
        return true;
    };
}

/**
 * Session actions that steer the chat rather than read it. They are all
 * neutralised at once on a read-only chat, so no surface and no extension
 * has to remember a guard of its own.
 */
const WRITE_ACTIONS = [
    'onSend',
    'onStop',
    'onAttachFiles',
    'onRemoveAttachment',
    'setAgent',
    'onSetAgent',
    'onRegenerate',
    'cancelQueued',
    'runUnpin',
    'setApprovalMode',
    'cycleApprovalMode',
    'setReasoningEffort',
    'approveTool',
    'approveForSession',
    'rejectTool',
    'answerWithOption',
    'respondYesno',
    'runStopCompact',
    'runUndoToEvent',
    'runForkAtEvent',
    'openHandoverPicker',
];

/**
 * Registry of live-update handlers for bus event types the core does not
 * handle, keyed by event type. Each handler has the signature
 * `(payload, session) => void`, where `session` exposes the reactive
 * `state`, `updateEvent(eventId, kind, update)` rewriting one logged event
 * in place through `update(entry) => entry`, `bumpStreamActivity()` and
 * `requestScroll()`.
 */
export const sessionEventHandlers = registry.category('muk_ai.session_event_handlers');

/**
 * Routes the composer's send is offered to first, as
 * `({state, orm, appendCommand}, text) => Promise<boolean>`.
 *
 * A route returning true has taken the message. It lives on the session so
 * that every way of sending goes through it, voice mode included.
 */
export const sessionSendRoutes = registry.category('muk_ai.session_send_routes');

const COMPACT_WARN_RATIO = 0.65;
const COMPACT_AUTO_RATIO = 0.8;
const STREAM_IDLE_MS = 3000;

let clientKeySeq = 0;

/**
 * Hook owning an AI chat session: state, streaming, tool calls, and commands.
 * @param {object} [options] session hook options (callbacks, defaults)
 * @returns {object} reactive session API consumed by chat components
 */
export function useAiSession(options = {}) {
    const orm = useService('orm');
    const user = useService('user');
    const busEnv = useEnv();
    const bus = busEnv.services.bus_service;
    const notification = useService('notification');
    const actionService = useService('action');
    const dialog = useService('dialog');
    const sessionNotification = useService('muk_ai.session_notification');
    const env = useEnv();
    const surface = options.surface || 'window';
    const state = useState({
        sessionId: null,
        name: '',
        status: 'new',
        loading: true,
        events: [],
        oldestSequence: null,
        hasMoreOlder: false,
        loadingOlder: false,
        pendingAsk: null,
        error: null,
        input: '',
        iterationCount: 0,
        inputTokens: 0,
        outputTokens: 0,
        totalCost: 0,
        lastInputTokens: 0,
        contextWindow: 0,
        expandedTools: {},
        streamingText: '',
        streamingReasoning: '',
        streamingTools: [],
        pendingAttachments: [],
        focusToken: 0,
        agents: [],
        agentId: null,
        agentName: '',
        ownerId: null,
        ownerName: '',
        shareIds: [],
        readonly: false,
        autoCompactPending: false,
        viewContext: null,
        approvalMode: false,
        effectiveApprovalMode: 'ask',
        reasoningEffort: false,
        effectiveReasoningEffort: false,
        reasoningEffortOptions: [],
        agentReasoningEffort: false,
        pendingMessages: [],
        streamIdle: false,
        resumeAt: '',
        artifactsFocus: null,
    });
    let eventKeys = new Set();
    let onScrollCallback = null;
    let streamIdleTimer = null;
    let loadSeq = 0;
    let pendingLoad = null;
    let requeueRerouting = false;
    const busHandler = (payload) => onBusEvent(payload);
    busSubscribe(bus, 'muk_ai.event', busHandler);
    useSessionChannel(() => state.sessionId);
    useOpenSession(() => (state.readonly ? null : state.sessionId));
    function clearStreamIdleTimer() {
        if (streamIdleTimer) {
            clearTimeout(streamIdleTimer);
            streamIdleTimer = null;
        }
    }
    function bumpStreamActivity() {
        state.streamIdle = false;
        clearStreamIdleTimer();
        const status = state.status;
        if (status !== 'running' && status !== 'compacting') {
            return;
        }
        streamIdleTimer = setTimeout(() => {
            streamIdleTimer = null;
            const current = state.status;
            if (current === 'running' || current === 'compacting') {
                state.streamIdle = true;
            }
        }, STREAM_IDLE_MS);
    }
    function contentKey(entry) {
        const { at: _at, event_id: _id, _clientKey: _ck, ...rest } = entry || {};
        return canonicalStringify(rest);
    }
    function eventKey(entry) {
        if (entry && entry.event_id != null) {
            return 'id:' + entry.event_id;
        }
        return contentKey(entry);
    }
    function canonicalStringify(value) {
        if (value === null || typeof value !== 'object') {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return '[' + value.map(canonicalStringify).join(',') + ']';
        }
        const keys = Object.keys(value).sort();
        return (
            '{' +
            keys
                .map((k) => JSON.stringify(k) + ':' + canonicalStringify(value[k]))
                .join(',') +
            '}'
        );
    }
    function onBusEvent(event) {
        if (!event) {
            return;
        }
        if (pendingLoad && event.session_id === pendingLoad.sessionId) {
            pendingLoad.buffer.push(event);
            return;
        }
        if (event.session_id !== state.sessionId) {
            return;
        }
        if (event.type === 'log') {
            const key = eventKey(event.payload);
            if (eventKeys.has(key)) {
                return;
            }
            eventKeys.add(key);
            const twinKey = contentKey(event.payload);
            const twinIndex = state.events.findIndex(
                (entry) =>
                    entry &&
                    entry._clientKey &&
                    entry.event_id == null &&
                    contentKey(entry) === twinKey,
            );
            if (twinIndex >= 0) {
                const next = [...state.events];
                next[twinIndex] = {
                    ...event.payload,
                    _clientKey: next[twinIndex]._clientKey,
                };
                state.events = next;
            } else {
                state.events = [...state.events, event.payload];
            }
            const kind = event.payload?.kind;
            if (kind === 'text') {
                state.streamingText = '';
                state.streamingReasoning = '';
            } else if (kind === 'tool_call') {
                state.streamingTools = state.streamingTools.filter(
                    (t) => t.callId !== event.payload.call_id,
                );
            }
            if (kind === 'text' || kind === 'tool_call' || kind === 'tool_result') {
                bumpStreamActivity();
            }
            requestScroll();
        } else if (event.type === 'text_delta') {
            const delta = (event.payload || {}).delta || '';
            if (delta) {
                state.streamingText = (state.streamingText || '') + delta;
                bumpStreamActivity();
                requestScroll();
            }
        } else if (event.type === 'reasoning_delta') {
            const delta = (event.payload || {}).delta || '';
            if (delta) {
                state.streamingReasoning = (state.streamingReasoning || '') + delta;
                bumpStreamActivity();
                requestScroll();
            }
        } else if (event.type === 'tool_call_start') {
            const callId = event.payload?.call_id;
            if (!callId) {
                return;
            }
            if (!state.streamingTools.some((t) => t.callId === callId)) {
                state.streamingTools = [
                    ...state.streamingTools,
                    { callId, name: event.payload?.name || '', argsBuffer: '' },
                ];
                bumpStreamActivity();
                requestScroll();
            }
        } else if (event.type === 'tool_call_args_delta') {
            const { call_id: callId, delta } = event.payload || {};
            if (!callId || !delta) {
                return;
            }
            state.streamingTools = state.streamingTools.map((t) =>
                t.callId === callId
                    ? { ...t, argsBuffer: (t.argsBuffer || '') + delta }
                    : t,
            );
            bumpStreamActivity();
            requestScroll();
        } else if (event.type === 'tool_call_result') {
            const { call_id: callId, result } = event.payload || {};
            if (!callId) {
                return;
            }
            state.streamingTools = state.streamingTools.map((t) =>
                t.callId === callId
                    ? { ...t, done: true, result: result === undefined ? null : result }
                    : t,
            );
            bumpStreamActivity();
            requestScroll();
        } else if (event.type === 'state') {
            if (event.payload.state) {
                state.status = event.payload.state;
                if (event.payload.state !== 'running') {
                    state.streamingText = '';
                    state.streamingReasoning = '';
                    state.streamingTools = [];
                    state.streamIdle = false;
                    clearStreamIdleTimer();
                } else {
                    bumpStreamActivity();
                }
            }
            if (event.payload.ask) {
                state.pendingAsk = event.payload.ask;
            } else if (event.payload.state && event.payload.state !== 'waiting') {
                state.pendingAsk = null;
            }
            if (event.payload.error) {
                state.error = event.payload.error;
            }
            if (typeof event.payload.last_input_tokens === 'number') {
                state.lastInputTokens = event.payload.last_input_tokens;
            }
            if (typeof event.payload.context_window === 'number') {
                state.contextWindow = event.payload.context_window;
            }
            if (typeof event.payload.total_cost === 'number') {
                state.totalCost = event.payload.total_cost;
            }
            if (event.payload.resume_at !== undefined) {
                state.resumeAt = normalizeResumeAt(event.payload.resume_at);
            } else if (
                event.payload.state &&
                event.payload.state !== 'waiting_schedule'
            ) {
                state.resumeAt = '';
            }
        } else if (event.type === 'rename') {
            if (event.payload && event.payload.name) {
                state.name = event.payload.name;
            }
        } else if (event.type === 'agent_switched') {
            const payload = event.payload || {};
            state.agentId = payload.agent_id || null;
            state.agentName = payload.agent_name || '';
            if (payload.effective_approval_mode) {
                state.effectiveApprovalMode = payload.effective_approval_mode;
            }
            if (payload.reasoning_effort_options) {
                state.effectiveReasoningEffort = payload.effective_reasoning_effort;
                state.reasoningEffortOptions = payload.reasoning_effort_options;
                state.agentReasoningEffort = payload.agent_reasoning_effort;
            }
        } else if (event.type === 'ui_action') {
            handleUiAction(event.payload);
        } else if (event.type === 'view_context') {
            state.viewContext = (event.payload || {}).view_context || null;
        } else if (event.type === 'queue') {
            state.pendingMessages = (event.payload || {}).pending || [];
        } else if (event.type === 'compact_delta') {
            const eventId = (event.payload || {}).event_id;
            const delta = (event.payload || {}).delta || '';
            if (eventId == null || !delta) {
                return;
            }
            updateEvent(eventId, 'compact_progress', (entry) => ({
                ...entry,
                streamed_text: (entry.streamed_text || '') + delta,
            }));
            bumpStreamActivity();
            requestScroll();
        } else if (event.type === 'compact_update') {
            const eventId = (event.payload || {}).event_id;
            const patch = (event.payload || {}).patch || {};
            if (eventId == null) {
                return;
            }
            updateEvent(eventId, 'compact_progress', (entry) => ({
                ...entry,
                ...patch,
            }));
            requestScroll();
        } else {
            const handle = sessionEventHandlers.get(event.type, null);
            if (handle) {
                handle(event.payload || {}, {
                    state,
                    updateEvent,
                    bumpStreamActivity,
                    requestScroll,
                });
            }
        }
    }
    function updateEvent(eventId, kind, update) {
        state.events = state.events.map((entry) =>
            entry && entry.event_id === eventId && entry.kind === kind
                ? update(entry)
                : entry,
        );
    }
    async function handleUiAction(payload) {
        const action = payload && payload.action;
        if (!action || typeof action !== 'object') {
            return;
        }
        try {
            maybePopoutBeforeAction();
            await actionService.doAction(action);
        } catch (error) {
            notification.add(
                _t('Failed to execute UI action: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    function maybePopoutBeforeAction() {
        if (surface !== 'fullscreen' || !state.sessionId) {
            return;
        }
        const chatWindow = env.services?.['muk_ai.chat_window'];
        if (!chatWindow || typeof chatWindow.open !== 'function') {
            return;
        }
        chatWindow.open(state.sessionId);
    }
    /**
     * Load a session into the state, or clear it when it cannot be read.
     * A session that is gone or not shared with this user falls back to the
     * empty new-chat state: keeping its id and flagging the state read-only
     * would advertise a missing session as one somebody shared, and leave
     * the user with no composer.
     * @param {number|null} sessionId
     * @returns {Promise<object|null>} the loaded record, null when unusable
     */
    async function load(sessionId) {
        const seq = ++loadSeq;
        const previousSessionId = state.sessionId;
        state.loading = true;
        if (!sessionId) {
            pendingLoad = null;
            sessionNotification.markInactive(previousSessionId);
            clearStreamIdleTimer();
            _resetSessionState(null);
            state.loading = false;
            return null;
        }
        const myLoad = { sessionId, buffer: [] };
        pendingLoad = myLoad;
        let record = null;
        let snapshot = null;
        let loadError = null;
        try {
            const [result] = await orm.read(
                'muk_ai.session',
                [sessionId],
                [
                    ...SESSION_READ_FIELDS,
                    ...sessionStateFields.getAll().map((entry) => entry.field),
                ],
            );
            record = result || null;
            if (record) {
                try {
                    snapshot = await orm.call('muk_ai.session', 'get_snapshot', [
                        sessionId,
                    ]);
                } catch {
                    snapshot = null;
                }
            }
        } catch (error) {
            loadError = error;
        }
        if (seq !== loadSeq) {
            return record;
        }
        sessionNotification.markInactive(previousSessionId);
        clearStreamIdleTimer();
        if (pendingLoad === myLoad) {
            pendingLoad = null;
        }
        if (loadError || !record) {
            _resetSessionState(null);
            state.loading = false;
            return null;
        }
        _resetSessionState(sessionId);
        sessionNotification.markActive(sessionId);
        applyRecord(record);
        if (snapshot && snapshot.events !== undefined) {
            state.events = snapshot.events || [];
            state.oldestSequence = snapshot.oldest_sequence ?? null;
            state.hasMoreOlder = !!snapshot.has_more_older;
            rebuildEventKeys();
        }
        for (const buffered of myLoad.buffer) {
            onBusEvent(buffered);
        }
        state.loading = false;
        return record;
    }
    function _resetSessionState(sessionId) {
        state.sessionId = sessionId;
        state.ownerId = null;
        state.ownerName = '';
        state.shareIds = [];
        state.readonly = !!sessionId;
        state.input = '';
        state.error = null;
        state.pendingAsk = null;
        state.events = [];
        state.oldestSequence = null;
        state.hasMoreOlder = false;
        state.loadingOlder = false;
        state.streamingText = '';
        state.streamingReasoning = '';
        state.streamingTools = [];
        state.pendingAttachments = [];
        state.streamIdle = false;
        state.resumeAt = '';
        eventKeys = new Set();
    }
    function applySessionFields(payload) {
        state.status = payload.state;
        state.pendingAsk = payload.pending_ask || null;
        state.viewContext = payload.view_context || null;
        state.approvalMode = payload.override_approval_mode || false;
        state.effectiveApprovalMode = payload.effective_approval_mode || 'ask';
        state.reasoningEffort = payload.override_reasoning_effort || false;
        state.effectiveReasoningEffort = payload.effective_reasoning_effort || false;
        state.reasoningEffortOptions = payload.reasoning_effort_options || [];
        state.agentReasoningEffort = payload.agent_reasoning_effort || false;
        state.error = payload.error_message || null;
        state.iterationCount = payload.iteration_count || 0;
        state.inputTokens = payload.total_input_tokens || 0;
        state.outputTokens = payload.total_output_tokens || 0;
        state.lastInputTokens = payload.last_input_tokens || 0;
        state.pendingMessages = payload.pending_user_messages || [];
        state.resumeAt = normalizeResumeAt(payload.resume_at);
        if (typeof payload.total_cost === 'number') {
            state.totalCost = payload.total_cost;
        }
        if (typeof payload.context_window === 'number') {
            state.contextWindow = payload.context_window;
        }
        for (const entry of sessionStateFields.getAll()) {
            // Snapshots carry only the core's fields, so an addon's applier
            // would read undefined and reset the state it is keeping.
            if (entry.field in payload) {
                entry.apply(state, payload);
            }
        }
    }
    function normalizeResumeAt(value) {
        if (!value) {
            return '';
        }
        if (typeof value === 'string') {
            return value;
        }
        if (value && typeof value === 'object' && value.isLuxonDateTime) {
            try {
                const utc = value.toUTC();
                return utc.isValid ? utc.toISO() : '';
            } catch {
                return '';
            }
        }
        return String(value);
    }
    function applyRecord(record) {
        applySessionFields(record);
        state.name = record.name || '';
        state.totalCost = record.total_cost || 0;
        state.contextWindow = record.context_window || 0;
        const agent = record.agent_id;
        state.agentId = Array.isArray(agent) ? agent[0] : null;
        state.agentName = Array.isArray(agent) ? agent[1] : '';
        const owner = record.user_id;
        state.ownerId = Array.isArray(owner)
            ? owner[0]
            : typeof owner === 'number'
              ? owner
              : null;
        state.ownerName = Array.isArray(owner) ? owner[1] : '';
        state.shareIds = record.share_user_ids || [];
        // The server's verdict, not a guess from ownership: a chat can be
        // writable without being owned, as a subagent is after a handover.
        state.readonly =
            record.can_write === undefined
                ? !!(state.ownerId && state.ownerId !== user.userId)
                : !record.can_write;
        rebuildEventKeys();
    }
    function applySnapshot(snapshot) {
        if (!snapshot) {
            return;
        }
        if (snapshot.id && snapshot.id !== state.sessionId) {
            return;
        }
        applySessionFields(snapshot);
        const clientKeysById = new Map();
        const clientKeysByContent = new Map();
        for (const entry of state.events || []) {
            if (!entry || !entry._clientKey) {
                continue;
            }
            if (entry.event_id != null) {
                clientKeysById.set(entry.event_id, entry._clientKey);
            } else {
                clientKeysByContent.set(contentKey(entry), entry._clientKey);
            }
        }
        let incomingEvents = snapshot.events || [];
        if (clientKeysById.size || clientKeysByContent.size) {
            incomingEvents = incomingEvents.map((entry) => {
                if (!entry) {
                    return entry;
                }
                const key =
                    clientKeysById.get(entry.event_id) ??
                    clientKeysByContent.get(contentKey(entry));
                return key ? { ...entry, _clientKey: key } : entry;
            });
        }
        if (incomingEvents.length || state.status !== 'running') {
            // A snapshot is a WINDOW over the newest events, never the whole
            // transcript. Replacing with it makes the client shrink: on a
            // tool-heavy turn the 100 newest events are all tool calls, so the
            // question that started the turn drops off the screen mid-answer.
            // Keep what we hold from before the window and let the window own
            // its own range onward — truncation (clear, undo, fork) only ever
            // removes NEWER events, so those stay correct too.
            const oldest = snapshot.oldest_sequence ?? null;
            const older =
                oldest === null
                    ? []
                    : (state.events || []).filter(
                          (entry) =>
                              entry &&
                              Number.isInteger(entry.sequence) &&
                              entry.sequence < oldest,
                      );
            state.events = older.length
                ? [...older, ...incomingEvents]
                : incomingEvents;
            if (!older.length) {
                if (snapshot.oldest_sequence !== undefined) {
                    state.oldestSequence = snapshot.oldest_sequence ?? null;
                }
                if (snapshot.has_more_older !== undefined) {
                    state.hasMoreOlder = !!snapshot.has_more_older;
                }
            }
        }
        const preserveStreaming =
            state.status === 'running' &&
            ((state.streamingText && state.streamingText.length) ||
                (state.streamingReasoning && state.streamingReasoning.length) ||
                (state.streamingTools && state.streamingTools.length));
        if (!preserveStreaming) {
            state.streamingText = '';
            state.streamingReasoning = '';
            state.streamingTools = [];
        }
        rebuildEventKeys();
    }
    function rebuildEventKeys() {
        eventKeys = new Set((state.events || []).map((entry) => eventKey(entry)));
    }
    async function loadMoreEvents() {
        if (state.loadingOlder || !state.hasMoreOlder || !state.sessionId) {
            return;
        }
        const sessionId = state.sessionId;
        const seq = loadSeq;
        state.loadingOlder = true;
        try {
            const result = await orm.call(
                'muk_ai.session',
                'fetch_events',
                [sessionId],
                {
                    limit: 100,
                    before_sequence: state.oldestSequence,
                },
            );
            if (seq !== loadSeq || state.sessionId !== sessionId) {
                return;
            }
            const incoming = result.events || [];
            const merged = [...incoming, ...state.events];
            const seen = new Set();
            state.events = merged.filter((e) => {
                const k = eventKey(e);
                if (seen.has(k)) {
                    return false;
                }
                seen.add(k);
                return true;
            });
            if (
                result.oldest_sequence !== undefined &&
                result.oldest_sequence !== null
            ) {
                state.oldestSequence = result.oldest_sequence;
            }
            state.hasMoreOlder = !!result.has_more_older;
            rebuildEventKeys();
        } finally {
            if (seq === loadSeq && state.sessionId === sessionId) {
                state.loadingOlder = false;
            }
        }
    }
    /**
     * Tell whether this chat may be steered as well as read.
     * @returns {boolean} false on a chat shared with the current user
     */
    function canWrite() {
        return !state.readonly;
    }
    function canSend() {
        const hasContent =
            state.input.trim().length > 0 || state.pendingAttachments.length > 0;
        return canWrite() && !!state.sessionId && !state.loading && hasContent;
    }
    function canAttach() {
        return (
            canWrite() &&
            !!state.sessionId &&
            !state.loading &&
            state.status !== 'running'
        );
    }
    function canStop() {
        return canWrite() && state.status === 'running';
    }
    function isQueueing() {
        return (
            state.status === 'running' ||
            state.status === 'compacting' ||
            (state.status === 'waiting' && !!(state.pendingAsk || {}).queues_input)
        );
    }
    /**
     * Ask the artifacts panel to open on a tab and single out one of its items.
     * @param {string} tab artifact type id
     * @param {number|string|null} [itemId] item to single out within the tab
     */
    function focusArtifact(tab, itemId = null) {
        state.artifactsFocus = { tab, itemId };
    }
    function onInputChange(value) {
        state.input = value;
    }
    /**
     * Re-dispatch a message the server refused to queue (the turn ended
     * mid-flight, so no drain would ever run it) through the regular
     * send path, preserving any draft typed meanwhile.
     * @param {object} snapshot
     * @param {string} message
     * @param {Array} attachments
     */
    async function redispatchRejected(snapshot, message, attachments) {
        applySnapshot(snapshot);
        const draft = state.input;
        const draftAttachments = [...state.pendingAttachments];
        state.input = message;
        state.pendingAttachments = attachments;
        if (!requeueRerouting) {
            requeueRerouting = true;
            try {
                await onSend();
            } finally {
                requeueRerouting = false;
            }
            if (draft) {
                state.input = draft;
                state.pendingAttachments = draftAttachments;
            }
        }
    }
    async function onSend() {
        if (!canSend()) {
            return;
        }
        for (const route of sessionSendRoutes.getAll()) {
            if (
                await route(
                    { state, orm, appendCommand: appendLocalCommandLog },
                    state.input,
                )
            ) {
                state.input = '';
                state.focusToken += 1;
                return;
            }
        }
        const slash = parseSlashCommand(state.input);
        if (slash) {
            state.input = '';
            await dispatchCommand(slash);
            state.focusToken += 1;
            return;
        }
        const message = state.input;
        const attachments = [...state.pendingAttachments];
        const attachmentIds = attachments.map((a) => a.id);
        state.input = '';
        state.pendingAttachments = [];
        if (isQueueing()) {
            const optimisticKey = 'ck' + ++clientKeySeq;
            const optimisticEntry = {
                content: message,
                attachment_ids: attachmentIds,
                queued_at: new Date().toISOString(),
                _clientKey: optimisticKey,
            };
            state.pendingMessages = [...state.pendingMessages, optimisticEntry];
            state.focusToken += 1;
            requestScroll(true);
            try {
                const snapshot = await orm.call(
                    'muk_ai.session',
                    'enqueue_message',
                    [state.sessionId, message],
                    { attachment_ids: attachmentIds },
                );
                if (snapshot && snapshot.queue_rejected_state) {
                    state.pendingMessages = state.pendingMessages.filter(
                        (m) => m?._clientKey !== optimisticKey,
                    );
                    await redispatchRejected(snapshot, message, attachments);
                    return;
                }
                applySnapshot(snapshot);
            } catch (error) {
                notification.add(
                    _t('Failed to queue message: %s', formatError(error)),
                    { type: 'danger' },
                );
                state.pendingMessages = state.pendingMessages.filter(
                    (m) => m?._clientKey !== optimisticKey,
                );
            }
            return;
        }
        await maybeAutoCompact();
        const wasWaitingQuestion =
            state.status === 'waiting' && (state.pendingAsk || {}).kind === 'question';
        const clientKey = 'ck' + ++clientKeySeq;
        const optimistic = wasWaitingQuestion
            ? {
                  kind: 'answer',
                  answer: message,
                  question: (state.pendingAsk || {}).text,
                  attachments,
                  _clientKey: clientKey,
              }
            : {
                  kind: 'user_message',
                  content: message,
                  attachments,
                  _clientKey: clientKey,
              };
        state.events = [...state.events, optimistic];
        eventKeys.add(eventKey(optimistic));
        state.streamingText = '';
        state.streamingReasoning = '';
        state.streamingTools = [];
        const previousAsk = state.pendingAsk;
        const previousStatus = state.status;
        state.pendingAsk = null;
        state.status = 'running';
        state.error = null;
        requestScroll(true);
        try {
            const method = wasWaitingQuestion
                ? 'answer'
                : state.iterationCount === 0 &&
                    state.events.length <= 1 &&
                    !state.streamingText
                  ? 'start'
                  : 'send_message';
            const snapshot = await orm.call(
                'muk_ai.session',
                method,
                [state.sessionId, message],
                { attachment_ids: attachmentIds },
            );
            if (snapshot && snapshot.queue_rejected_state) {
                state.events = state.events.filter(
                    (entry) => entry?._clientKey !== clientKey,
                );
                eventKeys.delete(eventKey(optimistic));
                await redispatchRejected(snapshot, message, attachments);
                return;
            }
            applySnapshot(snapshot);
        } catch (error) {
            if (wasWaitingQuestion) {
                state.events = state.events.filter(
                    (entry) => entry?._clientKey !== clientKey,
                );
                eventKeys.delete(eventKey(optimistic));
                state.pendingAsk = previousAsk;
                state.status = previousStatus;
            } else {
                state.status = 'error';
            }
            state.error = formatError(error);
        }
        state.focusToken += 1;
        requestScroll();
    }
    async function cancelQueued(index) {
        if (!state.sessionId) {
            return;
        }
        const removed = state.pendingMessages[index];
        state.pendingMessages = state.pendingMessages.filter((_m, i) => i !== index);
        try {
            const snapshot = await orm.call('muk_ai.session', 'cancel_queued', [
                state.sessionId,
                index,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            if (removed) {
                state.pendingMessages = [
                    ...state.pendingMessages.slice(0, index),
                    removed,
                    ...state.pendingMessages.slice(index),
                ];
            }
            notification.add(
                _t('Failed to cancel queued message: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    async function onStop() {
        if (!state.sessionId) {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'action_stop', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(_t('Failed to stop session: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    async function onRegenerate() {
        if (
            !state.sessionId ||
            state.status === 'running' ||
            state.status === 'compacting' ||
            state.status === 'waiting'
        ) {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'regenerate_last_turn', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(_t('Failed to regenerate: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    function canRegenerate() {
        if (!state.sessionId || !canWrite()) return false;
        if (
            state.status === 'running' ||
            state.status === 'compacting' ||
            state.status === 'waiting'
        )
            return false;
        return (state.events || []).some(
            (e) => e.kind === 'user_message' || e.kind === 'answer',
        );
    }
    async function onAttachFiles(files) {
        if (!state.sessionId || !files || !files.length) {
            return;
        }
        try {
            const payloads = await Promise.all(files.map((file) => fileToBase64(file)));
            const descriptors = await orm.call('muk_ai.session', 'upload_attachments', [
                state.sessionId,
                payloads,
            ]);
            state.pendingAttachments = [...state.pendingAttachments, ...descriptors];
        } catch (error) {
            notification.add(_t('Attachment upload failed: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    function parseSlashCommand(raw) {
        const trimmed = (raw || '').trim();
        if (!trimmed.startsWith('/')) {
            return null;
        }
        const parts = trimmed.slice(1).split(/\s+/);
        const name = parts.shift().toLowerCase();
        if (!name) {
            return null;
        }
        if (!SLASH_COMMANDS.some((c) => c.name === `/${name}`)) {
            return null;
        }
        return { name: `/${name}`, args: parts.join(' ') };
    }
    async function dispatchCommand(slash) {
        if (slash.name === '/help') {
            appendLocalCommandLog('/help', {
                summary: _helpSummary(),
            });
            return;
        }
        if (slash.name === '/clear') {
            await runClear();
            return;
        }
        if (slash.name === '/compact') {
            await runCompact({ silent: false });
            return;
        }
        if (slash.name === '/unpin') {
            await runUnpin();
            return;
        }
        if (slash.name === '/agent') {
            await runSwitchAgent(slash.args);
            return;
        }
        if (slash.name === '/handover') {
            openHandoverPicker(slash.args);
            return;
        }
    }
    async function runSwitchAgent(query) {
        const agents = state.agents || [];
        if (!agents.length) {
            notification.add(_t('No agents available to switch to.'), {
                type: 'warning',
            });
            return;
        }
        const q = (query || '').trim().toLowerCase();
        let target = agents.find((a) => (a.name || '').toLowerCase() === q);
        if (!target && q) {
            target = agents.find((a) => (a.name || '').toLowerCase().includes(q));
        }
        if (!target) {
            notification.add(
                _t(
                    'No agent matches "%s". Type /agent to pick from the list.',
                    query || '',
                ),
                { type: 'warning' },
            );
            return;
        }
        await onSetAgent(target.id);
    }
    async function runUnpin() {
        if (!state.sessionId) {
            return;
        }
        if (!state.viewContext) {
            notification.add(_t('No view context is pinned.'), { type: 'info' });
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'unpin_view_context', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to clear view context: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    async function setApprovalMode(mode) {
        if (!state.sessionId) {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'set_approval_mode', [
                state.sessionId,
                mode || false,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to set approval mode: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    async function setReasoningEffort(effort) {
        if (!state.sessionId) {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'set_reasoning_effort', [
                state.sessionId,
                effort || false,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to set reasoning effort: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    function isAwaitingApproval() {
        return (
            state.status === 'waiting' && (state.pendingAsk || {}).kind === 'approval'
        );
    }
    function cycleApprovalMode() {
        const next = state.effectiveApprovalMode === 'off' ? 'ask' : 'off';
        return setApprovalMode(next);
    }
    async function answerWithOption(option) {
        if (state.status === 'running' || !option) {
            return;
        }
        state.input = option;
        await onSend();
    }
    async function respondYesno(decision) {
        const pending = state.pendingAsk || {};
        if (pending.kind === 'approval') {
            if (decision === 'approve') {
                return approveTool();
            }
            if (decision === 'session') {
                return approveForSession();
            }
            return rejectTool();
        }
        const labels = { approve: 'Approve', session: 'Approve', reject: 'Reject' };
        return answerWithOption(labels[decision] || decision);
    }
    async function _runApproval(method, errMessage, kwargs) {
        if (!state.sessionId || !isAwaitingApproval()) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session',
                method,
                [state.sessionId],
                kwargs,
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(errMessage(error), { type: 'danger' });
        }
    }
    async function approveTool() {
        return _runApproval('approve_tool', (e) =>
            _t('Failed to approve tool: %s', formatError(e)),
        );
    }
    async function approveForSession() {
        return _runApproval('approve_for_session', (e) =>
            _t('Failed to approve tool: %s', formatError(e)),
        );
    }
    async function rejectTool(reason) {
        return _runApproval(
            'reject_tool',
            (e) => _t('Failed to reject tool: %s', formatError(e)),
            { reason: reason || '' },
        );
    }
    async function openPinnedContext() {
        const ctx = state.viewContext;
        if (!ctx || !ctx.model) {
            return;
        }
        const action = {
            type: 'ir.actions.act_window',
            res_model: ctx.model,
        };
        if (ctx.kind === 'record' && ctx.id) {
            action.res_id = ctx.id;
            action.view_mode = 'form';
            action.views = [[false, 'form']];
        } else {
            const viewType = ctx.view_type || 'list';
            action.view_mode = viewType;
            action.views = [[false, viewType]];
            if (Array.isArray(ctx.domain)) {
                action.domain = ctx.domain;
            }
        }
        try {
            maybePopoutBeforeAction();
            await actionService.doAction(action);
        } catch (error) {
            notification.add(_t('Failed to open view: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    function _helpSummary() {
        return allSlashCommands()
            .map((c) => `**${c.name}** — ${c.hint}`)
            .join('\n\n');
    }
    function appendLocalCommandLog(name, extra) {
        const entry = {
            kind: 'command',
            name,
            ...(extra || {}),
        };
        state.events = [...state.events, entry];
        eventKeys.add(eventKey(entry));
        requestScroll();
    }
    async function runClear() {
        if (!state.sessionId) {
            return;
        }
        if (state.status === 'running') {
            notification.add(_t('Stop the running session before clearing.'), {
                type: 'warning',
            });
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'clear', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
            if (options.onRefresh) {
                await options.onRefresh();
            }
        } catch (error) {
            notification.add(_t('Failed to clear session: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    async function runCompact({ silent: _silent }) {
        if (!state.sessionId) {
            return;
        }
        if (state.status === 'running') {
            notification.add(_t('Stop the running session before compacting.'), {
                type: 'warning',
            });
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'compact', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to compact conversation: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
    async function runStopCompact() {
        if (!state.sessionId || state.status !== 'compacting') {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'stop_compact', [
                state.sessionId,
            ]);
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(_t('Failed to stop compaction: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    function _eventsFromOrAfter(eventId) {
        const events = state.events || [];
        const idx = events.findIndex((e) => Number(e.event_id) === Number(eventId));
        if (idx < 0) {
            return events.length;
        }
        return events.length - idx;
    }
    async function runUndoToEvent(eventId) {
        if (!state.sessionId || !eventId) {
            return;
        }
        if (
            state.status === 'running' ||
            state.status === 'compacting' ||
            state.status === 'waiting'
        ) {
            notification.add(_t('Stop the session before rewinding.'), {
                type: 'warning',
            });
            return;
        }
        const dropCount = _eventsFromOrAfter(eventId);
        const confirmed = await new Promise((resolve) => {
            dialog.add(ConfirmationDialog, {
                title: _t('Rewind conversation'),
                body: _t(
                    'Remove this message and the %s event(s) that follow from ' +
                        'the conversation? This cannot be undone.',
                    dropCount,
                ),
                confirmLabel: _t('Rewind'),
                cancelLabel: _t('Cancel'),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
        if (!confirmed) {
            return;
        }
        try {
            const snapshot = await orm.call('muk_ai.session', 'undo_to_event', [
                state.sessionId,
                eventId,
            ]);
            applySnapshot(snapshot);
            if (options.onRefresh) {
                await options.onRefresh();
            }
        } catch (error) {
            notification.add(_t('Failed to rewind: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    async function runForkAtEvent(eventId) {
        if (!state.sessionId || !eventId) {
            return;
        }
        if (state.status === 'running' || state.status === 'compacting') {
            notification.add(_t('Stop the session before forking.'), {
                type: 'warning',
            });
            return;
        }
        try {
            const newId = await orm.call('muk_ai.session', 'fork_at_event', [
                state.sessionId,
                eventId,
            ]);
            notification.add(_t('Forked into a new session.'), { type: 'success' });
            if (options.onForked) {
                await options.onForked(newId);
            }
        } catch (error) {
            notification.add(_t('Failed to fork: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    async function onHandover(userId) {
        if (!state.sessionId || !userId) {
            return;
        }
        if (state.status === 'running' || state.status === 'compacting') {
            notification.add(_t('Stop the session before handing it over.'), {
                type: 'warning',
            });
            return;
        }
        try {
            await orm.call('muk_ai.session', 'action_handover', [
                state.sessionId,
                userId,
            ]);
            notification.add(_t('Chat handed over.'), { type: 'success' });
            if (options.onHandedOver) {
                await options.onHandedOver(state.sessionId);
            }
        } catch (error) {
            notification.add(_t('Failed to hand over: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    /**
     * Open a user picker and hand the current chat to the chosen user.
     * @param {string} [query] optional name prefilter typed after /handover
     */
    function openHandoverPicker(query = '') {
        if (!state.sessionId) {
            return;
        }
        const domain = [
            ['share', '=', false],
            ['active', '=', true],
            ['id', '!=', state.ownerId],
        ];
        if (query) {
            domain.push(['name', 'ilike', query]);
        }
        dialog.add(SelectCreateDialog, {
            resModel: 'res.users',
            title: _t('Hand over chat to…'),
            domain,
            noCreate: true,
            multiSelect: false,
            context: {
                list_view_ref: 'muk_ai.view_res_users_list_handover',
                kanban_view_ref: 'muk_ai.view_res_users_kanban_handover',
                search_view_ref: 'muk_ai.view_res_users_search_handover',
            },
            onSelected: (resIds) => {
                if (resIds && resIds[0]) {
                    onHandover(resIds[0]);
                }
            },
        });
    }
    async function maybeAutoCompact() {
        if (!state.contextWindow || !state.lastInputTokens) {
            return;
        }
        const ratio = state.lastInputTokens / state.contextWindow;
        if (ratio >= COMPACT_AUTO_RATIO) {
            await runCompact({ silent: true });
            notification.add(
                _t(
                    'Auto-compacted: context window was %s%% full.',
                    Math.round(ratio * 100),
                ),
                { type: 'info' },
            );
        } else if (ratio >= COMPACT_WARN_RATIO && !state.autoCompactPending) {
            state.autoCompactPending = true;
            notification.add(
                _t(
                    'Context window at %s%%. Type /compact to free room ' +
                        'before continuing.',
                    Math.round(ratio * 100),
                ),
                { type: 'warning' },
            );
        }
    }
    async function loadAgents() {
        try {
            state.agents = await orm.searchRead(
                'muk_ai.agent',
                [['active', '=', true]],
                ['id', 'name', 'description', 'suggestions'],
                { order: 'sequence, name' },
            );
        } catch {
            state.agents = [];
        }
    }
    async function setAgent(agentId, agentName = '') {
        if (!state.sessionId) {
            return;
        }
        try {
            await orm.write('muk_ai.session', [state.sessionId], {
                agent_id: agentId || false,
            });
            state.agentId = agentId || null;
            state.agentName = agentName;
        } catch (error) {
            notification.add(_t('Failed to change agent: %s', formatError(error)), {
                type: 'danger',
            });
        }
    }
    async function onSetAgent(agentId) {
        const agent = state.agents.find((a) => a.id === agentId);
        await setAgent(agentId || null, agent ? agent.name : '');
    }
    async function onRemoveAttachment(attachmentId) {
        state.pendingAttachments = state.pendingAttachments.filter(
            (a) => a.id !== attachmentId,
        );
        if (!state.sessionId) {
            return;
        }
        try {
            await orm.call('muk_ai.session', 'discard_attachments', [
                state.sessionId,
                [attachmentId],
            ]);
        } catch {
            /* ignore */
        }
    }
    function toggleToolBlock(callId) {
        if (!callId) {
            return;
        }
        state.expandedTools = {
            ...state.expandedTools,
            [callId]: !state.expandedTools[callId],
        };
    }
    function isToolExpanded(callId) {
        return !!(callId && state.expandedTools[callId]);
    }
    let cachedTurnsEvents = null;
    let cachedTurns = [];
    function renderedTurns() {
        if (state.events !== cachedTurnsEvents) {
            cachedTurnsEvents = state.events;
            cachedTurns = buildRenderedTurns(state.events);
        }
        return cachedTurns;
    }
    function latestReasoningLine() {
        const text = state.streamingReasoning || '';
        if (!text) {
            return '';
        }
        const lines = text
            .split(/\n+/)
            .map((l) =>
                l
                    .trim()
                    .replace(/^[#*\->\s]+/, '')
                    .replace(/[*]+$/, ''),
            )
            .filter((l) => l.length > 0);
        if (!lines.length) {
            return '';
        }
        return lines[lines.length - 1];
    }
    const markdownCache = new Map();
    function renderMarkdown(text) {
        if (typeof text !== 'string') {
            return markup(renderMarkdownToHtml(text));
        }
        let cached = markdownCache.get(text);
        if (cached === undefined) {
            cached = markup(renderMarkdownToHtml(text));
        } else {
            markdownCache.delete(text);
        }
        markdownCache.set(text, cached);
        if (markdownCache.size > 400) {
            markdownCache.delete(markdownCache.keys().next().value);
        }
        return cached;
    }
    function copyText(text) {
        if (!text || !navigator.clipboard) {
            return;
        }
        navigator.clipboard.writeText(String(text)).then(
            () => notification.add(_t('Copied to clipboard'), { type: 'success' }),
            () => notification.add(_t('Copy failed'), { type: 'danger' }),
        );
    }
    function setScrollCallback(callback) {
        onScrollCallback = callback;
    }
    function requestScroll(force = false) {
        if (onScrollCallback) {
            onScrollCallback(force);
        }
    }
    onWillUnmount(() => {
        sessionNotification.markInactive(state.sessionId);
        busUnsubscribe(bus, 'muk_ai.event', busHandler);
        clearStreamIdleTimer();
    });
    /**
     * Call a method on the session this surface is showing.
     *
     * An addon draws its pill or card outside this hook and still has to act
     * on the chat it is drawn in.
     * @param {string} method the method on ``muk_ai.session``
     * @param {Array} [args] its arguments after the session id
     * @returns {Promise<*>} whatever the method returned, null without a session
     */
    async function callSession(method, args = []) {
        if (!state.sessionId) {
            return null;
        }
        return orm.call('muk_ai.session', method, [state.sessionId, ...args]);
    }
    const api = {
        state,
        callSession,
        load,
        loadMoreEvents,
        applySnapshot,
        onInputChange,
        onSend,
        onStop,
        onAttachFiles,
        onRemoveAttachment,
        loadAgents,
        setAgent,
        onSetAgent,
        toggleToolBlock,
        isToolExpanded,
        renderedTurns,
        latestReasoningLine,
        renderMarkdown,
        copyText,
        onRegenerate,
        canRegenerate,
        setScrollCallback,
        canWrite,
        canSend,
        canAttach,
        canStop,
        isQueueing,
        focusArtifact,
        cancelQueued,
        runUnpin,
        setApprovalMode,
        cycleApprovalMode,
        setReasoningEffort,
        openPinnedContext,
        approveTool,
        approveForSession,
        rejectTool,
        answerWithOption,
        respondYesno,
        runStopCompact,
        runUndoToEvent,
        runForkAtEvent,
        openHandoverPicker,
    };
    for (const name of WRITE_ACTIONS) {
        const action = api[name];
        api[name] = (...args) => (state.readonly ? undefined : action(...args));
    }
    return api;
}

/**
 * Observe a session handed down as a prop through this component's own proxy.
 *
 * OWL re-renders a subcomponent only when a prop changes identity, and the
 * `session` object is the same one on every parent render. Reading the state
 * through the component's own proxy subscribes it to the keys it uses, so a
 * card driven by the event log follows the session it is shown in.
 * @param {object} session the session api received as a prop
 * @returns {object} the same api, reading state through this component's proxy
 */
export function useSessionState(session) {
    return Object.assign(Object.create(session), { state: useState(session.state) });
}
