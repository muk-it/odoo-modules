import { signal } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';

import { describeToolBlock, toolBlockDecorators } from '@muk_ai/core/session/turns';

const names = {};
const loaded = signal(0);
const asked = new Map();
let queue = null;

async function fetchNames() {
    const requested = queue;
    queue = null;
    const result = await rpc('/web/dataset/call_kw/ir.model/ai_tool_labels', {
        model: 'ir.model',
        method: 'ai_tool_labels',
        args: [requested],
        kwargs: {},
    });
    for (const [model, entry] of Object.entries(result)) {
        names[model] = {
            name: entry.name,
            fields: { ...names[model]?.fields, ...entry.fields },
        };
    }
    loaded.set(loaded() + 1);
}

/**
 * Return the display names of a model and some of its fields, asking the
 * server once per name; the technical names stand in meanwhile.
 * @param {string} model the technical model name
 * @param {string[]} [fieldNames] the technical field names
 * @returns {object} `{name, fields}`
 */
export function modelNames(model, fieldNames = []) {
    loaded();
    const seen = asked.get(model);
    const missing = fieldNames.filter((name) => !seen?.has(name));
    if (model && (!seen || missing.length)) {
        asked.set(model, new Set([...(seen || []), ...fieldNames]));
        if (!queue) {
            queue = {};
            Promise.resolve().then(fetchNames);
        }
        queue[model] = [...(queue[model] || []), ...missing];
    }
    return {
        name: names[model]?.name || model || '',
        fields: Object.fromEntries(
            fieldNames.map((name) => [name, names[model]?.fields[name] || name]),
        ),
    };
}

const rows = (result) => (Array.isArray(result) ? result : []);
const fieldList = (model, fieldNames) =>
    Object.values(modelNames(model, fieldNames).fields).join(', ');

function recordNames(result, ids) {
    const found = rows(result)
        .map((row) => row.display_name || row.name)
        .filter(Boolean);
    if (!found.length) {
        return ids?.length ? _t('%s records', ids.length) : '';
    }
    const more = found.length > 2 ? ` +${found.length - 2}` : '';
    return found.slice(0, 2).join(', ') + more;
}

function tool(icon, label, band = () => '') {
    return {
        icon: () => icon,
        label: ({ args }) => label(modelNames(args.model).name),
        band,
    };
}

/**
 * The plain-language line of each standard tool, keyed by tool name, as
 * `describeToolBlock` parts; a tool not listed keeps its technical name.
 */
export const toolLabels = {
    search_read: tool(
        'search',
        (model) => _t('Search %s', model),
        ({ result, pending }) => (pending ? '' : _t('%s found', rows(result).length)),
    ),
    search_count: tool(
        'tag',
        (model) => _t('Count %s', model),
        ({ result, pending }) => (pending ? '' : String(result?.count ?? '')),
    ),
    read_records: tool(
        'visibility',
        (model) => _t('Read %s', model),
        ({ args, result }) => recordNames(result, args.ids),
    ),
    read_group: tool(
        'bar_chart',
        (model) => _t('Summarize %s', model),
        ({ args }) => {
            const groups = []
                .concat(args.groupby || [])
                .map((name) => name.split(':')[0]);
            return groups.length ? _t('by %s', fieldList(args.model, groups)) : '';
        },
    ),
    describe_model: tool(
        'info',
        (model) => _t('Look up %s', model),
        () => _t('fields'),
    ),
    create_records: tool(
        'add',
        (model) => _t('Create %s', model),
        ({ args }) => _t('%s new', [].concat(args.values || []).length),
    ),
    update_records: tool(
        'edit',
        (model) => _t('Update %s', model),
        ({ args }) => fieldList(args.model, Object.keys(args.values || {})),
    ),
    delete_records: tool(
        'delete',
        (model) => _t('Delete %s', model),
        ({ args }) => recordNames(null, args.ids),
    ),
    call_method: tool(
        'play_arrow',
        (model) => _t('Run an action on %s', model),
        ({ args }) => args.method || '',
    ),
    export_records: tool('download', (model) => _t('Export %s', model)),
    print_report: tool('print', (model) => _t('Print %s', model)),
    summarize_record: tool('article', (model) => _t('Summarize a %s', model)),
    get_messages: tool('forum', (model) => _t('Read the messages of a %s', model)),
    post_message: tool('send', (model) => _t('Post a message on a %s', model)),
    get_access_rights: tool('lock', (model) => _t('Check the access to %s', model)),
    open_record: tool('open_in_new', (model) => _t('Open %s', model)),
    open_view: tool('open_in_new', (model) => _t('Open the %s view', model)),
    open_action: tool('open_in_new', () => _t('Open a menu')),
    adjust_search: tool('tune', () => _t('Adjust the view')),
    show_notification: tool('notifications', () => _t('Show a notification')),
    web_search: tool(
        'explore',
        () => _t('Search the web'),
        ({ args }) => (args.query ? `"${args.query}"` : ''),
    ),
    web_fetch: tool(
        'public',
        () => _t('Read a web page'),
        ({ args }) => URL.parse(args.url || '')?.hostname || '',
    ),
    generate_image: tool('image', () => _t('Generate an image')),
    list_agents: tool('group', () => _t('List the agents')),
    switch_agent: tool(
        'swap_horiz',
        () => _t('Hand over'),
        ({ args }) => String(args.agent || ''),
    ),
    tool_load: tool(
        'extension',
        () => _t('Load tools'),
        ({ args }) => [].concat(args.names || []).join(', '),
    ),
    list_models: tool('database', () => _t('List the models')),
    list_modules: tool('apps', () => _t('List the apps')),
    list_languages: tool('translate', () => _t('List the languages')),
    system_info: tool('dns', () => _t('Read the system information')),
    whoami: tool('person', () => _t('Check the current user')),
    read_resource: tool('description', () => _t('Read a resource')),
};

toolBlockDecorators.add('muk_ai.tool_labels', (block) => {
    if (toolLabels[block.name]) {
        describeToolBlock(block, toolLabels[block.name]);
    }
});
