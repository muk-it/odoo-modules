const EXTENSION_MIMETYPES = {
    md: 'text/markdown',
    markdown: 'text/markdown',
    txt: 'text/plain',
    csv: 'text/csv',
};

function guessMimetype(file) {
    if (file.type) {
        return file.type;
    }
    const parts = (file.name || '').split('.');
    if (parts.length <= 1) {
        return '';
    }
    return EXTENSION_MIMETYPES[parts.pop().toLowerCase()] || '';
}

/**
 * Read a File into a base64 payload with filename and guessed mimetype.
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
                mimetype: guessMimetype(file),
                data_b64: payload,
            });
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}
