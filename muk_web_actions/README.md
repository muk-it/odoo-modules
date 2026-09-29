# MuK Batch Actions

Runs server actions and reports from the Actions and Print menus in batches
instead of in one request. A server action set to Execute in Batch processes the
selected records in slices of a configurable size, and a report set to Execute in
Batch downloads one file per record, both behind a progress bar. Each batch is its
own transaction, so large selections stay below the server timeout and a failing
batch keeps the batches before it saved.

## Configuration

Enable Execute in Batch on a server action (Settings > Technical > Server
Actions) and set its Batch Size, or on a PDF report (Settings > Technical >
Reports). The action or report must be in the Actions or Print menu of its model.
