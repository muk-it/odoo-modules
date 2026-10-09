HTTP_HINT = (
    'Clients that can run HTTP requests (a shell, curl, a script) should use '
    'it: the file then never passes through the conversation.'
)


def delivery_field():
    """Return the JSON schema for how a tool hands over the file it produces."""
    return {
        'type': 'string',
        'enum': ['inline', 'link'],
        'default': 'inline',
        'description': (
            '"inline" returns the file as base64; "link" stores it and returns a '
            'one-time download_url instead. ' + HTTP_HINT
        ),
    }
