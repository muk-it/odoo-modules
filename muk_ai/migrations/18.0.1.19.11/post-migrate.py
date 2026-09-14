from __future__ import annotations

from odoo.sql_db import Cursor

STRIP_REMOTE_SOURCE_ICONS = """
    UPDATE muk_ai_session_event
       SET payload = jsonb_set(
               payload,
               '{sources}',
               (
                   SELECT jsonb_agg(
                       CASE
                           WHEN source->>'icon' LIKE '/%'
                            AND source->>'icon' NOT LIKE '//%'
                           THEN source
                           ELSE source - 'icon'
                       END
                       ORDER BY idx
                   )
                     FROM jsonb_array_elements(payload->'sources')
                          WITH ORDINALITY AS entries(source, idx)
               )
           )
     WHERE jsonb_typeof(payload->'sources') = 'array'
       AND jsonb_array_length(payload->'sources') > 0
       AND EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(payload->'sources') AS source
                WHERE source->>'icon' IS NOT NULL
                  AND (
                      source->>'icon' NOT LIKE '/%'
                      OR source->>'icon' LIKE '//%'
                  )
           )
"""


def migrate(cr: Cursor, version: str) -> None:
    """Drop the third-party favicon URLs from the source descriptors on record.

    Up to this version a cited page carried the icon URL of the search vendor's
    CDN or of the site itself, and the client rendered it, so opening an old
    chat still made every viewer's browser call out to those hosts. The client
    now refuses a non-local icon, and this clears the stored ones so nothing is
    left pointing at a third party; those sources fall back to their glyph.
    """
    cr.execute(STRIP_REMOTE_SOURCE_ICONS)
