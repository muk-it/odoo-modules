// @odoo-module

import { useEffect } from '@odoo/owl';

/**
 * Highlight a drop target and forward the drop event to a callback.
 *
 * Stands in for the mail/web ``useDropzone`` hooks, which Odoo 16 does not
 * expose outside its legacy messaging models. The signature matches the
 * later-version hook: the callback receives the drop event itself.
 *
 * @param {object} targetRef OWL ref of the drop target
 * @param {(ev: DragEvent) => void} onDrop invoked with the drop event
 * @param {string} [extraClass] class applied while a drag hovers the target
 * @param {() => boolean} [isDropzoneEnabled] guard consulted on each drag
 */
export function useDropzone(
    targetRef,
    onDrop,
    extraClass,
    isDropzoneEnabled = () => true,
) {
    useEffect(
        (el) => {
            if (!el) {
                return;
            }
            let depth = 0;
            const hasFiles = (ev) => !!ev.dataTransfer?.types?.includes('Files');
            const clear = () => {
                depth = 0;
                if (extraClass) {
                    el.classList.remove(extraClass);
                }
            };
            const onDragEnter = (ev) => {
                if (!isDropzoneEnabled() || !hasFiles(ev)) {
                    return;
                }
                depth++;
                if (extraClass) {
                    el.classList.add(extraClass);
                }
            };
            const onDragOver = (ev) => {
                if (isDropzoneEnabled() && hasFiles(ev)) {
                    ev.preventDefault();
                }
            };
            const onDragLeave = () => {
                depth = Math.max(0, depth - 1);
                if (!depth && extraClass) {
                    el.classList.remove(extraClass);
                }
            };
            const onDropEvent = (ev) => {
                if (!isDropzoneEnabled() || !hasFiles(ev)) {
                    return;
                }
                ev.preventDefault();
                clear();
                onDrop(ev);
            };

            el.addEventListener('dragenter', onDragEnter);
            el.addEventListener('dragover', onDragOver);
            el.addEventListener('dragleave', onDragLeave);
            el.addEventListener('drop', onDropEvent);
            return () => {
                clear();
                el.removeEventListener('dragenter', onDragEnter);
                el.removeEventListener('dragover', onDragOver);
                el.removeEventListener('dragleave', onDragLeave);
                el.removeEventListener('drop', onDropEvent);
            };
        },
        () => [targetRef.el],
    );
}
