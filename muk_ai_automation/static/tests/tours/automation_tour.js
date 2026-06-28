import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('muk_ai_automation_tour', {
    steps: () => [
        {
            trigger: '.o-mail-AISessionBox-header:contains("AI Sessions")',
            content: 'The AI Sessions chatter box renders on the linked record',
        },
        {
            trigger: '.o-mail-AISessionBox-header',
            content: 'Expand the AI Sessions box',
            run: 'click',
        },
        {
            trigger: '.o-mail-AISessionBox-item:contains("Tour Session")',
            content: 'The session linked to this record is listed',
        },
    ],
});
