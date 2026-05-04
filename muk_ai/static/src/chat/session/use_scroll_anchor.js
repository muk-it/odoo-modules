import { onMounted, onPatched, onWillUnmount, useRef, useState } from '@odoo/owl';

const SCROLL_NEAR_BOTTOM = 160;
const SCROLL_NEAR_TOP_DEFAULT = 200;

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

export function onScrollUpNearTop(scrollerRef, callback, thresholdPx = SCROLL_NEAR_TOP_DEFAULT) {
    let lastScrollTop = null;
    let pending = false;
    function listener() {
        const el = scrollerRef.el;
        if (!el) {
            return;
        }
        const top = el.scrollTop;
        const direction = lastScrollTop === null
            ? 'init'
            : (top < lastScrollTop ? 'up' : (top > lastScrollTop ? 'down' : 'same'));
        lastScrollTop = top;
        if (pending) {
            return;
        }
        if (direction !== 'up') {
            return;
        }
        if (top > thresholdPx) {
            return;
        }
        pending = true;
        Promise.resolve(callback()).finally(() => {
            pending = false;
        });
    }
    onMounted(() => {
        const el = scrollerRef.el;
        if (el) {
            lastScrollTop = el.scrollTop;
            el.addEventListener('scroll', listener, { passive: true });
        }
    });
    onWillUnmount(() => {
        const el = scrollerRef.el;
        if (el) {
            el.removeEventListener('scroll', listener);
        }
    });
}

export async function preserveAnchor(scrollerRef, fn) {
    const el = scrollerRef.el;
    const savedDelta = el ? el.scrollHeight - el.scrollTop : 0;
    try {
        await fn();
    } finally {
        if (el) {
            requestAnimationFrame(() => {
                el.scrollTop = el.scrollHeight - savedDelta;
            });
        }
    }
}
