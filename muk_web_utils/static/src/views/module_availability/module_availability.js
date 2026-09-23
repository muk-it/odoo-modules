const cache = new Map();

/**
 * Derive the technical module name a ``module_<name>`` settings field installs.
 * @param {string} fieldName the settings field name
 * @returns {string} the module name, or an empty string for other fields
 */
export function moduleNameFromField(fieldName) {
    return fieldName.startsWith('module_') ? fieldName.slice(7) : '';
}

/**
 * Check whether an Odoo module exists on the instance, caching the result per
 * module name to avoid repeated lookups.
 * @param {object} orm the ORM plugin
 * @param {string} moduleName the technical module name to probe
 * @returns {Promise<boolean>} resolves true when the module is available
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
