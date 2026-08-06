import { onMounted, onWillUnmount } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { debounce } from '@web/core/utils/timing';

import { NavBar } from '@web/webclient/navbar/navbar';
import { AppsMenu } from '@muk_web_theme/webclient/appsmenu/appsmenu';

/** Add the app-menu service to the navbar setup. */
patch(NavBar.prototype, {
    /**
     * Fit the menu again whenever the systray takes a different amount of room.
     *
     * The navbar sizes its menu to what the systray leaves, and does so again
     * when the window is resized or an item joins or leaves the systray — but
     * not when an item it already shows grows. Counters arriving after the
     * first paint do exactly that, and the menu is left running underneath
     * them until something else happens to trigger a fit.
     *
     * @override
     */
    setup() {
        super.setup();
        this.appMenuService = useService('app_menu');
        const refit = debounce(() => this.adapt(), 250);
        let observer = null;
        onMounted(() => {
            const systray = this.root.el?.querySelector('.o_menu_systray');
            if (systray) {
                observer = new ResizeObserver(refit);
                observer.observe(systray);
            }
        });
        onWillUnmount(() => {
            observer?.disconnect();
            refit.cancel();
        });
    },
});

/** Register the themed AppsMenu as a navbar component. */
patch(NavBar, {
    components: {
        ...NavBar.components,
        AppsMenu,
    },
});
