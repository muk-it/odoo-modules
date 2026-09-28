# MuK Mail Utils

Technical module to provide some utility features and libraries that can be used
in other applications. It adds a `message_list` list view with a preview pane for
the selected message, and a _Canned Response_ command in the HTML editor.

## Configuration

No configuration required.

## Usage

-   **Message preview**: other modules open message lists with
    `js_class="message_list"`. Clicking a row, or moving to it with the keyboard,
    shows its author, recipients, attachments and body on the right. The pane
    appears on extra-large screens.
-   **Canned responses**: type `/` in any HTML field, including the full email
    composer, pick _Canned Response_, search, and press Enter to insert it.
