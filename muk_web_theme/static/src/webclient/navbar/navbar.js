/** @odoo-module */

import { patch } from '@web/core/utils/patch';

import { NavBar } from '@web/webclient/navbar/navbar';
import { AppsMenu } from "@muk_web_theme/webclient/appsmenu/appsmenu";

patch(NavBar, {
    components: {
        ...NavBar.components,
        AppsMenu,
    },
});
