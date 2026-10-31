// @odoo-module

import { browser } from '@web/core/browser/browser';
import { hotkeyService } from '@web/core/hotkeys/hotkey_service';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { uiService } from '@web/core/ui/ui_service';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { makeFakeNotificationService } from '@web/../tests/helpers/mock_services';
import {
    click,
    getFixture,
    mount,
    nextTick,
    patchWithCleanup,
} from '@web/../tests/helpers/utils';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

const APPROVAL = {
    key: 'muk_ai.session:1',
    res_model: 'muk_ai.session',
    res_id: 1,
    session_id: 1,
    agent_id: 1,
    label: 'Lead agent',
    sublabel: 'Update Azure',
    icon: 'fa-hand-paper-o',
    changes: [{ label: 'Name', from: 'Azure', to: 'Azure Interior' }],
    approve: 'approve_tool',
    reject: 'reject_tool',
};

const TASK = {
    key: 'res.partner:2',
    res_model: 'res.partner',
    res_id: 2,
    label: 'Check the offer',
    sublabel: 'Offer review - Globex',
    icon: 'fa-tasks',
    open: 'action_review',
};

const CHATS = [
    {
        id: 1,
        name: 'Waiting chat',
        state: 'waiting',
        agent_id: [1, 'Agent'],
        write_date: '2026-01-01 10:00:00',
        last_text: '',
        error_message: false,
    },
    {
        id: 2,
        name: 'Unread report',
        state: 'done',
        agent_id: [1, 'Agent'],
        write_date: '2026-01-01 10:00:00',
        last_text: 'The report is **ready**, see [Q1](account.move,4).',
        error_message: false,
    },
    {
        id: 3,
        name: 'Busy chat',
        state: 'running',
        agent_id: [1, 'Agent'],
        write_date: '2026-01-01 11:00:00',
        last_text: 'old',
        error_message: false,
    },
];

let target;

/**
 * Mount the systray against a mocked server.
 * @param {object} [options] `needs` rows, `steps` collecting the calls
 * @returns {Promise<void>}
 */
async function mountSystray({ needs, steps }) {
    const services = registry.category('services');
    services.add('orm', ormService);
    services.add('hotkey', hotkeyService);
    services.add('ui', uiService);
    services.add('notification', makeFakeNotificationService());
    services.add('bus_service', { start: () => ({ subscribe() {} }) });
    services.add('action', {
        start: () => ({
            currentController: null,
            doAction: (action) => steps.push(`action ${action.res_id}`),
        }),
    });
    services.add('muk_ai.chat_window', {
        start: () => ({ open: (id) => steps.push(`window ${id}`), sessionIds: [] }),
    });
    const env = await makeTestEnv({
        mockRPC(route, { method, args, kwargs }) {
            if (method === 'notification_badge') {
                return { count: 1, session_ids: [2], space_unread: {} };
            }
            if (method === 'get_needs_you') {
                return needs();
            }
            if (method === 'search_read' && kwargs.domain.length > 1) {
                return CHATS.filter((chat) => chat.id === 2);
            }
            if (method === 'search_read') {
                return CHATS;
            }
            steps.push(`${method} ${JSON.stringify(args)}`);
            return method === 'action_review'
                ? { type: 'ir.actions.act_window', res_id: 2 }
                : {};
        },
    });
    await mount(MukAISystray, target, { env });
    await click(target, '.dropdown-toggle');
}

QUnit.module('systray', {
    beforeEach() {
        target = getFixture();
        patchWithCleanup(browser, { setTimeout: (fn) => fn(), clearTimeout() {} });
    },
});

QUnit.test(
    'Needs you lists what waits and decides only a single write in place',
    async (assert) => {
        let needs = [APPROVAL, TASK];
        const steps = [];
        await mountSystray({ needs: () => needs, steps });
        assert.containsOnce(target, '.mk_ai_systray_btn .mk_systray_needs');
        assert.strictEqual(
            target.querySelector('.mk_ai_systray_btn').title,
            'MuK AI - 2 things need you',
        );
        assert.deepEqual(
            [...target.querySelectorAll('.mk_systray_need .mk_systray_name')].map(
                (el) => el.textContent,
            ),
            ['Lead agent', 'Check the offer'],
        );
        assert.containsN(target, '.mk_systray_decide button', 2);
        assert.deepEqual(
            [...target.querySelectorAll('.mk_systray_chats .mk_systray_name')].map(
                (el) => el.textContent,
            ),
            ['Unread report', 'Busy chat'],
        );
        assert.strictEqual(
            target.querySelector('.mk_systray_unread .mk_systray_preview').textContent,
            'The report is ready, see Q1.',
        );
        needs = [TASK];
        await click(target, '.mk_systray_decide .btn-primary');
        await nextTick();
        assert.deepEqual(steps, ['approve_tool [[1]]']);
        assert.containsOnce(target, '.mk_systray_need');
        await click(target, '.mk_systray_need .mk_systray_row');
        await nextTick();
        assert.deepEqual(steps.slice(1), ['action_review [[2]]', 'action 2']);
    },
);
