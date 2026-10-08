import { GROUPABLE_TYPES } from '@web/search/utils/misc';

import { clientTools } from '@muk_ai/core/client_tools/client_tools';

const TEXT_FIELD_TYPES = [
    'char',
    'html',
    'many2many',
    'many2one',
    'one2many',
    'properties',
    'text',
];
const GRAPH_MODES = ['bar', 'line', 'pie'];
const GROUP_INTERVALS = ['year', 'quarter', 'month', 'week', 'day'];
const MODEL_ARGS = ['mode', 'order', 'stacked', 'cumulated'];

/**
 * Find a search item by its name or field name.
 * @param {object} searchModel the search model
 * @param {string[]} types the item types accepted
 * @param {string} name the name
 * @returns {object|undefined} the item
 */
function findItem(searchModel, types, name) {
    return searchModel.getSearchItems(
        (item) =>
            types.includes(item.type) && [item.name, item.fieldName].includes(name),
    )[0];
}

/**
 * List the names of the search items of some types, for an error report.
 * @param {object} searchModel the search model
 * @param {string[]} types the item types
 * @returns {string[]} the distinct names
 */
function itemNames(searchModel, types) {
    const items = searchModel.getSearchItems((item) => types.includes(item.type));
    return [
        ...new Set(
            items.map((item) => item.name || item.fieldName || item.description),
        ),
    ].filter(Boolean);
}

/**
 * Turn a search item on, at the requested interval for a date group-by.
 * @param {object} searchModel the search model
 * @param {object} item the search item
 * @param {string} [interval] the group-by interval
 */
function activate(searchModel, item, interval) {
    if (item.type === 'dateGroupBy') {
        const wanted = interval || item.defaultIntervalId;
        if (
            !(item.options || []).some(
                (option) => option.id === wanted && option.isActive,
            )
        ) {
            searchModel.toggleDateGroupBy(item.id, interval);
        }
    } else if (!item.isActive) {
        if (item.type === 'dateFilter') {
            searchModel.toggleDateFilter(item.id);
        } else {
            searchModel.toggleSearchItem(item.id);
        }
    }
}

/**
 * Label a facet the way the tool reports it and accepts it back.
 * @param {object} facet the facet
 * @returns {string} e.g. `groupBy: Country`
 */
function facetLabel(facet) {
    return `${facet.type}: ${(facet.values || []).join(' or ')}`;
}

const STEPS = {
    remove_facets(searchModel, names, report) {
        for (const name of names) {
            if (name === '*') {
                for (const facet of [...searchModel.facets]) {
                    searchModel.deactivateGroup(facet.groupId);
                }
                report.applied.push('removed:*');
                continue;
            }
            const types = ['filter', 'dateFilter', 'groupBy', 'dateGroupBy', 'field'];
            const item = findItem(searchModel, types, name);
            const wanted = name.toLowerCase();
            let matches = searchModel.facets.filter(
                (facet) => facetLabel(facet).toLowerCase() === wanted,
            );
            if (!matches.length) {
                matches = searchModel.facets.filter((facet) =>
                    (facet.values || []).some(
                        (value) => String(value).toLowerCase() === wanted,
                    ),
                );
            }
            const groupId = item?.isActive
                ? item.groupId
                : matches.length === 1 && matches[0].groupId;
            if (groupId) {
                searchModel.deactivateGroup(groupId);
                report.applied.push(`removed:${name}`);
            } else {
                report.issues.push(
                    matches.length > 1
                        ? `Several facets match "${name}" - use the full label.`
                        : `No active facet matches "${name}".`,
                );
                report.available.facets = searchModel.facets.map(facetLabel);
            }
        }
    },
    filters(searchModel, names, report) {
        for (const name of names) {
            const item = findItem(searchModel, ['filter', 'dateFilter'], name);
            if (item) {
                activate(searchModel, item);
                report.applied.push(`filter:${name}`);
            } else {
                report.issues.push(`Unknown filter "${name}".`);
                report.available.filters = itemNames(searchModel, [
                    'filter',
                    'dateFilter',
                ]);
            }
        }
    },
    group_bys(searchModel, names, report) {
        for (const name of names) {
            const [fieldName, interval] = name.split(':');
            if (interval && !GROUP_INTERVALS.includes(interval)) {
                report.issues.push(
                    `Unknown group-by interval "${interval}" (year, quarter, month, week or day).`,
                );
                continue;
            }
            const item = findItem(searchModel, ['groupBy', 'dateGroupBy'], fieldName);
            const field = searchModel.searchViewFields[fieldName];
            if (item) {
                activate(searchModel, item, interval);
            } else if (
                field?.groupable &&
                fieldName !== 'id' &&
                GROUPABLE_TYPES.includes(field.type)
            ) {
                searchModel.createNewGroupBy(fieldName, { interval });
            } else {
                report.issues.push(`Cannot group by "${name}".`);
                report.available.group_bys = itemNames(searchModel, [
                    'groupBy',
                    'dateGroupBy',
                ]);
                continue;
            }
            report.applied.push(`group_by:${name}`);
        }
    },
    searches(searchModel, terms, report) {
        for (const term of terms) {
            const separator = term.indexOf('=');
            if (separator === -1) {
                report.issues.push(
                    `Invalid search "${term}" (expected "field=value").`,
                );
                continue;
            }
            const fieldName = term.slice(0, separator);
            const value = term.slice(separator + 1);
            const item = findItem(searchModel, ['field'], fieldName);
            if (!item) {
                report.issues.push(`Unknown search field "${fieldName}".`);
                report.available.search_fields = itemNames(searchModel, ['field']);
                continue;
            }
            searchModel.addAutoCompletionValues(item.id, {
                value,
                label: value,
                operator:
                    item.operator ||
                    (TEXT_FIELD_TYPES.includes(item.fieldType) ? 'ilike' : '='),
            });
            report.applied.push(`search:${term}`);
        }
    },
};

