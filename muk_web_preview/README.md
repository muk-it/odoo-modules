# MuK Preview

Extends the built-in file viewer with additional preview support for file types
such as email messages, CSV files, and Microsoft Office documents. The module
also adds common text-based mimetypes to the viewer so they can be previewed
directly without downloading.

## Configuration

To enable Microsoft Office file preview, go to Settings and enable the
**MS Office Preview** option. This uses the Microsoft Office Online viewer
to render docx, xlsx, and pptx files directly in the browser. The Odoo
instance must be publicly accessible from the internet for this feature
to work. Files are served via short-lived one-time token URLs for security.

## Usage

Once installed, the file viewer automatically supports additional file types:

- **Email Messages (.eml):** Email files are rendered as HTML with inline images
  resolved from CID attachments.

- **CSV/TSV Files:** Comma and tab separated files are displayed as formatted
  HTML tables with headers, striped rows, and truncation for large files.

- **Microsoft Office (.docx, .xlsx, .pptx):** Office documents are previewed
  using the Microsoft Office Online viewer in read-only mode. A "Preview only"
  badge is shown to make it clear the file cannot be edited. This feature must
  be enabled in Settings and requires the Odoo instance to be publicly
  accessible.

- **Additional Text Types:** Files with mimetypes such as `text/csv`,
  `text/markdown`, `text/xml`, `text/x-python`, `text/x-rst`,
  `text/x-yaml`, `application/xml`, `application/x-yaml`,
  `application/x-sh`, and `application/sql` can now be previewed
  directly in the file viewer.
