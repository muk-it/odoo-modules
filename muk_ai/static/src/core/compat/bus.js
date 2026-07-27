// @odoo-module

const REGISTRY = new WeakMap();

/**
 * Return the per-bus map of notification type to its live handler set.
 *
 * @param {object} bus the ``bus_service`` instance
 * @returns {Map<string, Set<Function>>} handlers grouped by notification type
 */
function channelsFor(bus) {
    if (!REGISTRY.has(bus)) {
        REGISTRY.set(bus, new Map());
    }
    return REGISTRY.get(bus);
}

/**
 * Listen for one notification type on the bus.
 *
 * Odoo 17's ``bus_service`` has no ``unsubscribe``, and its ``subscribe`` wraps
 * the callback in a fresh closure, so the listener it registers can never be
 * removed. A single real subscription per type is kept here and fanned out to a
 * mutable handler set, which makes unsubscribing possible without leaking a
 * listener per mount.
 *
 * @param {object} bus the ``bus_service`` instance
 * @param {string} type notification type to listen for
 * @param {(payload: any) => void} handler invoked with the notification payload
 */
export function busSubscribe(bus, type, handler) {
    const channels = channelsFor(bus);
    let handlers = channels.get(type);
    if (!handlers) {
        handlers = new Set();
        channels.set(type, handlers);
        bus.subscribe(type, (payload) => {
            for (const fn of [...handlers]) {
                fn(payload);
            }
        });
    }
    handlers.add(handler);
}

/**
 * Stop listening for a notification type previously passed to busSubscribe.
 *
 * @param {object} bus the ``bus_service`` instance
 * @param {string} type notification type used when subscribing
 * @param {(payload: any) => void} handler the original handler
 */
export function busUnsubscribe(bus, type, handler) {
    channelsFor(bus).get(type)?.delete(handler);
}
