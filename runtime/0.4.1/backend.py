#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Nerd Font metadata picker; no font outlines, clipboard history or paste."""
from pathlib import Path
import argparse
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preferences

SLUG = 'glyph-picker'
PREFERENCE_SCHEMA = {
    'density': {'type':'enum', 'default':'comfortable', 'label':'Density', 'choices':['comfortable','compact']},
    'layout': {'type':'enum', 'default':'grid', 'label':'Layout', 'choices':['grid','list']},
    'sortOrder': {'type':'enum', 'default':'default', 'label':'Sort order', 'choices':['default','name','favorites-first']},
    'view': {'type':'enum', 'default':'all', 'label':'Show', 'choices':['all','favorites','recent']},
    'collection': {'type':'string', 'default':'', 'label':'Personal collection (empty = all)', 'maxLength':256},
    'category': {'type':'enum', 'default':'all', 'label':'Named collection', 'choices':['all','developer','arrows','media','weather','status']},
}


def preference_metadata(rows=None):
    prefs = preferences.read(SLUG, PREFERENCE_SCHEMA)
    if rows is not None:
        view, collection = prefs['options']['view'], prefs['options']['collection']
        if view != 'all':
            members = prefs[view if view == 'favorites' else 'recent']
            rows[:] = [row for row in rows if row['id'] in members]
            if view == 'recent':
                rows.sort(key=lambda row: members.index(row['id']))
        if collection:
            rows[:] = [row for row in rows if row['id'] in prefs['collections'].get(collection, [])]
            for row in rows:
                row['collection'] = collection
    for row in rows or []:
        if row['id'] in prefs['favorites']:
            row['favorite'] = True
    return {'preferences': prefs, 'settingsSchema': PREFERENCE_SCHEMA}


DATA = Path(__file__).resolve().parent / 'data/glyphs.tsv'


def bounded_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Catalogue input must be a regular local file.')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Catalogue input exceeds its supported byte limit.')
    return raw


def glyph_rows():
    raw = bounded_read(DATA, 1048576).decode('utf-8')
    lines = raw.splitlines()
    if len(lines) > 16384:
        raise ValueError('Glyph database exceeds the supported record limit.')
    rows, seen = [], set()
    for line in lines:
        fields = line.split('\t')
        if len(fields) != 2:
            continue
        glyph, name = fields
        if len(glyph) != 1 or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,95}', name) or name in seen:
            continue
        n = ord(glyph)
        if not (0xe000 <= n <= 0xf8ff or 0xf0000 <= n <= 0xffffd or 0x100000 <= n <= 0x10fffd):
            continue
        seen.add(name)
        rows.append({'id': name, 'label': name.replace('-', ' ').replace('_', ' '), 'detail': f'U+{n:04X}', 'glyph': glyph})
    if not rows:
        raise ValueError('No valid private-use glyphs found in the bundled database.')
    return rows


def catalog():
    rows = glyph_rows()
    metadata = preference_metadata(rows)
    category = metadata['preferences']['options']['category']
    patterns = {
        'developer': r'^(dev|cod|seti)-',
        'arrows': r'(?:^|[-_])(arrow|arrows|chevron|caret)(?:[-_]|$)',
        'media': r'(?:^|[-_])(play|pause|stop|skip|volume|music|headphone|headphones|microphone|record|rewind|fast_forward)(?:[-_]|$)',
        'weather': r'^weather-',
        'status': r'(?:^|[-_])(check|alert|error|warning|info|information|close|loading|sync|success)(?:[-_]|$)',
    }
    if category != 'all':
        rows = [row for row in rows if re.search(patterns[category], row['id'])]
        for row in rows:
            row.setdefault('collection', category)
    return {**metadata, 'rows': rows, 'message': f'{len(rows)} Nerd Font glyphs match saved filters; font required for rendering.', 'actions': ['copy', 'copy-codepoint', 'copy-unicode', 'favorite'], 'actionLabel': 'Copy'}


def run_helper(argv):
    executable = shutil.which(argv[0])
    if not executable:
        raise ValueError(f'{argv[0]} is unavailable; install or configure it separately.')
    # A separate deadline survives cancellation/destruction of the QML-owned backend.
    with subprocess.Popen(['/usr/bin/timeout', '--signal=KILL', '3', executable, *argv[1:]], stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          start_new_session=True) as proc:
        try:
            code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise ValueError('Helper timed out; request completion is unconfirmed.') from None
    if code in (124, -signal.SIGKILL):
        raise ValueError('Helper timed out; request completion is unconfirmed.')
    if code != 0:
        raise ValueError(f'Helper rejected the request (exit {code}); check the client separately.')


