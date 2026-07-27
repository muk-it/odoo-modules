// @odoo-module

const HANDLERS = new WeakMap();

/**
 * Return the per-bus map of notification type to wrapped listeners.
 *
 * @param {object} bus the ``bus_service`` instance
 * @returns {Map} registry of original handler to its wrapper
 */
function registryFor(bus) {
    if (!HANDLERS.has(bus)) {
        HANDLERS.set(bus, new Map());
    }
    return HANDLERS.get(bus);
}

/**
 * Listen for one notification type on the bus.
 *
 * Stands in for ``bus_service.subscribe``, which only exists from 17.0 on.
 * Odoo 16 emits a single ``notification`` event carrying every payload.
 *
 * @param {object} bus the ``bus_service`` instance
 * @param {string} type notification type to filter on
 * @param {(payload: any) => void} handler invoked with the matching payload
 */
export function busSubscribe(bus, type, handler) {
    const wrapper = ({ detail: notifications }) => {
        for (const notification of notifications || []) {
            if (notification.type === type) {
                handler(notification.payload);
            }
        }
    };
    registryFor(bus).set(handler, wrapper);
    bus.addEventListener('notification', wrapper);
    bus.start();
}

/**
 * Stop listening for a notification type previously passed to busSubscribe.
 *
 * @param {object} bus the ``bus_service`` instance
 * @param {string} type notification type used when subscribing
 * @param {(payload: any) => void} handler the original handler
 */
export function busUnsubscribe(bus, type, handler) {
    const registry = registryFor(bus);
    const wrapper = registry.get(handler);
    if (wrapper) {
        bus.removeEventListener('notification', wrapper);
        registry.delete(handler);
    }
}
