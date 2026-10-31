// @odoo-module

import { hotkeyService } from '@web/core/hotkeys/hotkey_service';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { uiService } from '@web/core/ui/ui_service';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { makeFakeNotificationService } from '@web/../tests/helpers/mock_services';
import { click, getFixture, mount, nextTick } from '@web/../tests/helpers/utils';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

const APPROVAL = {
    key: 'muk_ai.session:1',
    res_model: 'muk_ai.session',
    res_id: 1,
    session_id: 1,
    label: 'Lead agent',
    sublabel: 'Update Azure',
    icon: 'fa-hand-paper-o',
    changes: [{ label: 'Name', from: 'Azure', to: 'Azure Interior' }],
    approve: 'approve_tool',
    reject: 'reject_tool',
};

const TASK = {
    key: 'project.task:2',
    res_model: 'project.task',
    res_id: 2,
    label: 'Check the offer',
    sublabel: 'Offer review - Globex',
    icon: 'fa-check-square-o',
    open: 'action_review',
};

const CHATS = [
    {
        id: 1,
        name: 'Lead agent',
        state: 'waiting',
        agent_id: [1, 'Aimee'],
        write_date: '2026-01-01 10:00:00',
    },
    {
        id: 2,
        name: 'Unread report',
        state: 'done',
        agent_id: [1, 'Aimee'],
        write_date: '2026-01-01 10:00:00',
        last_text: 'The report is **ready**, see [Q1](account.move,4).',
    },
];

/**
 * Mount the AI menu over fake services and a mocked server.
 * @param {object} config `needs`, the `record` on screen, `steps` to fill
 * @returns {Promise<HTMLElement>} the fixture holding the menu
 */
async function mountSystray({ needs, record = null, steps }) {
    const services = registry.category('services');
    services.add('hotkey', hotkeyService);
    services.add('ui', uiService);
    services.add('orm', ormService);
    services.add('notification', makeFakeNotificationService());
    services.add('bus_service', {
        start: () => Object.assign(new EventTarget(), { start() {} }),
    });
    services.add('action', {
        start: () => ({
            currentController: record && {
                props: { resModel: record.model, resId: record.id },
            },
            doAction: (action) => steps.push(`action ${action.res_id || action.tag}`),
        }),
    });
    services.add('muk_ai.chat_window', {
        start: () => ({ open: (id) => steps.push(`window ${id}`), sessionIds: [] }),
    });
    const env = await makeTestEnv({
        mockRPC(route, { model, method, args, kwargs }) {
            if (method === 'fetch_skills') {
                return [];
            }
            if (method === 'get_needs_you') {
                return needs();
            }
            if (method === 'notification_badge') {
                return { count: 1, session_ids: [2] };
            }
            if (model === 'muk_ai.session' && method === 'search_read') {
                return kwargs.domain.some((leaf) => leaf[0] === 'notification_unread')
                    ? [CHATS[1]]
                    : CHATS;
            }
            if (model === 'muk_ai.agent') {
                return [
                    {
                        suggestions: [
                            { label: 'Pipeline', prompt: 'Show my pipeline' },
                        ],
                    },
                ];
            }
            if (method === 'read') {
                return [{ id: record.id, display_name: record.name }];
            }
            if (method === 'create') {
                return [9];
            }
            if (method === 'action_review') {
                return { type: 'ir.actions.act_window', res_id: args[0][0] };
            }
            if (['approve_tool', 'start'].includes(method)) {
                steps.push(`${method} ${args[0]} ${args[1] || ''}`.trim());
            }
            return true;
        },
    });
    const target = getFixture();
    await mount(MukAISystray, target, { env });
    return target;
}

/**
 * Open the AI menu and let what it loads on opening arrive.
 * @param {HTMLElement} target the fixture
 */
async function openMenu(target) {
    await click(target, '.dropdown-toggle');
    await nextTick();
    await nextTick();
}

/**
 * Return the trimmed texts of the elements a selector matches.
 * @param {HTMLElement} target the fixture
 * @param {string} selector the elements
 * @returns {Array<string>} their texts
 */
function texts(target, selector) {
    return [...target.querySelectorAll(selector)].map((el) =>
        el.textContent.replace(/\s+/g, ' ').trim(),
    );
}

QUnit.module('muk_ai', {}, function () {
    QUnit.module('systray');

    QUnit.test(
        'Needs you lists what waits under an amber mark and decides only a single write in place',
        async (assert) => {
            const steps = [];
            let needs = [APPROVAL, TASK];
            const target = await mountSystray({ needs: () => needs, steps });
            assert.containsOnce(target, '.mk_systray_needs');
            assert.strictEqual(
                target.querySelector('.mk_ai_systray_btn').title,
                'MuK AI - 2 things need you',
            );
            await openMenu(target);
            assert.deepEqual(texts(target, '.mk_systray_need .mk_systray_name'), [
                'Lead agent',
                'Check the offer',
            ]);
            assert.deepEqual(texts(target, '.mk_systray_need small'), [
                'ApprovalName Azure Azure Interior',
                'Offer review - Globex',
            ]);
            assert.containsN(target, '.mk_systray_decide button', 2);
            assert.deepEqual(texts(target, '.mk_systray_chats .mk_systray_name'), [
                'Unread report',
            ]);
            assert.deepEqual(texts(target, '.mk_systray_unread .mk_systray_preview'), [
                'The report is ready, see Q1.',
            ]);
            needs = [TASK];
            await click(target, '.mk_systray_need .mk_systray_decide .btn-primary');
            await nextTick();
            assert.deepEqual(steps, ['approve_tool 1']);
            assert.containsOnce(target, '.mk_systray_need');
            assert.containsOnce(target, '.mk_systray_menu');
            await click(target, '.mk_systray_need .mk_systray_row');
            await nextTick();
            assert.deepEqual(steps, ['approve_tool 1', 'action 2']);
        },
    );

    QUnit.test(
        'on a record the menu asks about it and runs an offered action in a new window',
        async (assert) => {
            const steps = [];
            const target = await mountSystray({
                needs: () => [],
                record: { model: 'res.partner', id: 2, name: 'Globex' },
                steps,
            });
            await openMenu(target);
            assert.deepEqual(texts(target, '.mk_systray_ask'), ['Ask about Globex']);
            assert.deepEqual(texts(target, '.mk_systray_chips .mk_systray_chip'), [
                'Pipeline',
            ]);
            await click(target, '.mk_systray_chips .mk_systray_chip');
            await nextTick();
            assert.deepEqual(steps, ['start 9 Show my pipeline', 'window 9']);
        },
    );
});
