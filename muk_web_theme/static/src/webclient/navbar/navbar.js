import { onMounted, onWillUnmount } from '@odoo/owl';
import { patch } from '@web/core/utils/patch';
import { debounce } from '@web/core/utils/timing';
import { NavBar } from '@web/webclient/navbar/navbar';

/** Fit the menu again whenever the systray takes a different amount of room. */
patch(NavBar.prototype, {
    setup() {
        super.setup();
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
