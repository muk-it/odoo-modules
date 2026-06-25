import { useEffect } from '@odoo/owl';
import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';

import { TourPointer } from '@web_tour/js/tour_pointer/tour_pointer';

/** Flip the pointer below its anchor when the anchor sits outside the active UI element. */
patch(TourPointer.prototype, {
    setup() {
        super.setup(...arguments);
        const uiService = useService('ui');
        useEffect(
            (anchor) => {
                if (anchor) {
                    const activeEl = uiService.activeElement;
                    if (
                        !this.state ||
                        !activeEl ||
                        typeof activeEl.contains !== 'function'
                    ) {
                        return;
                    }
                    this.state.triggerBelow = !activeEl.contains(anchor);
                }
            },
            () => [this.props.pointerState.anchor],
        );
    },
});
