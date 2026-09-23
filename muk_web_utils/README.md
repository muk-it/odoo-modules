# MuK Web Utils

Technical module to provide some utility features and libraries that can be used
in other applications. It adds field widgets and view options for other modules
to use, a setting to disable quick create on many2one fields, a Reports entry in
the debug menu, and fixes for the domain field and the tour pointer.

## Configuration

In debug mode, Settings > General Settings > Permissions offers the option to
disable quick create for many2one fields.

## Usage

Other modules use the widgets `selection_icons`, `text_icon` and `module_link`,
the field options `prettify` (json) and `no_open` (one2many, many2many), the
`icon` attribute on list columns, the `multi_actions` client action, the
`block_progress` service and the Python helpers in `tools`.
