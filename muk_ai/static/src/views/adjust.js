import { onMounted, onWillUnmount } from '@odoo/owl';

import { GROUPABLE_TYPES } from '@web/search/utils/misc';

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
const SWITCH_TARGET_TIMEOUT_MS = 2000;
const SWITCH_TARGET_POLL_MS = 100;

const targets = [];

/**
 * Register a view controller as the adjustable target for the AI
 * `adjust_search` client tool while it is mounted. Controllers rendered
 * inside a dialog (e.g. a record picker) never register - the tool must
 * adjust the view the user is talking about, not a transient popup.
 * @param {object} controller the list/kanban/pivot/graph controller
 */
export function useAdjustTarget(controller) {
    if (controller.env.inDialog) {
        return;
    }
    onMounted(() => targets.push(controller));
    onWillUnmount(() => {
        const index = targets.indexOf(controller);
        if (index >= 0) {
            targets.splice(index, 1);
        }
    });
}

/**
 * Return the most recently mounted adjustable controller, waiting briefly
 * for one to mount (a view switch registers its controller asynchronously).
 * @returns {Promise<object|null>} the active controller, or null
 */
async function waitForTarget() {
    let waited = 0;
    while (!targets.length && waited < SWITCH_TARGET_TIMEOUT_MS) {
        await new Promise((resolve) => setTimeout(resolve, SWITCH_TARGET_POLL_MS));
        waited += SWITCH_TARGET_POLL_MS;
    }
    return targets[targets.length - 1] || null;
}

function findItem(searchModel, types, name) {
    const [item] = searchModel.getSearchItems(
        (i) => types.includes(i.type) && [i.name, i.fieldName].includes(name),
    );
    return item;
}

function itemNames(searchModel, types) {
    const names = searchModel
        .getSearchItems((i) => types.includes(i.type))
        .map((i) => i.name || i.fieldName || i.description);
    return [...new Set(names.filter(Boolean))];
}

function activateItem(searchModel, item, interval = undefined) {
    if (item.type === 'dateGroupBy') {
        // isActive covers ANY interval; check the one actually requested
        const target = interval || item.defaultIntervalId;
        const intervalActive = (item.options || []).some(
            (option) => option.id === target && option.isActive,
        );
        if (!intervalActive) {
            searchModel.toggleDateGroupBy(item.id, interval);
        }
        return;
    }
    if (item.isActive) {
        return;
    }
    if (item.type === 'dateFilter') {
        searchModel.toggleDateFilter(item.id);
    } else {
        searchModel.toggleSearchItem(item.id);
    }
}

function applyFilters(searchModel, names, report) {
    for (const name of names) {
        const item = findItem(searchModel, ['filter', 'dateFilter'], name);
        if (!item) {
            report.issues.push(`Unknown filter "${name}".`);
            report.available.filters = itemNames(searchModel, ['filter', 'dateFilter']);
            continue;
        }
        activateItem(searchModel, item);
        report.applied.push(`filter:${name}`);
    }
}

function applyGroupBys(searchModel, names, report) {
    for (const name of names) {
        const [fieldName, interval] = name.split(':');
        if (interval && !GROUP_INTERVALS.includes(interval)) {
            report.issues.push(
                `Unknown group-by interval "${interval}" ` +
                    '(year, quarter, month, week or day).',
            );
            continue;
        }
        const item = findItem(searchModel, ['groupBy', 'dateGroupBy'], fieldName);
        if (item) {
            activateItem(searchModel, item, interval);
            report.applied.push(`group_by:${name}`);
            continue;
        }
        const field = searchModel.searchViewFields[fieldName];
        if (
            field &&
            field.groupable &&
            fieldName !== 'id' &&
            GROUPABLE_TYPES.includes(field.type)
        ) {
            searchModel.createNewGroupBy(fieldName, { interval });
            report.applied.push(`group_by:${name}`);
        } else {
            report.issues.push(`Cannot group by "${name}".`);
            report.available.group_bys = itemNames(searchModel, [
                'groupBy',
                'dateGroupBy',
            ]);
        }
    }
}

