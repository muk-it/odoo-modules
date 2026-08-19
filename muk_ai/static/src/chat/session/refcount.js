/**
 * Count how many holders claim each key.
 *
 * Two surfaces can show one chat at once — a popped-out window over the
 * full page — so what the first of them releases has to stay held until the
 * last one lets go.
 * @returns {{acquire: Function, release: Function, has: Function}} the counter
 */
export function makeRefCount() {
    const counts = new Map();
    return {
        /**
         * Claim a key and tell whether this is the first claim.
         * @param {*} key the counted key
         * @returns {boolean} true when nobody held it yet
         */
        acquire(key) {
            const count = counts.get(key) || 0;
            counts.set(key, count + 1);
            return count === 0;
        },
        /**
         * Let a key go and tell whether that was the last holder.
         * @param {*} key the counted key
         * @returns {boolean} true when nobody holds it any more
         */
        release(key) {
            const count = counts.get(key) || 0;
            if (count <= 1) {
                counts.delete(key);
                return count === 1;
            }
            counts.set(key, count - 1);
            return false;
        },
        /**
         * Tell whether anybody currently holds the key.
         * @param {*} key the counted key
         * @returns {boolean} true while at least one holder remains
         */
        has(key) {
            return counts.has(key);
        },
    };
}
