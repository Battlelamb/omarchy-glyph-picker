# Glyph Picker backend

## Operations and data

Primary verb: `copy`; rows contain canonical `id`, searchable human-readable name in `label`, Unicode codepoint in `detail`, and the single private-use glyph in the parent-approved optional `glyph` field. The bundle has 10,757 Nerd Fonts v3.4.0 mappings, including supplementary-plane characters. Names/aliases remain distinct stable IDs. `action --id cod-add --verb copy --apply` re-reads the complete corpus, then calls `wl-copy --type text/plain;charset=utf-8 -- <glyph>`. There is no clipboard read, history, recent-items store, paste or font installation.

The mapping is a directly rights-traced MIT metadata derivative of Nerd Fonts `glyphnames.json`; it is **not the HyDE glyph.db file** and not font artwork. See `NOTICE.backend.md`, `runtime/0.2.0/data/LICENSE.nerd-fonts`, and `runtime/0.2.0/data/provenance.json`. A compatible installed Nerd Font is required for rendering; missing font coverage can show tofu while names/codepoints still work.

## Bounds and limitations

Bundled input only, maximum 1 MiB and 16,384 physical records; names match canonical ASCII grammar (96 characters), values must be one private-use scalar. Duplicate IDs, malformed fields and non-private-use characters are excluded. Oversized/no-valid data fails. The complete shipped catalogue fits under 1 MiB compact UTF-8 JSON; actions use complete membership beyond the UI's 256 displayed matches. The copy helper's normal zero exit is its acknowledgement; real compositor clipboard ownership/UTF-8 readback has not been tested. No preview image is needed: the `glyph` field is the renderable symbol and `label` remains searchable text.

## CLI and safety contract

Run with `/usr/bin/python3 runtime/0.2.0/backend.py catalog`, or `action --id <exact-known-id> --verb <primary-verb> --apply`. The catalogue is read-only. Runtime/data paths derive from `__file__`, never cwd. One bounded JSON object is emitted; errors are JSON with nonzero exit and no traceback/provider output. Unknown IDs/verbs, missing `--apply`, unavailable providers, nonzero helper exits and deadlines fail closed. Selection is checked against fresh full bounded membership, not the displayed list. **No restore operation is supported or advertised**: copying and launching do not have a meaningful reversible restore.

Actions use literal argument vectors, no shell/eval, no execution of commands from displayed metadata. Helpers are found on normal PATH (tests replace it with a private shim directory); their stdin/stdout/stderr are discarded. GNU `/usr/bin/timeout --signal=KILL 3` supplies an independent process-group deadline even if the QML-owned backend is killed; a five-second Python wait is backup. An already-successful app launch/clipboard ownership can intentionally outlive its short helper. Cancelling after dispatch cannot revoke an accepted action. A timeout does not prove that the request had no effect.

Success means a completed helper exited zero and accepted the request. It is **not proof of actual app/game startup or live clipboard ownership**. The latter require an explicitly authorized native session test. No clients, fonts, packages or dependencies are installed; no bindings, themes, configs, services or live IPC are changed by this implementation task.

## Tests and receipts

From this project's root, use the shipped offline runner with TMPDIR naming an existing approved private scratch directory:

```sh
TMPDIR="${TMPDIR:?Set TMPDIR to an existing private scratch directory}" env -u PYTHONPATH PATH=/usr/bin /usr/bin/python3 scripts/run-tests.py --backend-only
```

The shipped runner invokes `/usr/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v` inside bwrap, with `--unshare-all --clearenv`, read-only `/usr` and source, fake HOME, private proc/dev/tmp/run, no network, no live HOME, display, Hyprland or session bus. It masks production theme/background/shell setters and streams results without creating receipts. No package installation or GUI is involved. The isolation test verifies loopback-only networking, an unreachable external test address, absent live paths/sockets and cleared session variables.

The private `release-output/run-backend-tests.py` runner and ignored `release-output/` receipts below are historical development evidence, not shipped files or prerequisites for the public test command.

Feature-specific RED/GREEN receipts are immutable under ignored `release-output/`; earlier failed runs are retained, not overwritten. Tests run real parsers and CLI entry points against synthetic local files/SQLite and literal executable shims. They cover selected metadata, helper acknowledgement and observable argv logs, malformed/oversized/nonregular inputs, missing clients, revalidation, unknown selections and deadline failure. The cancellation test checks an actual TERM-ignoring descendant becomes non-running after its backend is terminated. Shims establish the adapter boundary only, not genuine client integration. `release-output/backend-result.json` records counted methods, final receipt and exact source hashes. UI/package/README integration remains parent-owned.

Final backend receipt: `06-ui-glyph-field-GREEN.txt`: **9 test methods passed, zero failures/errors, no warnings**.
