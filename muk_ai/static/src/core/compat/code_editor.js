// @odoo-module

import { Component, onWillDestroy, onWillStart, useEffect, useRef } from '@odoo/owl';

import { loadJS } from '@web/core/assets';

/**
 * Ace-backed code editor exposing the ``CodeEditor`` API of later versions.
 *
 * Odoo 16 ships the ace library and an ``AceField`` widget, but no reusable
 * ``@web/core/code_editor`` component, so this wraps ace directly with the
 * props the field widgets already pass.
 */
export class CodeEditor extends Component {
    static template = 'muk_ai.CompatCodeEditor';
    static props = {
        value: { type: String, optional: true },
        mode: { type: String, optional: true },
        readonly: { type: Boolean, optional: true },
        onChange: { type: Function, optional: true },
        onBlur: { type: Function, optional: true },
        class: { type: String, optional: true },
    };
    static defaultProps = {
        value: '',
        mode: 'js',
        readonly: false,
        class: '',
    };

    setup() {
        this.editorRef = useRef('editor');
        this.editor = null;
        onWillStart(async () => {
            // ``ace/mode/js`` needs three modules that ace.js does not carry:
            // the doc-comment rules from javascript_highlight_rules.js, and
            // matching_brace_outdent plus folding/cstyle, which Odoo happens to
            // ship inside mode-scss.js. Later versions get all of these from the
            // web.ace_lib bundle, which Odoo 16 does not define.
            await loadJS('/web/static/lib/ace/ace.js');
            await Promise.all([
                loadJS('/web/static/lib/ace/javascript_highlight_rules.js'),
                loadJS('/web/static/lib/ace/mode-scss.js'),
            ]);
            await loadJS('/web/static/lib/ace/mode-js.js');
        });
        useEffect(
            () => {
                this._mount();
                return () => this._destroy();
            },
            () => [this.editorRef.el],
        );
        onWillDestroy(() => this._destroy());
    }

    _mount() {
        if (!this.editorRef.el || typeof window.ace === 'undefined') {
            return;
        }
        this.editor = window.ace.edit(this.editorRef.el);
        this.editor.setValue(this.props.value || '', -1);
        this.editor.setOptions({
            maxLines: Infinity,
            showPrintMargin: false,
            highlightActiveLine: false,
            useWorker: false,
        });
        this.editor.session.setMode(`ace/mode/${this.props.mode || 'js'}`);
        this.editor.setReadOnly(!!this.props.readonly);
        this.editor.renderer.setShowGutter(false);
        if (this.props.onChange) {
            this.editor.session.on('change', () =>
                this.props.onChange(this.editor.getValue()),
            );
        }
        if (this.props.onBlur) {
            this.editor.on('blur', () => this.props.onBlur());
        }
    }

    _destroy() {
        if (this.editor) {
            this.editor.destroy();
            this.editor = null;
        }
    }
}
