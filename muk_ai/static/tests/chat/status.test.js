import {
    advanceTime,
    animationFrame,
    expect,
    freezeTime,
    mockDate,
    test,
} from '@odoo/hoot';
import { Component, t, useProps, xml } from '@odoo/owl';
import {
    contains,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { ContextChip } from '@muk_ai/chat/context_chip/context_chip';
import { SessionStatus } from '@muk_ai/chat/status/status';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

class Header extends Component {
    static template = xml`<div><SessionStatus session="this.props.session"/><ContextChip session="this.props.session"/></div>`;
    static components = { ContextChip, SessionStatus };
    props = useProps({ session: t.object() });
}

async function mountHeader(values = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
    const session = await openSession(1);
    await mountWithCleanup(Header, { props: { session } });
    return session;
}

test('the status names the agent and the state, a scheduled chat counts down to its resume', async () => {
    mockDate('2026-01-01 10:00:00', 0);
    freezeTime();
    const session = await mountHeader({ state: 'running', agent_id: [1, 'General'] });
    expect('.mk_avatar.mk_state_running .oi-spin').toHaveCount(1);
    expect('.mk_avatar').toHaveAttribute('title', 'General · Running');
    Object.assign(session.data, {
        state: 'waiting_schedule',
        resume_at: '2026-01-01 10:02:00',
    });
    await animationFrame();
    expect('.mk_avatar.mk_state_waiting').toHaveAttribute(
        'title',
        'General · Scheduled',
    );
    expect('.mk_resume').toHaveText('resumes in 2m 0s');
    await advanceTime(5000);
    expect('.mk_resume').toHaveText('resumes in 1m 55s');
    session.data.state = 'done';
    await animationFrame();
    expect('.mk_resume').toHaveCount(0);
});

test('the pinned view shows as a chip named after its model that opens it, and its owner unpins it', async () => {
    onRpc('muk_ai.session', 'unpin_view_context', () => {
        expect.step('unpin');
        return snapshot();
    });
    const session = await mountHeader();
    expect('.mk_ctx_chip').toHaveCount(0);
    for (const [context, label] of [
        [
            { kind: 'record', model: 'res.partner', id: 7, display_name: 'Azure' },
            'Partner · Azure',
        ],
        [{ kind: 'record', model: 'res.partner', id: 7 }, 'Partner · #7'],
        [
            { kind: 'list', model: 'res.partner', view_type: 'kanban' },
            'Partner · kanban',
        ],
        [{ kind: 'pivot', model: 'crm.lead' }, 'Lead'],
    ]) {
        session.data.view_context = context;
        await animationFrame();
        expect('.mk_ctx_open').toHaveText(label);
    }
    session.data.view_context = {
        kind: 'list',
        model: 'res.partner',
        domain: [['id', '=', 7]],
    };
    await animationFrame();
    expect('.mk_ctx_open').toHaveAttribute(
        'title',
        'Partner · list\n[["id","=",7]]\nClick to open · /unpin to clear',
    );
    patchWithCleanup(getService(ActionPlugin), {
        doAction: (action) => expect.step(action.domain),
    });
    await contains('.mk_ctx_open').click();
    await contains('.mk_ctx_unpin').click();
    expect.verifySteps([[['id', '=', 7]], 'unpin']);
    expect('.mk_ctx_chip').toHaveCount(0);
    session.data.view_context = { kind: 'record', model: 'res.partner', id: 7 };
    session.data.can_write = false;
    await animationFrame();
    expect('.mk_ctx_unpin').toHaveCount(0);
});
