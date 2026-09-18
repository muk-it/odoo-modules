import { registry } from '@web/core/registry';

// Walk a finished delegation the way a user does: pick the conversation out
// of the sidebar, read the strip above the composer, open the row, step into
// the subagent's own transcript and come back. Every roster value on screen
// arrives over the real snapshot RPCs.
registry.category('web_tour.tours').add('muk_ai_subagents_run_tour', {
    steps: () => [
        {
            trigger: '.mk_sidebar_item:contains("Tour lead")',
            content: 'The conversation that delegated is in the sidebar',
            run: 'click',
        },
        {
            trigger: '.mk_messages_wrap',
            content: 'Its transcript opens',
        },
        {
            // A subagent is not a chat of its own, so it must not appear here.
            trigger: 'body:not(:has(.mk_sidebar_item:contains("Tour worker")))',
            content: 'The subagent is not offered as a conversation to open',
        },
        {
            trigger: '.mk_subagent_spawn_label',
            content: 'The turn that delegated says so, with a dot per subagent',
        },
        {
            trigger: '.mk_subagent_result_name:contains("Tour worker")',
            content: 'The report card names the subagent that answered',
        },
        {
            trigger: '.mk_run_strip_line',
            content: 'One quiet line above the composer summarises the run',
            run: 'click',
        },
        {
            // A run that has ended folds its finished subagents away, so the
            // strip stays one line until someone asks for the detail.
            trigger: '.mk_agents_done_toggle',
            content: 'Expanding it offers the subagents that reported',
            run: 'click',
        },
        {
            trigger: '.mk_agent_row_name:contains("Tour worker")',
            content: 'One row per subagent, named',
            run: 'click',
        },
        {
            trigger: '.mk_agent_detail_open',
            content: 'The row opens into its detail, which offers the transcript',
            run: 'click',
        },
        {
            trigger: '.mk_subagent_child',
            content: 'The subagent takes the room the conversation had',
        },
        {
            trigger: '.mk_subagent_crumb_child:contains("Tour worker")',
            content: 'The breadcrumb names it',
        },
        {
            trigger: '.mk_bubble_assistant:contains("Counted 40 orders")',
            content: 'Its own answer is on screen, read from its own session',
        },
        {
            // One composer, wherever you are: the chat never grows a second.
            trigger: '.mk_composer textarea',
            content: 'There is exactly one composer',
        },
        {
            trigger: '.mk_subagent_back',
            content: 'Go back to the conversation that delegated',
            run: 'click',
        },
        {
            trigger: '.mk_messages_wrap',
            content: 'The parent transcript is back',
        },
        {
            trigger: 'body:not(:has(.mk_subagent_child))',
            content: 'And the subagent view is gone',
        },
    ],
});

// A subagent is an ordinary session, so it is inspectable in the backend —
// from the one Sessions list, through its own filter and group-by, rather
// than through a menu of its own.
registry.category('web_tour.tours').add('muk_ai_subagents_backend_tour', {
    steps: () => [
        {
            trigger: '.o_list_view',
            content: 'The Sessions list is the one door to every session',
        },
        {
            trigger: '.o_control_panel .o_searchview_dropdown_toggler',
            content: 'Open the search panel',
            run: 'click',
        },
        {
            // An exact match: "With Subagents" sits in the same menu.
            trigger: '.o_filter_menu .o_menu_item:contains(/^Subagents$/)',
            content: 'Keep only the subagents',
            run: 'click',
        },
        {
            trigger: '.o_group_by_menu .o_menu_item:contains("Parent Session")',
            content: 'Group them by the conversation that ran them',
            run: 'click',
        },
        {
            trigger: '.o_control_panel .o_searchview_dropdown_toggler',
            content: 'Close the search panel',
            run: 'click',
        },
        {
            trigger: '.o_group_header:contains("Tour lead")',
            content: 'Subagents are grouped under the conversation that ran them',
            run: 'click',
        },
        {
            trigger: '.o_list_view td[name="name"]:contains("Tour worker")',
            content: 'Open it',
            run: 'click',
        },
        {
            // What makes it a subagent is on its own page of the form, and a
            // page nobody opened is not in the document.
            trigger: '.o_form_view .o_notebook .nav-link:contains("Delegation")',
            content: 'Its delegation page is offered',
            run: 'click',
        },
        {
            trigger: '.o_form_view [name="parent_session_id"]',
            content: 'It names the conversation it belongs to',
        },
        {
            trigger: '.o_form_view [name="stop_reason"]',
            content: 'And why it ended',
        },
    ],
});
