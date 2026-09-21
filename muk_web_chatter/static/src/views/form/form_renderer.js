import { session } from '@web/session';
import { patch } from '@web/core/utils/patch';
import { browser } from '@web/core/browser/browser';
import { FormRenderer } from '@web/views/form/form_renderer';

import { signal } from '@odoo/owl';

import '@mail/chatter/web/form_renderer';

const BOTTOM_LAYOUTS = {
    SIDE_CHATTER: 'BOTTOM_CHATTER',
    EXTERNAL_COMBO_XXL: 'EXTERNAL_COMBO',
};
const MIN_CHATTER_WIDTH = 50;
const MIN_SHEET_WIDTH = 250;
const STORAGE_KEY = 'muk_web_chatter.width';

/** Place the chatter per user preference and wire its drag-resize handle. */
patch(FormRenderer.prototype, {
    setup() {
        super.setup();
        this.chatterWidth = signal(
            Number(browser.localStorage.getItem(STORAGE_KEY)) || 0,
        );
    },
    /** Map the aside layouts onto their bottom counterparts. */
    mailLayout() {
        const layout = super.mailLayout(...arguments);
        if (session.chatter_position !== 'bottom') {
            return layout;
        }
        return BOTTOM_LAYOUTS[layout] ?? layout;
    },
    onStartChatterResize(ev) {
        if (ev.button !== 0) {
            return;
        }
        const container = ev.currentTarget.parentElement;
        const startX = ev.pageX;
        const startWidth = container.offsetWidth;
        const drag = new AbortController();
        document.addEventListener(
            'mousemove',
            (moveEvent) =>
                this.chatterWidth.set(
                    Math.min(
                        Math.max(
                            MIN_CHATTER_WIDTH,
                            startWidth - (moveEvent.pageX - startX),
                        ),
                        Math.max(
                            container.parentElement.offsetWidth - MIN_SHEET_WIDTH,
                            MIN_SHEET_WIDTH,
                        ),
                    ),
                ),
            { signal: drag.signal },
        );
        document.addEventListener(
            'mouseup',
            () => {
                drag.abort();
                document.body.classList.remove('user-select-none');
                browser.localStorage.setItem(STORAGE_KEY, this.chatterWidth());
            },
            { signal: drag.signal },
        );
        document.body.classList.add('user-select-none');
    },
    onDoubleClickChatterResize() {
        browser.localStorage.removeItem(STORAGE_KEY);
        this.chatterWidth.set(0);
    },
});
