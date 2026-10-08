import { animationFrame, expect, press, test } from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import {
    defineAIModels,
    emitEvent,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const highlighted = (name) =>
    [...(CSS.highlights.get(name) || [])].map((range) => range.toString());

async function openSearch() {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            iteration_count: 1,
            events: [
                {
                    kind: 'user_message',
                    content: 'Send the Report',
                    event_id: 1,
                    sequence: 1,
                },
                {
                    kind: 'text',
                    content: 'The **report** is ready, a second report follows.',
                    event_id: 2,
                    sequence: 2,
                },
            ],
        }),
    );
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params: { session_id: 1 },
    });
    await contains('button[title="Search this chat"]').click();
}

test('the search counts and highlights the matches, Enter and Shift+Enter walk them', async () => {
    await openSearch();
    expect('.mk_search_bar input').toBeFocused();
    await contains('.mk_search_bar input').edit('report', { confirm: false });
    expect('.mk_search_counter').toHaveText('1 of 3');
    expect(highlighted('mk-search')).toEqual(['Report', 'report', 'report']);
    for (const [keys, counter] of [
        ['Enter', '2 of 3'],
        ['Enter', '3 of 3'],
        ['Enter', '1 of 3'],
        [['Shift', 'Enter'], '3 of 3'],
    ]) {
        await press(keys);
        await animationFrame();
        expect('.mk_search_counter').toHaveText(counter);
    }
    expect(highlighted('mk-search-active')).toEqual(['report']);
    await contains('.mk_search_bar input').edit('nothing', { confirm: false });
    expect('.mk_search_counter').toHaveText('0 of 0');
    expect('.mk_search_bar button[title^="Next match"]').toHaveProperty(
        'disabled',
        true,
    );
});

test('a message arriving while searching is counted, closing the search clears the highlights', async () => {
    await openSearch();
    await contains('.mk_search_bar input').edit('report', { confirm: false });
    await emitEvent(1, 'log', {
        kind: 'user_message',
        content: 'One more report',
        event_id: 3,
        sequence: 3,
    });
    await animationFrame();
    expect('.mk_search_counter').toHaveText('1 of 4');
    await press('Escape');
    await animationFrame();
    expect('.mk_search_bar').toHaveCount(0);
    expect(CSS.highlights.has('mk-search')).toBe(false);
});
