import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { click, queryAllTexts } from '@odoo/hoot-dom';
import { reactive } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ToolsMenu } from '@muk_ai/chat/tools_menu/tools_menu';

describe.current.tags('muk_ai');
defineMailModels();

const SOURCES = [
    {
        key: 'web_search',
        section: 'Abilities',
        icon: 'fa-globe',
        label: 'Web search',
        hint: 'Search the web for current information',
        enabled: true,
    },
    {
        key: 'mcp:7',
        section: 'Connectors',
        icon: 'fa-plug',
        label: 'EU VAT Info',
        hint: 'eu-vat-info 1.1.0',
        enabled: false,
        items: [
            { label: 'calculate_vat', badge: 'Always allow', tone: 'success' },
            { label: 'validate_vat_number', badge: 'Needs approval', tone: 'warning' },
        ],
    },
];

async function mountMenu(toolSources) {
    const session = {
        state: reactive({ toolSources, readonly: false }),
        setToolSource(key, enabled) {
            expect.step(`${key} ${enabled}`);
            session.state.toolSources = session.state.toolSources.map((source) =>
                source.key === key ? { ...source, enabled } : source,
            );
        },
    };
    await mountWithCleanup(ToolsMenu, { props: { session } });
    return session;
}

test('the sources are grouped by section and switch per chat', async () => {
    await mountMenu(SOURCES);
    await click('.mk_tools_toggle');
    await animationFrame();
    expect(queryAllTexts('.mk_tools_title')).toEqual(['ABILITIES', 'CONNECTORS']);
    expect(queryAllTexts('.mk_tools_label')).toEqual(['Web search', 'EU VAT Info']);
    expect('[data-source=web_search] input').toBeChecked();
    expect('[data-source="mcp:7"] input').not.toBeChecked();
    await click('[data-source="mcp:7"] input');
    await animationFrame();
    expect.verifySteps(['mcp:7 true']);
    expect('[data-source="mcp:7"] input').toBeChecked();
});

test('a connector lists its tools, a shared chat cannot switch anything', async () => {
    const session = await mountMenu(SOURCES);
    await click('.mk_tools_toggle');
    await animationFrame();
    expect('.mk_tools_items').toHaveCount(0);
    await click('[data-source="mcp:7"] .mk_tools_expand');
    await animationFrame();
    expect(queryAllTexts('.mk_tools_items li')).toEqual([
        'calculate_vat\nAlways allow',
        'validate_vat_number\nNeeds approval',
    ]);
    expect('.mk_tools_items .badge:contains(Needs approval)').toHaveClass(
        'text-bg-warning',
    );
    session.state.readonly = true;
    await animationFrame();
    expect('.mk_tools_source input:disabled').toHaveCount(2);
});

test('without sources the composer shows no tools button', async () => {
    await mountMenu([]);
    expect('.mk_tools_toggle').toHaveCount(0);
});
