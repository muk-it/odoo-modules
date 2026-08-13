# muk_ai_chatter — publish-readiness, resume notes

State as of 2026-08-12, commits `2ad4971`, `8394ec0`, `e5526bd`,
`3edfbbf`, `c48186c`, `005f834`, `2d88068`, `ed8bf5f`, `b69ab8a`, `e6e242c` on `19.0` (pushed).
Version stays `19.0.1.0.0`: the module has never been released, so
everything here folds into the initial release and the changelog keeps
its single `1.0.0` entry.

## Done

- **Lint**: `ruff check` + `ruff format` clean, `eslint static/` clean,
  `prettier --check` clean (XML has no parser, as in every MuK addon).
  Addon lint template is in sync except `.prettierignore`, which adds
  `static/description/` on purpose — the description page is
  hand-authored in the house style and prettier reflows the inline
  styles it is built around.
- **`fenced()` could be escaped** (`tools/chatter.py`). One pass over
  `</thread_</thread_context>context>` leaves a whole closing tag behind,
  which is exactly what somebody writing into the thread would send. Now
  cut until none is left; the redundant second strip in
  `mark_selection()` went away with it. Covered by
  `test_a_nested_closing_tag_does_not_break_out_of_the_snapshot`.
- **A mention that cannot run took the message down with it**
  (`models/mail_thread.py`). A rate limit reached or a half-configured
  provider raised out of `message_post` and rolled back what the user
  wrote. The spawn now runs in a savepoint and only the run is lost.
  Covered by `test_a_run_that_refuses_to_start_still_leaves_the_message_posted`.
- **`suppress(Exception)` without a savepoint** in `_post_chatter_mirror`
  and `_post_mention_placeholder` was no protection at all: a failed
  statement aborts the transaction and the caller dies on the next one.
  Both now enter a savepoint.
- **Docs corrected.** README claimed a `_search` / `_check_access`
  override granting record readers access to linked sessions. No such
  override exists and the tests assert the opposite: sessions stay with
  the user who ran them, admins see all. README, `doc/index.rst` and the
  description page now say that. The stale `muk_ai.compose.prompt` /
  "Writing Prompts" bullet was replaced by the composer-skill wording,
  and `AI → Agents` corrected to `MuK AI → Agents`.
- **The session box never live-updated** (`ai_session_box.js`). It
  listened on `bus_service.addEventListener('notification')`, which is
  18-era: in 19 `BUS:NOTIFICATION` is internal and dispatched per type
  through `subscribe()`. A running session's dot pulsed until a reload.
  Now subscribed to `muk_ai.session_state` and `muk_ai.event` the way
  every other muk_ai component does; the detail-array unwrapping went
  away with it, and the box zeroes the topbar count as it unmounts. The
  JS test mocked the dead API, so it was green over nothing — it mocks
  `subscribe`/`unsubscribe` now.
- **The editor-hosted panel closed on any click** (`compose_plugin.js`).
  `EditorOverlay` defaults `closeOnPointerdown: true`, so clicking back
  into the message threw the generated draft away — while the popover
  twin in the chatter deliberately sets `closeOnClickAway: false`. Both
  surfaces behave the same now.
- **A generated message lost its layout** (`adapters.js`). `asFragment`
  only fenced off blank-line paragraphs, so a three-bullet answer arrived
  in the editor as one run-on line; single newlines are breaks now. The
  same file read and wrote `composer.text`, which does not exist in 19 —
  the write was dead and the no-textarea fallback silently returned an
  empty draft. It is `composerText`.
- **`static/description/index.html` written** in the MuK house style
  (hero, overview, mentions, writing helper, skills, sessions box, guard
  rails, More Apps, Want more?).
