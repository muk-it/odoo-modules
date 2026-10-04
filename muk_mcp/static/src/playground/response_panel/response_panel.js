import { Component, t, useProps } from '@odoo/owl';
import { CopyButton } from '@web/core/copy_button/copy_button';

import { prettyJson } from '@muk_mcp/playground/utils/utils';

const ALERT_CLASSES = {
    ok: 'alert-success',
    tool_error: 'alert-warning',
    error: 'alert-danger',
    empty: 'alert-secondary',
};

/**
 * Renders a tools/call response: its outcome, each content block, downloadable
 * resources and the raw JSON-RPC body.
 */
export class ResponsePanel extends Component {
    static template = 'muk_mcp.ResponsePanel';
    static components = { CopyButton };
    props = useProps({ response: t.object() });
    prettyJson = prettyJson;
    /**
     * Classify the response body.
     * @returns {string} 'error', 'empty', 'tool_error' or 'ok'
     */
    get kind() {
        const body = this.props.response.body;
        if (body?.error) {
            return 'error';
        }
        if (!body?.result) {
            return 'empty';
        }
        return body.result.isError ? 'tool_error' : 'ok';
    }
    get alertClass() {
        return ALERT_CLASSES[this.kind];
    }
    get blocks() {
        return this.props.response.body?.result?.content || [];
    }
    get text() {
        return this.blocks
            .filter((block) => block.type === 'text')
            .map((block) => prettyJson(block.text))
            .join('\n');
    }
    /**
     * Build a base64 data URI.
     * @param {string} mimeType MIME type, binary when missing
     * @param {string} data base64 payload
     * @returns {string} the data URI
     */
    dataUri(mimeType, data) {
        return `data:${mimeType || 'application/octet-stream'};base64,${data}`;
    }
    /**
     * Name the download of a resource block after the resource, or its URI.
     * @param {object} resource embedded resource of the block
     * @returns {string} the filename
     */
    downloadName(resource) {
        return resource.name || resource.uri.replace(/[^A-Za-z0-9._-]+/g, '_');
    }
}
