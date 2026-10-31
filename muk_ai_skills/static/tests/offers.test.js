import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { setSkills, skillsOpening } from '@muk_ai_skills/chat/skill_cache';
import '@muk_ai_skills/chat/chat';
import '@muk_ai_skills/chat/offers';

describe.current.tags('muk_ai_skills');
defineMailModels();
patchTranslations();

const SESSION = {
    id: 7,
    name: 'Demo',
    state: 'done',
    events: [],
    oldest_sequence: null,
    has_more_older: false,
    pending_ask: null,
    view_context: { kind: 'record', model: 'res.partner', id: 1 },
    last_text: '',
    error_message: null,
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    last_input_tokens: 0,
    context_window: 8000,
    total_cost: 0,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

const ENRICH = {
    name: 'enrich',
    label: 'Enrich',
    description: 'Does enrich.',
    scope: 'record',
    models: ['res.partner'],
};

/**
 * Mock the services and records a chat surface needs.
 * @returns {object} the chats opened in a window
 */
function setup() {
    const seen = { opened: [] };
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => seen.opened.push(id),
        close: () => {},
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('notification', { add: () => {} });
    onRpc('muk_ai.session', 'search_read', () => []);
    onRpc('muk_ai.session', 'read', () => [SESSION]);
    onRpc('muk_ai.session', 'get_snapshot', () => SESSION);
    onRpc('muk_ai.session', 'get_needs_you', () => []);
    onRpc('muk_ai.session', 'available_skill_names', () => [ENRICH]);
    onRpc('muk_ai.session', 'invoke_skill_from_chat', ({ args }) => {
        expect.step(`invoke ${args[0]} ${args[1]}`);
        return SESSION;
    });
    onRpc('muk_ai.agent', 'search_read', () => [
        { id: 3, suggestions: [{ label: 'Pipeline', prompt: 'Show my pipeline' }] },
    ]);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    onRpc('muk_ai.space', 'fetch_general_domain', () => [['space_id', '=', false]]);
    return seen;
}

test('an empty chat on a record offers the skills of its model, else the agent prompts', async () => {
    setup();
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await animationFrame();
    expect(chat.sessionSuggestions.map((suggestion) => suggestion.label)).toEqual([
        'Enrich',
    ]);
    await animationFrame();
    expect('.mk_suggestion .mk_suggestion_label').toHaveText(/^enrich$/i);
    await chat.onSubmitSuggestion(chat.sessionSuggestions[0]);
    expect.verifySteps(['invoke 7 enrich']);
    setSkills(7, []);
    await animationFrame();
    expect(chat.sessionSuggestions.map((suggestion) => suggestion.label)).toEqual([
        'Pipeline',
    ]);
});

test('on a record the systray offers its skills and opens all of them from its more chip', async () => {
    const seen = setup();
    onRpc('res.partner', 'read', () => [{ id: 1, display_name: 'Azure' }]);
    onRpc('muk_ai.skill', 'fetch_skills', () => [
        ENRICH,
        { ...ENRICH, name: 'help', models: [] },
    ]);
    onRpc('muk_ai.session', 'create', () => [9]);
    onRpc('muk_ai.session', 'set_view_context', () => true);
    mockService('action', {
        currentController: { props: { resModel: 'res.partner', resId: 1 } },
        doAction: () => {},
    });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    expect('.mk_systray_chips .mk_systray_chip').toHaveText('Enrich');
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['invoke 9 enrich']);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    await contains('.mk_systray_more').click();
    await animationFrame();
    expect(seen.opened).toEqual([9, 9]);
    expect(skillsOpening.has(9)).toBe(true);
    skillsOpening.clear();
});
