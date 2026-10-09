import { animationFrame, beforeEach, describe } from '@odoo/hoot';
import {
    defineModels,
    fields,
    getService,
    getTestApp,
    makeTestApp,
    models,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { BusPlugin } from '@bus/services/bus_plugin';
import { DialogPlugin } from '@web/core/dialog/dialog_plugin';
import { NotificationPlugin } from '@web/core/notifications/notification_plugin';
import { patch } from '@web/core/utils/patch';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';

export const SNAPSHOT = {
    name: 'Demo',
    state: 'done',
    can_write: true,
    share_user_ids: [],
    agent_id: false,
    events: [],
    has_more_older: false,
    oldest_sequence: null,
    pending_ask: null,
    view_context: null,
    error_message: false,
    pending_user_messages: [],
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    last_input_tokens: 0,
    turn_usage: {},
    context_window: 8000,
    total_cost: 0,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    override_reasoning_effort: false,
    effective_reasoning_effort: false,
    reasoning_effort_options: [],
    agent_reasoning_effort: false,
};

export class AISessionModel extends models.Model {
    _name = 'muk_ai.session';
    name = fields.Char();
    state = fields.Char({ default: 'new' });
    user_id = fields.Many2one({
        relation: 'res.users',
        default: () => serverState.userId,
    });
    share_user_ids = fields.Many2many({ relation: 'res.users' });
    agent_id = fields.Many2one({ relation: 'muk_ai.agent' });
    space_id = fields.Many2one({ relation: 'muk_ai.space' });
    notification_unread = fields.Boolean();
    awaiting_user = fields.Boolean();
    _records = [
        { id: 1, name: 'Demo', state: 'done' },
        { id: 2, name: 'Other', state: 'done' },
    ];
    get_snapshot(id) {
        const [record] = this.read(
            [id],
            ['name', 'state', 'user_id', 'share_user_ids', 'agent_id'],
        );
        return { ...snapshot({ id }), ...record };
    }
    start(id) {
        return { ...this.get_snapshot(id), state: 'running' };
    }
    send_message(id) {
        return this.start(id);
    }
    notification_badge() {
        return { count: 0, session_ids: [], space_unread: {} };
    }
    dismiss_notifications() {
        return true;
    }
    set_view_context() {
        return true;
    }
}

export class AIAgentModel extends models.Model {
    _name = 'muk_ai.agent';
    name = fields.Char();
    description = fields.Char();
    suggestions = fields.Json();
    active = fields.Boolean({ default: true });
    sequence = fields.Integer();
    _records = [
        {
            id: 1,
            name: 'General',
            sequence: 1,
            description: 'Default agent',
            suggestions: [{ label: 'Pipeline', prompt: 'Show my **pipeline**' }],
        },
        {
            id: 2,
            name: 'Analyst',
            description: 'Analyses',
            sequence: 2,
            suggestions: [],
        },
    ];
}

export class AISpaceModel extends models.Model {
    _name = 'muk_ai.space';
    name = fields.Char();
    icon = fields.Char({ default: 'folder' });
    system = fields.Boolean();
    pinned = fields.Boolean();
    sequence = fields.Integer();
    instructions = fields.Text();
    agent_id = fields.Many2one({ relation: 'muk_ai.agent' });
    fetch_spaces() {
        return this.search_read(
            [],
            ['name', 'icon', 'system', 'pinned', 'instructions'],
        ).map((space) => ({
            ...space,
            agent_id: false,
            session_domain: [['space_id', '=', space.id]],
        }));
    }
    fetch_general_domain() {
        return [['space_id', '=', false]];
    }
    reorder() {
        return true;
    }
}

export class LeadModel extends models.Model {
    _name = 'muk_ai.test_lead';
    name = fields.Char();
    stage = fields.Selection({
        selection: [
            ['new', 'New'],
            ['won', 'Won'],
        ],
    });
    amount = fields.Float({ aggregator: 'sum' });
    _records = [
        { id: 1, name: 'Acme', stage: 'new', amount: 50 },
        { id: 2, name: 'Globex', stage: 'won', amount: 300 },
    ];
    _views = {
        list: '<list><field name="name"/><field name="stage"/><field name="amount"/></list>',
        kanban: '<kanban><templates><t t-name="card"><field name="name"/></t></templates></kanban>',
        form: '<form><field name="name"/><field name="stage"/></form>',
        pivot: '<pivot><field name="stage" type="row"/></pivot>',
        graph: '<graph><field name="stage"/></graph>',
        search: `
            <search>
                <field name="name"/>
                <filter name="won" string="Won" domain="[('stage', '=', 'won')]"/>
                <filter name="by_stage" string="Stage" context="{'group_by': 'stage'}"/>
            </search>
        `,
    };
}

/**
 * Open the leads in a list with the other views a step away.
 * @param {object} [options] `doAction` options
 * @returns {Promise<void>} resolved once the list is shown
 */
export function openLeads(options) {
    return getService(ActionPlugin).doAction(
        {
            type: 'ir.actions.act_window',
            res_model: 'muk_ai.test_lead',
            views: [
                [false, 'list'],
                [false, 'kanban'],
                [false, 'pivot'],
                [false, 'graph'],
                [false, 'form'],
            ],
        },
        options,
    );
}

/**
 * Tag the test file and declare the mail and muk_ai mock models.
 * @param {...Function} extra further mock models
 */
export function defineAIModels(...extra) {
    describe.current.tags('muk_ai');
    defineMailModels();
    defineModels([AISessionModel, AIAgentModel, AISpaceModel, ...extra]);
    beforeEach(() =>
        onRpc('ir.model', 'ai_tool_labels', ({ args: [requested] }) =>
            Object.fromEntries(
                Object.entries(requested).map(([model, names]) => {
                    const last = model.split('.').at(-1);
                    return [
                        model,
                        {
                            name: last[0].toUpperCase() + last.slice(1),
                            fields: Object.fromEntries(
                                names.map((name) => [name, `${name} label`]),
                            ),
                        },
                    ];
                }),
            ),
        ),
    );
}

/**
 * Build a snapshot as `get_snapshot` answers it.
 * @param {object} [values] the values differing from the defaults
 * @returns {object} the snapshot
 */
export function snapshot(values = {}) {
    return {
        id: 1,
        user_id: [serverState.userId, 'Mitchell Admin'],
        ...SNAPSHOT,
        ...values,
    };
}

/**
 * Deliver a bus notification to this tab.
 * @param {string} type the notification type
 * @param {object} payload its payload
 * @returns {Promise<void>} resolved once the screen followed
 */
export function emit(type, payload) {
    getService(BusPlugin).notificationBus.trigger(type, { id: 0, payload });
    return animationFrame();
}

/**
 * Deliver a `muk_ai.event` of a chat.
 * @param {number} sessionId the chat
 * @param {string} type the event type
 * @param {object} [payload] its payload
 * @returns {Promise<void>} resolved once the screen followed
 */
export function emitEvent(sessionId, type, payload = {}) {
    return emit('muk_ai.event', { session_id: sessionId, type, payload });
}

/**
 * Return the AI chat plugin of the test app, starting the app when needed.
 * @returns {Promise<object>} the plugin
 */
export async function getChat() {
    if (!getTestApp()) {
        await makeTestApp();
    }
    return getService(AIChatPlugin);
}

/**
 * Show a chat as a surface does and wait for its snapshot.
 * @param {number} [id] the chat
 * @returns {Promise<object>} the loaded session
 */
export async function openSession(id = 1) {
    const chat = await getChat();
    const session = chat.acquire(id);
    await session.ready;
    return session;
}

/**
 * Build a one-pixel PNG file.
 * @param {string} [name] the file name
 * @returns {File} the file
 */
export function pngFile(name = 'shot.png') {
    return new File([new Uint8Array([137, 80, 78, 71])], name, { type: 'image/png' });
}

/**
 * Record the toasts the chat raises instead of drawing them.
 * @returns {Promise<Array>} the list `{message, type}` entries land in
 */
export async function recordNotifications() {
    await getChat();
    const notes = [];
    patch(getService(NotificationPlugin), {
        add(message, options = {}) {
            notes.push({ message: String(message), type: options.type });
            return () => {};
        },
    });
    return notes;
}

/**
 * Record the dialogs the chat opens instead of drawing them.
 * @returns {Promise<Array>} the list `{Component, props}` entries land in
 */
export async function recordDialogs() {
    await getChat();
    const dialogs = [];
    patch(getService(DialogPlugin), {
        add(Component, props) {
            dialogs.push({ Component, props });
            return () => {};
        },
    });
    return dialogs;
}
