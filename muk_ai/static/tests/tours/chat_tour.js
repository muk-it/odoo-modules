/** @odoo-module */

import { registry } from '@web/core/registry';


registry.category('web_tour.tours').add('muk_ai_chat_tour', {
    steps: () => [
        {
            trigger: '.mk_chat',
        },
        {
            trigger: '.mk_sidebar_header button:contains(New Chat)',
            run: 'click',
        },
        {
            trigger: '.mk_sidebar_item.active',
        },
        {
            trigger: '.mk_composer textarea:not([disabled])',
            run: 'edit Hello there',
        },
        {
            trigger: '.mk_sidebar_item.active .mk_sidebar_actions .fa-pencil',
            run: 'click',
        },
        {
            trigger: '.modal input',
            run: 'edit Renamed Chat',
        },
        {
            trigger: '.modal .btn-primary:contains(Rename)',
            run: 'click',
        },
        {
            trigger: '.mk_sidebar_name:contains(Renamed Chat)',
        },
        {
            trigger: '.mk_sidebar_item.active .mk_sidebar_actions .fa-trash',
            run: 'click',
        },
        {
            trigger: '.modal .btn-danger:contains(Delete)',
            run: 'click',
        },
        {
            trigger: '.mk_chat:not(:has(.mk_sidebar_name:contains(Renamed Chat)))',
        },
    ],
});
