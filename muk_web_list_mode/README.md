# MuK List Mode

Enables you to switch between read and editable list views as long as the user
has the needed access rights and the list view does not explicitly disable edit
mode by being set to readonly.

## Usage

On any list view the user is allowed to edit, a button group next to the pager
switches the mode. With "Open Form View" a click on a row opens the record in
its form. With "Inline Edit Mode" the rows are edited directly in the list;
select several rows to change a field on all of them at once. The chosen mode
is remembered per user, action and model. The switch is hidden in dialogs and
on small screens.

The lists of one2many and many2many fields in a form carry a toggle in the
last column of their header, next to the optional columns. It shows the
current mode and switches to the other one on click: "Open Form View" opens a
line in a dialog, "Inline Edit Mode" edits it in the row, and "Add a line"
follows the mode. The default is the mode set on the field's list; the chosen
mode is remembered per user, model and field.
