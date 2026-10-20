import { loadBundle } from '@web/core/assets';

/**
 * Draw an element to a PNG image block a client tool returns for the model
 * to look at. html2canvas draws a clone, the page is left as is.
 * @param {HTMLElement} element the element to draw
 * @param {string} name the image name
 * @param {object} [options] further html2canvas options, e.g. `{height}`
 * @returns {Promise<object>} `{data, mimetype, name}`
 */
export async function capture(element, name, options = {}) {
    window.html2canvas || (await loadBundle('muk_ai.assets_html2canvas'));
    const canvas = await window.html2canvas(element, {
        backgroundColor: '#ffffff',
        logging: false,
        scale: 1,
        useCORS: true,
        ...options,
    });
    return {
        data: canvas.toDataURL('image/png').split(',')[1],
        mimetype: 'image/png',
        name,
    };
}