/**
 * Add a JSON domain as facets, unless a pure conjunction already holds it.
 * @param {object} searchModel the search model
 * @param {string} domain the JSON-encoded domain
 * @param {object} report the report being built
 */
async function applyCustomDomain(searchModel, domain, report) {
    let parsed;
    try {
        parsed = JSON.parse(domain);
    } catch {
        parsed = null;
    }
    if (!Array.isArray(parsed)) {
        report.issues.push('custom_domain must be a JSON-encoded domain list.');
        return;
    }
    const active = searchModel.domain;
    const conditions = parsed.filter(Array.isArray);
    const pureAnd = !active.some((element) => element === '|' || element === '!');
    const held = JSON.stringify(active);
    if (
        pureAnd &&
        conditions.length &&
        conditions.every((cond) => held.includes(JSON.stringify(cond)))
    ) {
        report.applied.push(`domain:${domain} (already active)`);
    } else if (parsed.length) {
        await searchModel.splitAndAddDomain(parsed);
        report.applied.push(`domain:${domain}`);
    }
}

/**
 * Apply the graph or pivot display arguments to the view's model.
 * @param {object} target the adjustable view
 * @param {object} args the tool arguments
 * @param {object} report the report being built
 * @returns {Promise<void>} resolved once the model reloaded
 */
async function applyViewModel({ controller, viewType }, args, report) {
    const measures = args.measures || [];
    if (!measures.length && !MODEL_ARGS.some((key) => args[key] !== undefined)) {
        return;
    }
    if (!['pivot', 'graph'].includes(viewType)) {
        report.issues.push(
            'measures, mode, order, stacked and cumulated only apply to pivot or graph views.',
        );
        return;
    }
    const model = controller.model;
    const known = model.metaData.measures;
    const unknown = (measure) => {
        report.issues.push(`Unknown ${viewType} measure "${measure}".`);
        report.available.measures = Object.keys(known || {});
    };
    if (viewType === 'pivot') {
        for (const measure of measures) {
            if (known && !(measure in known)) {
                unknown(measure);
            } else if (!model.metaData.activeMeasures.includes(measure)) {
                await model.toggleMeasure(measure);
                report.applied.push(`measure:${measure}`);
            }
        }
        return;
    }
    const update = {};
    if (measures[0] && known && !(measures[0] in known)) {
        unknown(measures[0]);
    } else if (measures[0]) {
        update.measure = measures[0];
    }
    if (args.mode !== undefined) {
        if (GRAPH_MODES.includes(args.mode)) {
            update.mode = args.mode;
        } else {
            report.issues.push(`Unknown graph mode "${args.mode}" (bar, line or pie).`);
        }
    }
    if (args.order !== undefined) {
        const order = String(args.order).toUpperCase();
        if (['ASC', 'DESC'].includes(order)) {
            update.order = order;
        } else {
            report.issues.push(`Unknown graph order "${args.order}".`);
        }
    }
    for (const key of ['stacked', 'cumulated']) {
        if (args[key] !== undefined) {
            update[key] = Boolean(args[key]);
        }
    }
    if (Object.keys(update).length) {
        await model.updateMetaData(update);
        report.applied.push(
            ...Object.entries(update).map(([key, value]) => `graph_${key}:${value}`),
        );
    }
}

/**
 * Apply an `adjust_search` tool call to the view on screen: switch the view
 * type first, then change the facets, the custom domain and the graph or
 * pivot display, and pin the adjusted view before reporting.
 * @param {object} args the tool arguments
 * @param {object} chat the AI chat plugin
 * @returns {Promise<object>} the report posted back to the session
 */
export async function applyAdjustSearch(args, chat) {
    const report = { applied: [], issues: [], available: {} };
    if (args.view_type) {
        try {
            await chat.action.switchView(args.view_type);
        } catch {
            report.issues.push(`Could not switch to view type "${args.view_type}".`);
        }
    }
    const target = await chat.adjustTarget();
    if (!target) {
        return {
            note:
                'No adjustable view is open in this tab: the user must have a list, kanban, ' +
                'pivot or graph view open under the chat window. Form views cannot be ' +
                'adjusted - pass view_type or use open_view instead.',
        };
    }
    const searchModel = target.controller.env.searchModel;
    const query = JSON.stringify(searchModel.query);
    const rendered = target.rendered();
    if (args.view_type && target.viewType !== args.view_type) {
        report.issues.push(
            `View did not switch to "${args.view_type}" (still "${target.viewType}").`,
        );
    } else if (args.view_type) {
        report.applied.push(`view:${args.view_type}`);
    }
    for (const [key, step] of Object.entries(STEPS)) {
        step(searchModel, args[key] || [], report);
    }
    if (args.custom_domain) {
        await applyCustomDomain(searchModel, args.custom_domain, report);
    }
    if (JSON.stringify(searchModel.query) !== query) {
        await rendered;
    }
    await applyViewModel(target, args, report);
    await chat.pushContext(target.build());
    const result = {
        model: searchModel.resModel,
        view_type: target.viewType,
        applied: report.applied,
        facets: searchModel.facets.map(facetLabel),
    };
    if (report.issues.length) {
        result.issues = report.issues;
    }
    if (Object.keys(report.available).length) {
        result.available = report.available;
    }
    return result;
}

clientTools.add('adjust_search', { execute: applyAdjustSearch });
