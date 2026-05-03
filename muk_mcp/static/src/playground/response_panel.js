/** @odoo-module */

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { parseToolResult, prettyJson } from "./utils";

export class ResponsePanel extends Component {
    static template = "muk_mcp.ResponsePanel";
    static props = {
        response: { type: [Object, { value: null }], optional: true },
    };
    setup() {
        this.notification = useService("notification");
    }
    async onCopyResult() {
        try {
            await navigator.clipboard.writeText(this.prettyResult || "");
            this.notification.add(_t("Result copied"), { type: "success" });
        } catch {
            this.notification.add(_t("Clipboard unavailable"), {
                type: "danger",
            });
        }
    }
    async onCopyRaw() {
        try {
            await navigator.clipboard.writeText(this.rawBody || "");
            this.notification.add(_t("Raw response copied"), {
                type: "success",
            });
        } catch {
            this.notification.add(_t("Clipboard unavailable"), {
                type: "danger",
            });
        }
    }
    get parsed() {
        if (!this.props.response) {
            return null;
        }
        return parseToolResult(this.props.response.body);
    }
    get blocks() {
        return this.parsed?.blocks || [];
    }
    formatTextBlock(block) {
        return prettyJson(block.text);
    }
    dataUri(mimeType, base64) {
        return `data:${mimeType || "application/octet-stream"};base64,${base64}`;
    }
    downloadName(block) {
        if (block.resource?.name) {
            return block.resource.name;
        }
        const uri = block.resource?.uri || "attachment";
        return uri.replace(/[^A-Za-z0-9._-]+/g, "_");
    }
    get prettyResult() {
        const parsed = this.parsed;
        if (!parsed) {
            return "";
        }
        if (parsed.kind === "ok" || parsed.kind === "tool_error") {
            return prettyJson(parsed.text);
        }
        if (parsed.kind === "error") {
            return `JSON-RPC error ${parsed.code}: ${parsed.message}`;
        }
        return "";
    }
    get rawBody() {
        if (!this.props.response) {
            return "";
        }
        const body = this.props.response.body;
        if (body === null || body === undefined) {
            return this.props.response.raw || "";
        }
        try {
            return JSON.stringify(body, null, 2);
        } catch {
            return String(body);
        }
    }
    get statusClass() {
        const parsed = this.parsed;
        if (!parsed) {
            return "";
        }
        if (parsed.kind === "ok") {
            return "alert-success";
        }
        if (parsed.kind === "tool_error") {
            return "alert-warning";
        }
        if (parsed.kind === "error") {
            return "alert-danger";
        }
        return "alert-secondary";
    }
    get statusLabel() {
        const parsed = this.parsed;
        if (!parsed) {
            return "";
        }
        if (parsed.kind === "ok") {
            return "OK";
        }
        if (parsed.kind === "tool_error") {
            return "Tool Error";
        }
        if (parsed.kind === "error") {
            return "JSON-RPC Error";
        }
        return "Empty";
    }
}
