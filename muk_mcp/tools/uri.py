from urllib.parse import urlparse


def attachment_uri(attachment_id):
    return f'odoo://attachment/{attachment_id}'


def record_field_uri(model, record_id, field):
    return f'odoo://record/{model}/{record_id}/{field}'


def parse_uri(uri):
    if uri and (parsed := urlparse(uri)).scheme == 'odoo':
        parts = [p for p in parsed.path.split('/') if p]
        if parsed.netloc == 'attachment' and len(parts) == 1:
            try:
                return (
                    'attachment',
                    {'attachment_id': int(parts[0])}
                )
            except ValueError:
                return None
        if parsed.netloc == 'record' and len(parts) == 3:
            try:
                return (
                    'record_field',
                    {
                        'model': parts[0],
                        'record_id': int(parts[1]),
                        'field': parts[2],
                    }
                )
            except ValueError:
                return None
    return None
