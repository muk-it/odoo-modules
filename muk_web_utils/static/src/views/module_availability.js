const cache = new Map();

/**
 * Check whether an Odoo module exists on the instance, caching the result per
 * module name to avoid repeated lookups.
 * @param {object} orm the ORM service
 * @param {string} moduleName the technical module name to probe
 * @returns {Promise<boolean>} resolves true when the module is installed/available
 */
export function probeModuleAvailable(orm, moduleName) {
    if (!moduleName) {
        return Promise.resolve(false);
    }
    if (!cache.has(moduleName)) {
        const promise = orm
            .searchCount('ir.module.module', [['name', '=', moduleName]])
            .then((count) => count > 0)
            .catch(() => false);
        cache.set(moduleName, promise);
    }
    return cache.get(moduleName);
}
