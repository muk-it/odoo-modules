import { Component, useState } from '@odoo/owl';

import { ToolCard } from '@muk_ai/chat/tools/tool_card';

const CHIP_LIMIT = 4;

/**
 * Return whether a tool block's result represents an error.
 * @param {object} block tool block with an optional ``result``
 * @returns {boolean} true when the result carries an error marker
 */
export function toolBlockHasError(block) {
    const value = block.result;
    if (!value) {
        return false;
    }
    if (typeof value === 'object') {
        return Boolean(value.error || value.ok === false);
    }
    if (typeof value === 'string') {
        try {
            const parsed = JSON.parse(value);
            return Boolean(parsed.error || parsed.ok === false);
        } catch {
            return false;
        }
    }
    return false;
}

/**
 * Fold an assistant turn's flat blocks into renderable items, clustering runs
 * of consecutive visible tool calls into a single collapsible group item.
 * @param {Array} blocks ordered turn blocks (text, tool, ask)
 * @param {Function} isHidden predicate marking a tool block as not rendered
 * @returns {Array} ordered render items; tool clusters of two or more become
 *     a ``{type: 'group', tools}`` item, everything else passes through 1:1
 */
export function buildTurnItems(blocks, isHidden) {
    const items = [];
    let group = null;
    const flush = () => {
        if (!group) {
            return;
        }
        if (group.length === 1) {
            items.push({ ...group[0], type: 'tool' });
        } else {
            items.push({
                type: 'group',
                key: 'g-' + group[0].blockIndex,
                tools: group,
            });
        }
        group = null;
    };
    (blocks || []).forEach((block, blockIndex) => {
        if (block.type === 'tool' && !isHidden(block)) {
            (group ||= []).push({ key: 't-' + blockIndex, block, blockIndex });
            return;
        }
        flush();
        items.push({
            type: block.type,
            key: block.type[0] + '-' + blockIndex,
            block,
            blockIndex,
        });
    });
    flush();
    return items;
}

/** Collapsible cluster of consecutive tool calls within one assistant turn. */
export class ToolGroup extends Component {
    static template = 'muk_ai.ToolGroup';
    static components = { ToolCard };
    static props = {
        tools: { type: Array },
        isToolExpanded: { type: Function },
        onToggleTool: { type: Function },
        compact: { type: Boolean, optional: true },
    };
    static defaultProps = {
        compact: false,
    };
    setup() {
        this.state = useState({ expanded: false });
    }
    toggle() {
        this.state.expanded = !this.state.expanded;
    }
    get count() {
        return this.props.tools.length;
    }
    get okCount() {
        return this.props.tools.filter((t) => !toolBlockHasError(t.block)).length;
    }
    get errCount() {
        return this.props.tools.filter((t) => toolBlockHasError(t.block)).length;
    }
    get chips() {
        const names = this.props.tools.map((t) => t.block.name);
        return {
            shown: names.slice(0, CHIP_LIMIT),
            hasMore: names.length > CHIP_LIMIT,
        };
    }
}
