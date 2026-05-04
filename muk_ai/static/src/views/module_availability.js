const cache = new Map();

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
