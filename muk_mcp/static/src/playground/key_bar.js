/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class KeyBar extends Component {
    static template = "muk_mcp.KeyBar";
    static props = {
        client: Object,
        keyPrefix: String,
        onKeyChanged: Function,
    };
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            pasting: false,
            pasteValue: "",
            pasteName: "",
            scope: "write",
        });
    }
    onPasteToggle() {
        this.state.pasting = !this.state.pasting;
        this.state.pasteValue = "";
    }
    onPasteChange(ev) {
        this.state.pasteValue = ev.target.value;
    }
    onPasteNameChange(ev) {
        this.state.pasteName = ev.target.value;
    }
    onPasteConfirm() {
        const value = (this.state.pasteValue || "").trim();
        if (!value) {
            this.notification.add(_t("Key is empty"), { type: "warning" });
            return;
        }
        this.props.client.key = value;
        this.state.pasting = false;
        this.state.pasteValue = "";
        this.props.onKeyChanged();
        this.notification.add(_t("Key set for this tab"), { type: "success" });
    }
    async onGenerate() {
        const name =
            (this.state.pasteName || "").trim() ||
            `Playground ${new Date().toISOString().slice(0, 19).replace("T", " ")}`;
        try {
            const result = await this.orm.call(
                "muk_mcp.key",
                "generate_playground_key",
                [],
                { name, scope: this.state.scope }
            );
            this.props.client.key = result.plaintext;
            this.props.onKeyChanged();
            this.state.pasting = false;
            this.state.pasteValue = "";
            this.notification.add(
                _t(
                    "Generated key '%s' (prefix %s). Plaintext is now loaded for this tab only.",
                    result.name,
                    result.key_prefix
                ),
                { type: "success", sticky: true }
            );
        } catch (error) {
            this.notification.add(
                _t("Failed to generate key: %s", error.message || error),
                { type: "danger" }
            );
        }
    }
    onClearKey() {
        this.props.client.key = "";
        this.props.onKeyChanged();
        this.notification.add(_t("Key cleared"), { type: "info" });
    }
}
