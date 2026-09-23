import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';

import { NavBar } from '@web/webclient/navbar/navbar';
import { AppsMenu } from '@muk_web_theme/webclient/appsmenu/appsmenu';

/** Give the navbar the app-menu service the themed apps menu reads. */
patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.appMenuService = useService('app_menu');
    },
});

/** Register the themed AppsMenu as a navbar component. */
patch(NavBar, {
    components: {
        ...NavBar.components,
        AppsMenu,
    },
});
