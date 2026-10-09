import { Component, t, useProps } from '@odoo/owl';

import { ChatTurn } from '@muk_ai/chat/turn/turn';

const inserters = new Map();

/**
 * Say where the answers of a session handed over from a composer go.
 * @param {number} sessionId the session the chat window shows
 * @param {(text: string) => void} insert puts an answer in the composer
 */
export function rememberInsert(sessionId, insert) {
    inserters.set(sessionId, insert);
}

/**
 * Message action putting an answer back into the composer its session was
 * handed over from.
 */
export class InsertButton extends Component {
    static template = 'muk_ai_chatter.InsertButton';
    props = useProps({ session: t.object(), text: t.string() });
    get insert() {
        return inserters.get(this.props.session.id);
    }
}

ChatTurn.components = { ...ChatTurn.components, InsertButton };
