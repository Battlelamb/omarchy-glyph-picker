# Glyph Picker backend · v0.4.0

## Exact CLI

Run from the checkout root; runtime/data paths themselves derive from `__file__`, not the working directory.

```sh
/usr/bin/python3 runtime/0.4.0/backend.py catalog
/usr/bin/python3 runtime/0.4.0/backend.py preferences
/usr/bin/python3 runtime/0.4.0/backend.py preferences --apply --payload '{"options":{"category":"developer","view":"all"}}'
/usr/bin/python3 runtime/0.4.0/backend.py preferences --apply --payload '{"collections":{"Work":["cod-add","dev-python"]},"options":{"collection":"Work"}}'
/usr/bin/python3 runtime/0.4.0/backend.py preferences --apply --payload '{"reset":true}'
/usr/bin/python3 runtime/0.4.0/backend.py action --id cod-add --verb copy --apply
/usr/bin/python3 runtime/0.4.0/backend.py action --id cod-add --verb copy-codepoint --apply
/usr/bin/python3 runtime/0.4.0/backend.py action --id cod-add --verb copy-unicode --apply
/usr/bin/python3 runtime/0.4.0/backend.py action --id cod-add --verb favorite --apply
```

These are all supported commands/verbs. `copy` remains the primary action; `copy-codepoint`, `copy-unicode` and `favorite` are secondary. No Restore, paste, arbitrary clipboard text, custom database path or output path. Neither `catalog` nor a preference read writes files. Actions accept no payload. Every action and preference write requires `--apply`. Unexpected command options, unknown IDs/verbs and malformed JSON fail with nonzero exit and one plain JSON error object; no traceback or provider output is exposed.

Catalogue output retains `rows`, `actions`, `actionLabel`, `message` and adds `preferences` and `settingsSchema`. Rows retain id/label/detail/glyph, with `favorite:true` for favorites and optional `collection` on filtered collection rows. Preference responses are `{ok,preferences,settingsSchema,message}`; successful action responses include `{ok,message,preferences}` when recent/favorite persistence succeeds.

## Saved settings and collections

`PREFERENCE_SCHEMA` is the runtime source of truth:

| Option | Type/default | Accepted values |
|---|---|---|
| `view` | enum, `all` | `all`, `favorites`, `recent` |
| `collection` | string, empty | Exact personal collection name, maximum 256 characters; empty = all |
| `category` | enum, `all` | `all`, `developer`, `arrows`, `media`, `weather`, `status` |
| `density` | enum, `comfortable` | `comfortable`, `compact` |
| `layout` | enum, `grid` | `grid`, `list` |
| `sortOrder` | enum, `default` | `default`, `name`, `favorites-first` |

The three display enums are saved for the native view to interpret; they do not alter source membership or action dispatch. Old valid stores missing these keys receive the defaults on read without an automatic rewrite. Existing options, favorites, Recent and collections remain intact; Reset includes the new defaults.

Filters intersect. Recent view preserves most-recent-first order. Unknown personal names yield an empty selection, not a fallback. Named collections are deterministic name matches: developer uses dev/cod/seti prefixes, weather uses weather-, and arrows/media/status use bounded underscore/hyphen-delimited name tokens. They are useful groupings, not an exhaustive semantic classification. Personal collection names do not authorize paths or commands.

A preference patch accepts only `options`, `favorites`, `collections`. Options merge; supplied favorites or collections replace that entire section. `{"reset":true}` must be the sole key and an actual boolean. `recent` and `version` cannot be written through patches. Payloads must be JSON objects <=16,384 UTF-8 bytes; duplicate keys, nonfinite numbers, invalid option types/choices, unknown fields and invalid identifiers are rejected.

