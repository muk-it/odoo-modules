DEFAULT_CONTEXT_WINDOW = 128000

MAX_ITERATIONS = 20
MAX_TOOL_CALLS_PER_ROUND = 10
MAX_WALLCLOCK_SECONDS = 600

ADVISORY_LOCK_NAMESPACE = 0x4D554B41
WORKER_HEARTBEAT_INTERVAL = 5
WORKER_STALE_THRESHOLD = 60

COMPACT_AUTO_RATIO = 0.80
COMPACT_WARN_RATIO = 0.65
COMPACT_SUMMARY_SYSTEM = (
    "You are performing a CONTEXT CHECKPOINT COMPACTION. "
    "Do NOT continue the conversation. Do NOT respond to any questions in it. "
    "Output ONLY the structured summary, in the same language as the conversation."
)
COMPACT_SUMMARY_TEMPLATE = (
    "Produce a handoff summary using exactly this Markdown structure. "
    "Keep section order. Preserve exact file paths, function names, error "
    "messages, and user-stated constraints.\n\n"
    "## Goal\n"
    "## Constraints & Preferences\n"
    "## Progress\n"
    "### Done\n"
    "### In Progress\n"
    "### Blocked\n"
    "## Key Decisions\n"
    "## Next Steps\n"
    "## Critical Context\n"
    "## Relevant Files\n"
)
COMPACT_SUMMARY_REINJECTION = (
    "Another language model produced this summary of earlier work. "
    "Use it to continue the task without duplicating completed work."
)


class StreamCancelled(Exception):
    pass


def coerce_ids(values):
    ids = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            ids.append(value)
            continue
        if isinstance(value, str):
            try:
                ids.append(int(value))
            except ValueError:
                continue
    return ids


def sanitize_json_schema(schema):
    if not isinstance(schema, dict):
        return schema
    cleaned = dict(schema)
    if cleaned.get('type') == 'array' and 'items' not in cleaned:
        cleaned['items'] = {}
    if isinstance(cleaned.get('items'), dict):
        cleaned['items'] = sanitize_json_schema(cleaned['items'])
    if isinstance(cleaned.get('properties'), dict):
        cleaned['properties'] = {
            name: sanitize_json_schema(value)
            for name, value in cleaned['properties'].items()
        }
    for key in ('anyOf', 'oneOf', 'allOf'):
        if isinstance(cleaned.get(key), list):
            cleaned[key] = [
                sanitize_json_schema(s) for s in cleaned[key]
            ]
    return cleaned
