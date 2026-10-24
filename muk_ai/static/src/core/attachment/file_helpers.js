// @odoo-module

/**
 * Read a File into a base64 payload with its filename and the browser's mimetype.
 * @param {File} file the file to read
 * @returns {Promise<object>} { filename, mimetype, data_b64 }
 */
export function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result || '';
            const comma = result.indexOf(',');
            const payload = comma >= 0 ? result.slice(comma + 1) : result;
            resolve({
                filename: file.name,
                mimetype: file.type,
                data_b64: payload,
            });
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}
