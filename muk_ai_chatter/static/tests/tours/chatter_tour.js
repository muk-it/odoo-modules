import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('muk_ai_chatter_tour', {
    steps: () => [
        {
            trigger: '.o-mail-Chatter-aiSessions:contains("1")',
            content: 'The chatter topbar counts the sessions linked to the record',
        },
        {
            trigger: '.o-mail-Chatter-aiSessions',
            content: 'The list stays out of the way until it is asked for',
            run: () => {
                if (document.querySelector('.o-mail-AISessionBox')) {
                    throw new Error(
                        'the AI sessions were listed before being asked for',
                    );
                }
            },
        },
        {
            trigger: '.o-mail-Chatter-aiSessions',
            content: 'Show the AI sessions',
            run: 'click',
        },
        {
            trigger: '.o-mail-AISessionBox:contains("AI Sessions")',
            content: 'The AI Sessions section renders on the linked record',
        },
        {
            trigger: '.o-mail-AISessionBox-item:contains("Tour Session")',
            content: 'The session linked to this record is listed',
        },
        {
            trigger:
                '.o-mail-AISessionBox-item .o-mail-AISessionBox-state.o-state-done',
            content: 'Its state is carried by the colour of a dot',
        },
    ],
});
