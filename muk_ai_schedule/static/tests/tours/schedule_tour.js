import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('muk_ai_schedule_tour', {
    steps: () => [
        {
            trigger: '.o_kanban_record:contains("Tour Digest")',
            content: 'The seeded schedule card is rendered in the kanban',
        },
        {
            trigger: '.o_kanban_record:contains("Tour Digest") .mk_schedule_countdown',
            content: 'The countdown widget renders on the schedule card',
        },
        {
            trigger: '.o_kanban_record:contains("Tour Digest")',
            content: 'Open the schedule form',
            run: 'click',
        },
        {
            trigger: '.o_form_view .mk_schedule_countdown',
            content: 'The Next Call countdown widget renders on the form',
        },
        {
            trigger: '.o_notebook .nav-link:contains("Caps")',
            content: 'Open the Caps notebook tab',
            run: 'click',
        },
        {
            trigger: '.o_notebook [name="max_cost_eur"]',
            content: 'The per-schedule caps fields are shown',
        },
    ],
});
