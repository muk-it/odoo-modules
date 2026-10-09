import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('muk_ai_chatter_tour', {
    steps: () => [
        {
            trigger: '.mk_chatter_ai_sessions:contains("1")',
            content: 'The chatter topbar counts the sessions linked to the record',
        },
        {
            trigger: '.o-mail-Chatter:not(:has(.mk_session_box))',
            content: 'The list stays out of the way until it is asked for',
        },
        {
            trigger: '.mk_chatter_ai_sessions',
            content: 'Show the AI sessions',
            run: 'click',
        },
        {
            trigger: '.mk_session_box_item:contains("Tour Session") .mk_state_done',
            content: 'The linked session is listed, its state carried by a dot',
        },
        {
            trigger: '.mk_chatter_ai_sessions.active',
            content: 'Hide the AI sessions again',
            run: 'click',
        },
        {
            trigger: '.o-mail-Chatter:not(:has(.mk_session_box))',
            content: 'The list is gone again',
        },
    ],
});
