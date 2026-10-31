import { describe, expect, test } from '@odoo/hoot';
import { animationFrame, queryAllTexts } from '@odoo/hoot-dom';
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { openSkillsPanel } from '@muk_ai_skills/chat/skill_cache';
import '@muk_ai_skills/webclient/systray/systray';

describe.current.tags('muk_ai_skills');
defineMailModels();

test('on a record the systray offers its skills and opens all of them from its more chip', async () => {
    const windows = [];
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => windows.push(id),
        close: () => {},
        get sessionIds() {
            return [];
        },
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('action', {
        currentController: { props: { resModel: 'res.partner', resId: 7 } },
    });
    onRpc('muk_ai.session', 'search_read', () => []);
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 0,
        session_ids: [],
    }));
    onRpc('muk_ai.session', 'get_needs_you', () => []);
    onRpc('muk_ai.session', 'set_view_context', () => true);
    onRpc('res.partner', 'read', () => [{ id: 7, display_name: 'Globex' }]);
    let nextId = 40;
    onRpc('muk_ai.session', 'create', () => [++nextId]);
    onRpc('muk_ai.skill', 'fetch_skills', ({ args }) => {
        expect.step(`fetch ${args[1].model}`);
        return [
            {
                name: 'enrich',
                label: 'Enrich',
                description: 'Fill gaps.',
                models: ['res.partner'],
            },
            { name: 'help', label: 'Help', description: '', models: [] },
        ];
    });
    onRpc('muk_ai.session', 'invoke_skill_from_chat', ({ args }) => {
        expect.step(`invoke ${args[0]} ${args[1]}`);
        return {};
    });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    expect.verifySteps(['fetch res.partner']);
    expect(queryAllTexts('.mk_systray_chips .mk_systray_chip')).toEqual(['Enrich']);
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['invoke 41 enrich']);
    expect(windows).toEqual([41]);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    expect.verifySteps(['fetch res.partner']);
    await contains('.mk_systray_more').click();
    await animationFrame();
    expect(windows).toEqual([41, 42]);
    expect(openSkillsPanel.has(42)).toBe(true);
});