function applySearches(searchModel, terms, report) {
    for (const term of terms) {
        const separator = term.indexOf('=');
        if (separator === -1) {
            report.issues.push(`Invalid search "${term}" (expected "field=value").`);
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
}

function facetLabel(facet) {
    return `${facet.type}: ${(facet.values || []).join(' or ')}`;
}

function findFacetByLabel(searchModel, name) {
    const wanted = name.toLowerCase();
    const matching = (predicate) => searchModel.facets.filter(predicate);
    let matches = matching((facet) => facetLabel(facet).toLowerCase() === wanted);
    if (!matches.length) {
        matches = matching((facet) =>
            (facet.values || []).some(
                (value) => String(value).toLowerCase() === wanted,
            ),
        );
    }
    return {
        facet: matches.length === 1 ? matches[0] : null,
        ambiguous: matches.length > 1,
    };
}

function removeFacets(searchModel, names, report) {
    for (const name of names) {
        if (name === '*') {
            for (const facet of [...searchModel.facets]) {
                searchModel.deactivateGroup(facet.groupId);
            }
            report.applied.push('removed:*');
            continue;
        }
        const item = findItem(
            searchModel,
            ['filter', 'dateFilter', 'groupBy', 'dateGroupBy', 'field'],
            name,
        );
        if (item && item.isActive) {
            searchModel.deactivateGroup(item.groupId);
            report.applied.push(`removed:${name}`);
            continue;
        }
        // the reported facet strings ("groupBy: Country") are valid handles too
        const { facet, ambiguous } = findFacetByLabel(searchModel, name);
        if (facet) {
            searchModel.deactivateGroup(facet.groupId);
            report.applied.push(`removed:${name}`);
        } else {
            report.issues.push(
                ambiguous
                    ? `Several facets match "${name}" - use the full label.`
                    : `No active facet matches "${name}".`,
            );
            report.available.facets = searchModel.facets.map(facetLabel);
        }
    }
}

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
    if (!parsed.length) {
        return;
    }
    // re-sending an already-active condition must not stack a second facet;
    // only safe to skip when the active domain is a pure conjunction — under
    // '|' or '!' a contained condition is not actually enforced
    const activeDomain = searchModel.domain;
    const active = JSON.stringify(activeDomain);
    const pureAnd = !activeDomain.some((element) => element === '|' || element === '!');
    const conditions = parsed.filter((element) => Array.isArray(element));
    if (
        pureAnd &&
        conditions.length &&
        conditions.every((element) => active.includes(JSON.stringify(element)))
    ) {
        report.applied.push(`domain:${domain} (already active)`);
        return;
    }
    await searchModel.splitAndAddDomain(parsed);
    report.applied.push(`domain:${domain}`);
}

function applyGraphModel(model, args, report) {
    const metaData = model.metaData || {};
    const update = {};
    const measure = (args.measures || [])[0];
    if (measure) {
        if (metaData.measures && !(measure in metaData.measures)) {
            report.issues.push(`Unknown graph measure "${measure}".`);
            report.available.measures = Object.keys(metaData.measures || {});
        } else {
            update.measure = measure;
        }
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
    if (args.stacked !== undefined) {
        update.stacked = Boolean(args.stacked);
    }
    if (args.cumulated !== undefined) {
        update.cumulated = Boolean(args.cumulated);
    }
    if (Object.keys(update).length) {
        model.updateMetaData(update);
        report.applied.push(
            ...Object.entries(update).map(([key, value]) => `graph_${key}:${value}`),
        );
    }
}

function applyPivotModel(model, args, report) {
    const metaData = model.metaData || {};
    for (const measure of args.measures || []) {
        if (metaData.measures && !(measure in metaData.measures)) {
            report.issues.push(`Unknown pivot measure "${measure}".`);
            report.available.measures = Object.keys(metaData.measures || {});
        } else if (!(metaData.activeMeasures || []).includes(measure)) {
            model.toggleMeasure(measure);
            report.applied.push(`measure:${measure}`);
        }
    }
}

function applyViewModel(controller, viewType, args, report) {
    const hasModelArgs =
        (args.measures || []).length ||
        ['mode', 'order', 'stacked', 'cumulated'].some(
            (key) => args[key] !== undefined,
        );
    if (!hasModelArgs) {
        return;
    }
    if (viewType === 'graph') {
        applyGraphModel(controller.model, args, report);
    } else if (viewType === 'pivot') {
        applyPivotModel(controller.model, args, report);
    } else {
        report.issues.push(
            'measures, mode, order, stacked and cumulated only apply to ' +
                'pivot or graph views.',
        );
    }
}

/**
 * Apply an `adjust_search` tool call to the view mounted in this tab.
 *
 * Optionally switches the view type first (a switch re-creates the search
 * bar, so it must precede the search-model mutations), then activates
 * filters/group-bys/field searches, removes facets, adds a custom domain
 * and updates graph/pivot display options.
 *
 * @param {object} args the tool arguments
 * @param {object} env the webclient service environment
 * @returns {Promise<object>} the applied-changes report for the AI session
 */
export async function applyAdjustSearch(args, env) {
    const report = { applied: [], issues: [], available: {} };
    if (args.view_type) {
        try {
            await env.services.action.switchView(args.view_type);
            report.applied.push(`view:${args.view_type}`);
        } catch {
            report.issues.push(`Could not switch to view type "${args.view_type}".`);
        }
    }
    const controller = await waitForTarget();
    if (!controller) {
        return {
            note:
                'No adjustable view is open in this tab: the user must have ' +
                'a list, kanban, pivot or graph view open under the chat ' +
                'window. Form views cannot be adjusted - pass view_type or ' +
                'use open_view instead.',
        };
    }
    const searchModel = controller.env.searchModel;
    const viewType = controller.env.config?.viewType;
    if (args.view_type && viewType !== args.view_type) {
        // switchView can silently no-op (unsaved changes, blocking dialog)
        const claimed = report.applied.indexOf(`view:${args.view_type}`);
        if (claimed >= 0) {
            report.applied.splice(claimed, 1);
        }
        report.issues.push(
            `View did not switch to "${args.view_type}" ` + `(still "${viewType}").`,
        );
    }
    removeFacets(searchModel, args.remove_facets || [], report);
    applyFilters(searchModel, args.filters || [], report);
    applyGroupBys(searchModel, args.group_bys || [], report);
    applySearches(searchModel, args.searches || [], report);
    if (args.custom_domain) {
        await applyCustomDomain(searchModel, args.custom_domain, report);
    }
    applyViewModel(controller, viewType, args, report);
    const result = {
        model: searchModel.resModel,
        view_type: viewType,
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
