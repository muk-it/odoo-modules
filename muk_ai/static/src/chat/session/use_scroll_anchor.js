import { onMounted, onPatched, onWillUnmount, useRef, useState } from '@odoo/owl';

const SCROLL_NEAR_BOTTOM = 160;

export function useChatScrollAnchor(refName = 'scroll') {
    const scrollRef = useRef(refName);
    const state = useState({ atBottom: true });
    const anchor = { auto: true };

    function distanceFromBottom() {
        const el = scrollRef.el;
        if (!el) {
            return 0;
        }
        return el.scrollHeight - el.scrollTop - el.clientHeight;
    }

    function scrollToBottom(force) {
        const el = scrollRef.el;
        if (!el) {
            return;
        }
        if (!force && distanceFromBottom() > SCROLL_NEAR_BOTTOM) {
            anchor.auto = false;
            state.atBottom = false;
            return;
        }
        anchor.auto = true;
        state.atBottom = true;
        requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
        });
    }

    function onScroll() {
        const near = distanceFromBottom() <= SCROLL_NEAR_BOTTOM;
        state.atBottom = near;
        anchor.auto = near;
    }
    onMounted(() => {
        scrollToBottom(true);
        const el = scrollRef.el;
        if (el) {
            el.addEventListener('scroll', onScroll, { passive: true });
        }
    });

    onPatched(() => {
        if (anchor.auto) {
            scrollToBottom();
        }
    });

    onWillUnmount(() => {
        const el = scrollRef.el;
        if (el) {
            el.removeEventListener('scroll', onScroll);
        }
    });

    return { scrollRef, scrollToBottom, state };
}
