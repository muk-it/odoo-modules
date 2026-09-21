import { patch } from '@web/core/utils/patch';
import { append, createElement, setAttributes } from '@web/core/utils/xml';
import { FormCompiler } from '@web/views/form/form_compiler';

import '@mail/chatter/web/form_compiler';

/** Give the chatter container its drag handle and the width behind it. */
patch(FormCompiler.prototype, {
    compile(node, params) {
        const res = super.compile(node, params);
        const chatterContainerHookXml = res.querySelector(
            '.o-mail-Form-chatter:not(.o-isInFormSheetBg)',
        );
        if (!chatterContainerHookXml) {
            return res;
        }
        setAttributes(chatterContainerHookXml, {
            't-att-style':
                '__comp__.chatterWidth() ? `--mk-Chatter-width: ${__comp__.chatterWidth()}px` : ""',
        });
        const chatterContainerResizeHookXml = createElement('span');
        chatterContainerResizeHookXml.classList.add('mk_chatter_resize');
        setAttributes(chatterContainerResizeHookXml, {
            't-on-mousedown.stop.prevent':
                '__comp__.onStartChatterResize.bind(__comp__)',
            't-on-dblclick.stop.prevent':
                '__comp__.onDoubleClickChatterResize.bind(__comp__)',
        });
        append(chatterContainerHookXml, chatterContainerResizeHookXml);
        return res;
    },
});
