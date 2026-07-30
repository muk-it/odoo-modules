import { onMounted, onPatched, onWillUnmount, useRef, useState } from '@odoo/owl';

const SCROLL_NEAR_BOTTOM = 160;
const SCROLL_NEAR_TOP_DEFAULT = 200;

/**
 * Hook keeping a scroller pinned to the bottom while the user is near it.
 * @param {string} refName t-ref name of the scroll container
 * @returns {object} { scrollRef, scrollToBottom, state }
 */
export function useChatScrollAnchor(refName = 'scroll') {
    const scrollRef = useRef(refName);
    const state = useState({ atBottom: true });
    const anchor = { auto: true, forcing: false };
    function distanceFromBottom() {
        const el = scrollRef.el;
        if (!el) {
            return 0;
        }
        return el.scrollHeight - el.scrollTop - el.clientHeight;
    }
    /**
     * Scroll to the bottom, re-arming auto-follow unless the user scrolled up.
     * A forced scroll stays pending until its frame lands, so a render in
     * between cannot measure the grown scrollHeight against an unmoved
     * scrollTop and disarm auto-follow before the scroll ran.
     * @param {boolean} force scroll even when the user is far from the bottom
     */
    function scrollToBottom(force) {
        const el = scrollRef.el;
        if (!el) {
            return;
        }
        if (!force && !anchor.forcing && distanceFromBottom() > SCROLL_NEAR_BOTTOM) {
            anchor.auto = false;
            state.atBottom = false;
            return;
        }
        anchor.auto = true;
        state.atBottom = true;
        anchor.forcing = anchor.forcing || !!force;
        requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
            anchor.forcing = false;
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

/**
 * Invoke a callback once when the user scrolls up near the top of a scroller.
 * @param {object} scrollerRef t-ref to the scroll container
 * @param {Function} callback handler run near the top (may be async)
 * @param {number} thresholdPx distance from top that triggers the callback
 */
export function onScrollUpNearTop(
    scrollerRef,
    callback,
    thresholdPx = SCROLL_NEAR_TOP_DEFAULT,
) {
    let lastScrollTop = null;
    let pending = false;
    function listener() {
        const el = scrollerRef.el;
        if (!el) {
            return;
        }
        const top = el.scrollTop;
        const direction =
            lastScrollTop === null
                ? 'init'
                : top < lastScrollTop
                  ? 'up'
                  : top > lastScrollTop
                    ? 'down'
                    : 'same';
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

/**
 * Run an async mutation while preserving the scroller's distance from bottom.
 * @param {object} scrollerRef t-ref to the scroll container
 * @param {Function} fn async mutation to run
 * @returns {Promise<void>}
 */
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