def payload_object(raw):
    if len(raw.encode('utf-8')) > 16384:
        raise ValueError('Payload exceeds 16384 UTF-8 bytes.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate payload key.')
            result[key] = value
        return result
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Nonfinite payload number.')
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_float=number,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite payload number.')))
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('Payload must be a bounded JSON object.') from None
    if not isinstance(result, dict):
        raise ValueError('Payload must be a JSON object.')
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Invalid arguments; use catalog or action --id ID --verb copy --apply.')


def main():
    try:
        parser = Parser(allow_abbrev=False, add_help=False)
        parser.add_argument('command', choices=['catalog', 'action', 'preferences'])
        parser.add_argument('--id')
        parser.add_argument('--verb')
        parser.add_argument('--payload')
        parser.add_argument('--apply', action='store_true')
        args = parser.parse_args()
        if args.command == 'preferences':
            if args.id is not None or args.verb is not None:
                raise ValueError('Preferences do not accept selection arguments.')
            if args.payload is None:
                if args.apply:
                    raise ValueError('Preference writes require a payload.')
                result = {'ok': True, 'message': 'Saved preferences.', **preference_metadata()}
            else:
                if not args.apply:
                    raise ValueError('Explicit --apply is required; nothing changed.')
                patch = payload_object(args.payload)
                if set(patch) == {'reset'} and patch['reset'] is True:
                    prefs = preferences.reset(SLUG, PREFERENCE_SCHEMA)
                else:
                    prefs = preferences.change(SLUG, PREFERENCE_SCHEMA, patch)
                result = {'ok': True, 'message': 'Preferences saved.', 'preferences': prefs, 'settingsSchema': PREFERENCE_SCHEMA}
        elif args.command == 'catalog':
            if args.id is not None or args.verb is not None or args.apply or args.payload is not None:
                raise ValueError('Catalog does not accept action arguments.')
            result = catalog()
        elif args.verb == 'favorite':
            if not args.apply or args.payload is not None:
                raise ValueError('Favorite requires --apply and no payload.')
            if not any(row['id'] == args.id for row in glyph_rows()):
                raise ValueError('Selection is unknown; refresh the catalogue.')
            result = {'ok': True, 'message': 'Favorite updated.', 'preferences': preferences.toggle(SLUG, PREFERENCE_SCHEMA, args.id)}
        else:
            if args.payload is not None:
                raise ValueError('This action does not accept a payload.')
            if not args.apply:
                raise ValueError('Explicit --apply is required; nothing changed.')
            if args.verb not in ('copy', 'copy-codepoint', 'copy-unicode'):
                raise ValueError('Unsupported action; use copy, copy-codepoint or copy-unicode.')
            row = next((r for r in glyph_rows() if r['id'] == args.id), None)
            if row is None:
                raise ValueError('Selection is unknown or no longer available; refresh the catalogue.')
            value = row['glyph'] if args.verb == 'copy' else row['detail']
            if args.verb == 'copy-unicode':
                value = json.dumps(row['glyph'], ensure_ascii=True)[1:-1]
            run_helper(['wl-copy', '--type', 'text/plain;charset=utf-8', '--', value])
            copied = {'copy':'glyph', 'copy-codepoint':'code point', 'copy-unicode':'escaped Unicode text'}[args.verb]
            result = {'ok': True, 'message': f'Clipboard helper accepted the selected {copied}; no paste was performed.'}
        if args.command == 'action' and args.verb in ('copy', 'copy-codepoint', 'copy-unicode'):
            try:
                result['preferences'] = preferences.remember(SLUG, PREFERENCE_SCHEMA, args.id)
            except (ValueError, OSError, UnicodeError):
                result['message'] += ' Warning: recent selection could not be saved.'
        code = 0
    except (ValueError, OSError, UnicodeError) as error:
        result = {'ok': False, 'message': str(error)[:240] if isinstance(error, ValueError) else 'Local data is unavailable; check its permissions and refresh.'}
        code = 1
    try:
        text = preferences.encode_reply(result)
    except ValueError:
        text = preferences.encode_reply({'ok': False, 'message': 'Catalogue exceeds the 1 MiB output limit.'})
        code = 1
    print(text)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
