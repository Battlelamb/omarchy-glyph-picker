#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Nerd Font metadata picker; no font outlines, clipboard history or paste."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import signal
import stat
import subprocess


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
    return {'rows': rows, 'message': f'{len(rows)} Nerd Font glyphs; font required for rendering.', 'actions': ['copy'], 'actionLabel': 'Copy'}


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


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Invalid arguments; use catalog or action --id ID --verb copy --apply.')


def main():
    try:
        parser = Parser(allow_abbrev=False, add_help=False)
        parser.add_argument('command', choices=['catalog', 'action'])
        parser.add_argument('--id', default='')
        parser.add_argument('--verb', default='')
        parser.add_argument('--apply', action='store_true')
        args = parser.parse_args()
        if args.command == 'catalog':
            if args.id or args.verb or args.apply:
                raise ValueError('Catalog does not accept action arguments.')
            result = catalog()
        else:
            if not args.apply:
                raise ValueError('Explicit --apply is required; nothing changed.')
            if args.verb != 'copy':
                raise ValueError('Unsupported action; only copy is available.')
            row = next((r for r in glyph_rows() if r['id'] == args.id), None)
            if row is None:
                raise ValueError('Selection is unknown or no longer available; refresh the catalogue.')
            run_helper(['wl-copy', '--type', 'text/plain;charset=utf-8', '--', row['glyph']])
            result = {'ok': True, 'message': 'Clipboard helper accepted the selected glyph; no paste was performed.'}
        code = 0
    except (ValueError, OSError, UnicodeError) as error:
        result = {'ok': False, 'message': str(error)[:240] if isinstance(error, ValueError) else 'Local data is unavailable; check its permissions and refresh.'}
        code = 1
    text = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    if len(text.encode('utf-8')) > 1048575:
        text = json.dumps({'ok': False, 'message': 'Catalogue exceeds the 1 MiB output limit.'})
        code = 1
    print(text)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
