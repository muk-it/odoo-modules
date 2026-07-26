import { describe, expect, test } from '@odoo/hoot';

import { probeModuleAvailable } from '@muk_web_utils/views/module_availability';

describe.current.tags('muk_web_utils');

/**
 * Build a stub ORM recording the domains it was queried with.
 * @param {number|Error} outcome the count to resolve with, or an error to reject
 * @returns {object} an object with a ``searchCount`` method and a ``calls`` log
 */
function makeOrm(outcome) {
    const calls = [];
    return {
        calls,
        searchCount(model, domain) {
            calls.push([model, domain]);
            if (outcome instanceof Error) {
                return Promise.reject(outcome);
            }
            return Promise.resolve(outcome);
        },
    };
}

test('an empty module name resolves false without querying', async () => {
    const orm = makeOrm(1);
    expect(await probeModuleAvailable(orm, '')).toBe(false);
    expect(await probeModuleAvailable(orm, undefined)).toBe(false);
    expect(orm.calls).toHaveLength(0);
});

test('an existing module resolves true and queries ir.module.module by name', async () => {
    const orm = makeOrm(1);
    expect(await probeModuleAvailable(orm, 'muk_probe_present')).toBe(true);
    expect(orm.calls).toHaveLength(1);
    expect(orm.calls[0][0]).toBe('ir.module.module');
    expect(orm.calls[0][1]).toEqual([['name', '=', 'muk_probe_present']]);
});

test('a missing module resolves false', async () => {
    const orm = makeOrm(0);
    expect(await probeModuleAvailable(orm, 'muk_probe_absent')).toBe(false);
});

test('the result is cached so the module is probed only once', async () => {
    const orm = makeOrm(1);
    await probeModuleAvailable(orm, 'muk_probe_cached');
    await probeModuleAvailable(orm, 'muk_probe_cached');
    const other = makeOrm(0);
    expect(await probeModuleAvailable(other, 'muk_probe_cached')).toBe(true);
    expect(orm.calls).toHaveLength(1);
    expect(other.calls).toHaveLength(0);
});

test('a failing probe resolves false instead of rejecting', async () => {
    const orm = makeOrm(new Error('no access'));
    expect(await probeModuleAvailable(orm, 'muk_probe_error')).toBe(false);
});
