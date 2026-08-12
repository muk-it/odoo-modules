# muk_ai_chatter — publish-readiness, resume notes

State as of 2026-08-12, commits `2ad4971`, `8394ec0`, `e5526bd` on
`19.0` (pushed).
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
- **`static/description/index.html` written** in the MuK house style
  (hero, overview, mentions, writing helper, skills, sessions box, guard
  rails, More Apps, Want more?).
- **Filestore repaired**: `o19-ee-r5b` had 1826 of 1852 attachments with
  no file on disk (cloned without its filestore), which is what made the
  tour fail with `isTourReady always falsy` and every image 500. Copied
  `filestore/o19-ee-main/*` into `filestore/o19-ee-r5b/`; 0 missing now.
  Not a module defect.

## Open

1. **Screenshots.** `index.html` references three images that do not
   exist yet: `screenshot.png` (hero — chatter composer with the Write
   with AI panel open), `screenshot_mention.png` (Discuss channel: `@`
   suggestion list with an agent, and its answer), `screenshot_compose.png`
   (the diff preview). `screenshot_ai_sessions_box.png` exists but is
   poor — the box is collapsed at the bottom of the frame; retake it
   expanded. Until then the description page is incomplete.
   - Seed script ready at `.claude-tmp/chatter_shots_data.py` (creates
     "Northwind Interiors" with a three-message conversation).
   - Python playwright is available under `py -3.13`. Provider 1
     (openai) in `o19-ee-r5b` carries a real key, so a live run for the
     mention answer and the diff is possible.
   - Serve with: `py -3.13 odoo\odoo-bin server -c local\etc\ee.conf
     -d o19-ee-r5b --db-filter=^o19-ee-r5b$ --http-port=8093
     --gevent-port=8094` (admin/admin).
2. **Test run not reproduced after the fixes.** Last complete run
   (`.r5-logs/chatter-tests4.log`, before these commits) was
   **117 passed / 1 failed of 118**, the single failure being the tour,
   for the filestore reason above. Every run started after the fixes
   (`chatter-tests5/6`, `chatter-compose`) was killed by the machine
   (`EXIT=-1`, no traceback, dying at a different point each time,
   including 71 lines in during module-list update) — environmental, not
   a test failure. **Re-run and confirm green before publishing:**
   ```
   py -3.13 odoo\odoo-bin server -c local\etc\ee.conf -d o19-ee-r5b \
     --db-filter=^o19-ee-r5b$ --http-port=8093 --gevent-port=8094 \
     -u muk_ai_chatter --test-enable --test-tags /muk_ai_chatter \
     --stop-after-init --max-cron-threads=0 --log-level=test
   ```
   Note `-u muk_ai_chatter` alone also upgrades every other module whose
   manifest version moved, and runs their tests too; `--test-tags
   /muk_ai_chatter` keeps the signal clean.
3. **i18n not re-exported.** The four `.po` files carry 139 msgids each
   and predate the composer-skill refactor. Export fresh ones and
   translate what is new: `tools/create-translations.py` (needs an
   OpenAI key pasted into `OPEN_AI_KEY`; one is in
   `~/.claude/.credentials-openai.json`).
4. **Fable review round 2.** Round 1 ran two lenses. Python:
   `VERDICT: SHIP`, both findings fixed. JS/OWL: `DO-NOT-SHIP` on the two
   majors above, both fixed. Still open from that round, worth doing
   before publishing:
   - `adapters.js` `asFragment` only preserves blank-line paragraphs, so
     a single-newline answer ("- one\n- two") collapses to one run-on
     line on the editor path. Split on single `\n` and join with `<br>`.
   - `adapters.js` reads/writes `composer.text`, which does not exist in
     19 (it is `composerText`); the write is dead and the fallback
     silently returns `''`. Use `composerText` or drop the composer
     writes and rely on the textarea + `input` event.
   - Nits: `'%s selected words'` has no singular form; session rows are
     clickable `div`s with no `role="button"`/`tabindex` and show the raw
     UTC datetime as their tooltip; `compose_panel.scss` leans on
     `--o-view-background-color` / `--border-color`, neither of which
     core defines, and ships no dark-mode override for its pills.
   Then run a further round until it comes back clean.
5. **Monorepo pointer** for `addons/muk/muk_ai_chatter` still needs
   bumping once the above lands.