The sibling `preferences.py` supplies read/change/reset/toggle/remember with private, owned, regular-file, no-symlink reads; locked atomic replace and explicit corruption errors. Storage is absolute `$XDG_CONFIG_HOME/omarchy/lego/glyph-picker/preferences.json`, otherwise `$HOME/.config/omarchy/lego/glyph-picker/preferences.json`. Read does not create directories. Reset does not silently repair corrupt files or touch unrelated files. Bounds: 512 favorites, 32 recents, 64 collections, 512 IDs per collection, control-free nonempty IDs <=256 characters. Saved IDs are inert until fresh catalogue membership validates them.

New preference writes are preflighted under the store lock against an aggregate 128 KiB compact UTF-8 document budget before replacement. Individual list/text maxima do not imply their Cartesian maximum is supported. Legacy valid stores remain bounded to 16 MiB for reads and explicit Reset/recovery; a rejected write leaves the existing file unchanged. Replies use the common UTF-8 encoder below 1 MiB (including the newline, at most 1 MiB); the UI action parser uses the same strict byte ceiling. Oversized optional preference snapshots on successful commands are omitted with a warning, preserving `ok:true`; actual catalogue overflow still fails closed, without truncating saved data. A Recent-save failure likewise warns without reversing confirmed helper/export acceptance.

## Mapping, copy and limits

The bundle preserves all 10,757 Nerd Fonts v3.4.0 mappings, including aliases and supplementary-plane private-use scalars. Mapping names are canonical IDs; labels replace separators with spaces, detail is `U+` plus an uppercase code point. Input is a regular local file <=1 MiB / 16,384 physical records, with canonical ASCII names <=96 characters and one private-use scalar per mapping. Invalid/duplicate rows are excluded; empty/oversized data fails. The bundled corpus, license and provenance are unchanged apart from their versioned runtime location; see [NOTICE.backend.md](NOTICE.backend.md).

All three copy verbs freshly read the complete corpus independently of filters/display limits. `wl-copy --type text/plain;charset=utf-8 -- VALUE` receives the exact scalar, its `U+…` detail, or lowercase escaped Unicode text as a literal argument. `copy-unicode` uses JSON string escaping without surrounding quotes: BMP scalars yield `\uXXXX`; supplementary scalars yield two UTF-16 surrogate-pair escapes (for example U+F0001 becomes `\udb80\udc01`), never a truncated scalar or literal surrogate character. No shell, eval, clipboard read or history capture. Recent IDs are remembered only after a zero helper exit; failure to save recent state returns truthful acceptance with a warning rather than pretending the copy failed or was rolled back. Favorite toggles validate full mapping membership and never invoke wl-copy.

Helpers use normal PATH and discarded stdin/stdout/stderr. `/usr/bin/timeout --signal=KILL 3` supplies an independent process-group deadline; Python's five-second wait is backup. Tests confirm a real stubborn descendant stops after backend termination. Already-accepted clipboard work cannot be revoked by dismissing the overlay. Normal clipboard ownership can intentionally outlive the short helper. Complete replies remain below 1 MiB; optional snapshots never turn a confirmed copy into failure. Font rendering and real clipboard ownership need separate native-session verification.

## Offline verification

```sh
TMPDIR="${TMPDIR:?Set TMPDIR to an existing private scratch directory}" env -u PYTHONPATH PATH=/usr/bin /usr/bin/python3 scripts/run-tests.py --backend-only
```

The shipped runner invokes unittest discovery inside offline bwrap with cleared environment, fake HOME, no live display/session bus/compositor sockets and production setters masked. It does not create receipts itself. Tests exercise real mapping/parser/CLI behavior, actual bounded subprocesses and private wl-copy shims, including UTF-8 argv, full membership, five named collections, saved views, write validation, reset, truthful recent-storage failure and complete-source Python compilation. No host tests or GUI windows are needed.

Earlier `release-output/v030-result.json` receipts describe only v0.3.0. The v0.4.0 backend suite adds real BMP/supplementary escaped-copy argv, fresh-mapping refusal, helper failure/timeout, truthful preference warnings and saved-display-schema migration tests. Backend verification does not establish current native UI, live clipboard ownership, upgrade/rollback, hosted CI or publication qualification.
