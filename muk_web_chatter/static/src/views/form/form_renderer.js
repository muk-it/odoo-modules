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
const CHATTER_WIDTH_PROPERTY = '--mk-Chatter-width';
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
        let resized = false;
        document.addEventListener(
            'mousemove',
            (moveEvent) => {
                const width = Math.max(
                    MIN_CHATTER_WIDTH,
                    startWidth - (moveEvent.pageX - startX),
                );
                container.style.setProperty(CHATTER_WIDTH_PROPERTY, `${width}px`);
                resized = true;
            },
            { signal: drag.signal },
        );
        document.addEventListener(
            'mouseup',
            () => {
                drag.abort();
                document.body.classList.remove('user-select-none');
                if (resized) {
                    const width = container.offsetWidth;
                    container.style.setProperty(CHATTER_WIDTH_PROPERTY, `${width}px`);
                    this.chatterWidth.set(width);
                    browser.localStorage.setItem(STORAGE_KEY, width);
                }
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
