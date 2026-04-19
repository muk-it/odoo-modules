import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("muk_mcp_playground_tour", {
    steps: () => [
        {
            trigger: ".o_muk_mcp_playground",
        },
        {
            trigger: ".o_muk_mcp_keybar button:contains(Generate new)",
            run: "click",
        },
        {
            trigger: ".o_muk_mcp_keybar .badge.text-bg-success",
        },
        {
            trigger: ".o_muk_mcp_list input[type=search]",
            run: "edit whoami",
        },
        {
            trigger: ".o_muk_mcp_tool:contains(whoami)",
            run: "click",
        },
        {
            trigger: ".o_muk_mcp_detail button:contains(Try it):not([disabled])",
            run: "click",
        },
        {
            trigger: ".alert.alert-success",
        },
    ],
});
