# MuK Tree List

The module adds the treelist view type: a list view whose rows nest under their
parent record and open and close like the folders of a file explorer. It works
on any model with a many2one to itself, such as product categories, contacts,
departments or locations, and keeps what a list view offers: inline editing,
optional columns, sums, widgets and decorations.

## Configuration

A treelist is declared like a list view, with the `treelist` tag and the view
mode `treelist`:

```xml
<treelist parent_field="parent_id" editable="bottom" draggable="1">
    <field name="name"/>
    <field name="budget" sum="Total" rollup="1"/>
</treelist>
```

- `parent_field` -- the many2one to the same model, `parent_id` by default.
- `expand="1"` -- open every row when the view is first loaded.
- `draggable="1"` -- move a record under another one by drag and drop.
- `widget="handle"` on a sequence field -- drag rows to order them among
  their siblings.
- `rollup="1"` on a numeric field without a widget -- show subtree totals on
  parent rows and in the footer.

## Usage

- Click the chevron of a row, or press Right and Left, to open and close it.
  A row with many children pages them with its own pager.
- Search shows each match in place, under its greyed-out parents up to the
  root, opened automatically.
- Click **+** on a row to add a child record directly under it.
- Drag a row by its handle onto another row to move it there.
- Grouped, each group shows its records as a tree.
- Excel exports keep the tree: indented, with collapsible outline rows and,
  during a search, the parents as header rows.
- **Expand All** and **Collapse All** in the cog menu open or close every row.