- **Screenshots shot** against `o19-ee-main` with a live LLM:
  `screenshot.png` (the Write with AI panel over the chatter composer,
  groups and chips open), `screenshot_compose.png` (a real Shorten run,
  rendered as a diff with Replace / Try again / Discard),
  `screenshot_mention.png` (a mention answered in a Discuss channel, with
  the suggestion list offering the agent — cropped to the conversation
  pane, since the shared database's sidebar is full of E2E channels), and
  `screenshot_ai_sessions_box.png` retaken with the box expanded. The
  seed script is `.claude-tmp/chatter_shots_data.py`; serve with
  `py -3.13 odoo\odoo-bin server -c local\etc\ee.conf -d o19-ee-main
  --db-filter=^o19-ee-main$ --http-port=8095 --gevent-port=8096`.
- **Filestore repaired**: `o19-ee-r5b` had 1826 of 1852 attachments with
  no file on disk (cloned without its filestore), which is what made the
  tour fail with `isTourReady always falsy` and every image 500. Copied
  `filestore/o19-ee-main/*` into `filestore/o19-ee-r5b/`; 0 missing now.
  Not a module defect.

## Open

1. **An agent writes the model and id back at the reader.** Caught while
   shooting `screenshot_mention.png`: asked to summarise a thread, the
   General Assistant opened with "Summary for the Northwind order (this
   conversation — Sales Floor, `discuss.channel,264`)". `MENTION_RULES`
   in `tools/mention.py` says in as many words never to do that, and
   `linkify_records` then turns it into a link, so the wart is rendered
   rather than buried. The rule is not holding — the id reaches the model
   through the view context, and one sentence in the system prompt does
   not beat it. Needs prompt work and a check across models before the
   store screenshot shows it off. The committed screenshot has it.
2. **One more confirming run.** Last full run on `o19-ee-main` was
   **118 passed / 1 failed / 1 error of 120**. Both are accounted for and
   neither is open code:
   - the failure was my own over-specified assertion in
     `test_a_nested_closing_tag_does_not_break_out_of_the_snapshot` — it
     required the fenced block to be the *last* addendum, which stops
     being true as soon as another muk_ai extension appends one after it.
     Rewritten to count the tags instead, and `TestMention` then ran
     **30/30 green** (`.r5-logs/chatter-mention.log`);
   - the error was `TestHoot` failing to open a websocket to Chrome at
     browser startup — infrastructure, not a JS failure, and it passed on
     the earlier run.
   So the suite has never been seen green end to end in one run. Do that
   once before publishing:
   ```
   py -3.13 odoo\odoo-bin server -c local\etc\ee.conf -d o19-ee-main \
     --db-filter=^o19-ee-main$ --http-port=8095 --gevent-port=8096 \
     -u muk_ai_chatter --test-enable --test-tags /muk_ai_chatter \
     --stop-after-init --max-cron-threads=0 --log-level=test
   ```
   Note `-u muk_ai_chatter` alone also upgrades every other module whose
   manifest version moved, and runs their tests too; `--test-tags
   /muk_ai_chatter` keeps the signal clean. Do **not** use `o19-ee-r5b` —
   another session reset it mid-run (20 modules installed,
   `muk_ai_chatter` uninstalled) and deleted `.r5-logs/`.
3. **i18n not re-exported.** The four `.po` files carry 139 msgids each
   and predate the composer-skill refactor. Export fresh ones and
   translate what is new: `tools/create-translations.py` (needs an
   OpenAI key pasted into `OPEN_AI_KEY`; one is in
   `~/.claude/.credentials-openai.json`).
4. **Fable review round 2.** Round 1 ran two lenses. Python:
   `VERDICT: SHIP`, both findings fixed. JS/OWL: `DO-NOT-SHIP` on the two
   majors above, both fixed. Still open from that round, worth doing
   before publishing:
   - (done, `b69ab8a`) singular word count.

   - `compose_panel.scss` darkens its diff and error pills with
     `shade-color($danger|$success, 25–45%)`. Odoo 19 recompiles the
     sheet for dark mode, where darkening further reads as low contrast;
     core mail ships `*.dark.scss` overrides for comparable pills and
     this module ships none. Needs looking at on a dark background.
   Then run a further round until it comes back clean.
5. **Monorepo pointer** for `addons/muk/muk_ai_chatter` still needs
   bumping once the above lands.
