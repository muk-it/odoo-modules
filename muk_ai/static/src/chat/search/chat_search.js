import { Component, onMounted, useRef } from '@odoo/owl';

/** In-conversation search bar with match navigation controls. */
export class ChatSearch extends Component {
    static template = 'muk_ai.ChatSearch';
    static props = {
        query: { type: String },
        total: { type: Number },
        currentIdx: { type: Number },
        onChange: { type: Function },
        onPrev: { type: Function },
        onNext: { type: Function },
        onClose: { type: Function },
    };
    setup() {
        this.inputRef = useRef('input');
        onMounted(() => {
            if (this.inputRef.el) {
                this.inputRef.el.focus();
                this.inputRef.el.select();
            }
        });
    }
    onInput(ev) {
        this.props.onChange(ev.target.value);
    }
    onKeyDown(ev) {
        if (ev.key === 'Escape') {
            ev.preventDefault();
            this.props.onClose();
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            if (ev.shiftKey) {
                this.props.onPrev();
            } else {
                this.props.onNext();
            }
        }
    }
    get counterLabel() {
        if (!this.props.query) return '';
        if (!this.props.total) return '0 of 0';
        return `${this.props.currentIdx + 1} of ${this.props.total}`;
    }
}
