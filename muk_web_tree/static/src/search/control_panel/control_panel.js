import { patch } from '@web/core/utils/patch';
import { ControlPanel } from '@web/search/control_panel/control_panel';

import '@muk_web_refresh/search/control_panel/control_panel';

/** Allow the auto refresh on a treelist. */
patch(ControlPanel.prototype, {
    checkAutoLoadAvailability() {
        return (
            this.env.config.viewType === 'treelist' || super.checkAutoLoadAvailability()
        );
    },
});
