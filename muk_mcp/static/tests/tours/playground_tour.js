import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('muk_mcp_playground_tour', {
    steps: () => [
        {
            trigger: '.mk_mcp_keybar button:contains(Generate new)',
            run: 'click',
        },
        {
            trigger: '.mk_mcp_keybar .badge.text-bg-success',
        },
        {
            trigger: '.mk_mcp_list input[type=search]',
            run: 'edit whoami',
        },
        {
            trigger: '.mk_mcp_entry:has(.fw-bold:contains(whoami))',
            run: 'click',
        },
        {
            trigger:
                '.mk_mcp_detail:has(h4:contains(whoami)) button:contains(Try it):enabled',
            run: 'click',
        },
        {
            trigger: '.mk_mcp_response .alert-success',
        },
        {
            trigger: '.mk_mcp_panel_tab[title=Prompts]',
            run: 'click',
        },
        {
            trigger: '.mk_mcp_entry:contains(activities_today)',
            run: 'click',
        },
        {
            trigger:
                '.mk_mcp_detail:has(h4:contains(activities_today)) button:contains(Get prompt):enabled',
            run: 'click',
        },
        {
            trigger: '.mk_mcp_response .badge:contains(user)',
        },
    ],
});
