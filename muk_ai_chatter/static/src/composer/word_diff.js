const TOKEN_RE = /\s+|[^\s]+/g;

/**
 * Split text into words and the whitespace between them.
 *
 * Whitespace is kept as its own token so a rebuilt string is exactly the one
 * that went in, and so a change of spacing alone never reads as a reworded
 * sentence.
 *
 * @param {string} text
 * @returns {string[]} the tokens, in order
 */
function tokenize(text) {
    return (text || '').match(TOKEN_RE) || [];
}

/**
 * Compare two texts word by word.
 *
 * A plain longest-common-subsequence table, which is quadratic: composer
 * drafts are short, and anything longer is not worth reading as a diff
 * anyway, so it falls back to "everything replaced" past the cap.
 *
 * @param {string} before the text as the user wrote it
 * @param {string} after the text the agent returned
 * @param {number} [maxTokens=1200] size past which no diff is computed
 * @returns {{type: 'same'|'added'|'removed', value: string}[]} the parts, in order
 */
export function wordDiff(before, after, maxTokens = 1200) {
    const source = tokenize(before);
    const target = tokenize(after);
    if (source.length * target.length > maxTokens * maxTokens) {
        return [
            { type: 'removed', value: before },
            { type: 'added', value: after },
        ];
    }
    const lengths = Array.from(
        { length: source.length + 1 },
        () => new Uint32Array(target.length + 1),
    );
    for (let i = source.length - 1; i >= 0; i--) {
        for (let j = target.length - 1; j >= 0; j--) {
            lengths[i][j] =
                source[i] === target[j]
                    ? lengths[i + 1][j + 1] + 1
                    : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
        }
    }
    const parts = [];
    const push = (type, value) => {
        const last = parts[parts.length - 1];
        if (last && last.type === type) {
            last.value += value;
        } else {
            parts.push({ type, value });
        }
    };
    let i = 0;
    let j = 0;
    while (i < source.length && j < target.length) {
        if (source[i] === target[j]) {
            push('same', source[i]);
            i++;
            j++;
        } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
            push('removed', source[i]);
            i++;
        } else {
            push('added', target[j]);
            j++;
        }
    }
    while (i < source.length) {
        push('removed', source[i++]);
    }
    while (j < target.length) {
        push('added', target[j++]);
    }
    return parts;
}
