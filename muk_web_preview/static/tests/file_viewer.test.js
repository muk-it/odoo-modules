import { describe, expect, test } from '@odoo/hoot';
import { Deferred } from '@odoo/hoot-mock';

import { makeMockServer, makeServerError, onRpc } from '@web/../tests/web_test_helpers';
import { FileViewer } from '@web/core/file_viewer/file_viewer';

import '@muk_web_preview/core/file_viewer/file_viewer';

describe.current.tags('muk_web_preview');

/**
 * Build a viewer stub whose active file is the given descriptor.
 * @param {object} file the active file descriptor
 * @returns {object} the viewer stub
 */
function makeViewer(file) {
    const viewer = Object.create(FileViewer.prototype);
    viewer.state = { file, officeSource: null, officeLoading: false };
    return viewer;
}

test('a non-office file is not sent to the token endpoint', async () => {
    onRpc('/muk_web_preview/office/token', () => {
        expect.step('token');
        return {};
    });
    await makeMockServer();
    const viewer = makeViewer({ id: 1, isOffice: false });
    await viewer._loadOfficePreview();
    expect.verifySteps([]);
    expect(viewer.state.officeSource).toBe(null);
    expect(viewer.state.officeLoading).toBe(false);
});

test('an office file resolves the viewer url for its attachment', async () => {
    onRpc('/muk_web_preview/office/token', async (request) => {
        const { params } = await request.json();
        expect.step(`token:${params.attachment_id}`);
        return { viewer_url: 'https://view.example/embed?src=x' };
    });
    await makeMockServer();
    const viewer = makeViewer({ id: 42, isOffice: true });
    await viewer._loadOfficePreview();
    expect.verifySteps(['token:42']);
    expect(viewer.state.officeSource).toBe('https://view.example/embed?src=x');
    expect(viewer.state.officeLoading).toBe(false);
});

test('a failing token request leaves no source behind', async () => {
    onRpc('/muk_web_preview/office/token', () => {
        throw makeServerError({ message: 'Office preview is disabled' });
    });
    await makeMockServer();
    const viewer = makeViewer({ id: 42, isOffice: true });
    await viewer._loadOfficePreview();
    expect(viewer.state.officeSource).toBe(null);
    expect(viewer.state.officeLoading).toBe(false);
});

test('a late response for a file that is no longer active is discarded', async () => {
    const deferred = new Deferred();
    onRpc('/muk_web_preview/office/token', () => deferred);
    await makeMockServer();
    const first = { id: 1, isOffice: true };
    const viewer = makeViewer(first);
    const loading = viewer._loadOfficePreview();
    expect(viewer.state.officeLoading).toBe(true);
    viewer.state.file = { id: 2, isOffice: true };
    deferred.resolve({ viewer_url: 'https://view.example/stale' });
    await loading;
    expect(viewer.state.officeSource).toBe(null);
});
