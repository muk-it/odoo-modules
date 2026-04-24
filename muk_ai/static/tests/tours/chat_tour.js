import { registry } from '@web/core/registry';


registry.category('web_tour.tours').add('muk_ai_chat_sidebar_tour', {
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
            timeout: 30000,
        },
    ],
});

registry.category('web_tour.tours').add('muk_ai_chat_roundtrip_tour', {
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
            run: 'edit List the installed modules.',
        },
        {
            trigger: '.mk_composer .mk_send:not([disabled])',
            run: 'click',
        },
        {
            trigger: '.mk_bubble_user:contains(List the installed modules.)',
        },
        {
            trigger: '.mk_turn_assistant .mk_tool .mk_tool_name:contains(search_read)',
            timeout: 30000,
        },
        {
            trigger: '.mk_turn_assistant .mk_tool:not(.mk_tool_streaming)',
            timeout: 30000,
        },
        {
            trigger: '.mk_bubble_assistant:contains(installed modules)',
            timeout: 30000,
        },
        {
            trigger: '.mk_status_pill.mk_state_done',
            timeout: 30000,
        },
    ],
});
