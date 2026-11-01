"""CLI tests: real adapters, synthetic local files, isolated executable shims."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1] / 'runtime/0.1.0/backend.py'

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.env = {'HOME':str(self.home), 'PATH':str(self.bin), 'LANG':'C.UTF-8',
                    'TMPDIR':str(self.home), 'PYTHONDONTWRITEBYTECODE':'1'}

    def put(self, rel, text):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def shim(self, name, rc=0, body=''):
        p = self.bin / name
        p.write_text('#!/usr/bin/python3\nimport os,sys,json,time\nfrom pathlib import Path\n'
                     'p=Path(os.environ["HOME"])/"calls.jsonl"\n'
                     'with p.open("a") as f: f.write(json.dumps({"argv":sys.argv,"stdin":sys.stdin.read()})+"\\n")\n'
                     +body+'\nsys.exit('+str(rc)+')\n')
        p.chmod(0o755)

    def calls(self):
        p = self.home / 'calls.jsonl'
        return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []

    def cli(self, *args, rc=0):
        r = subprocess.run(['/usr/bin/python3',str(BACKEND),*args],cwd='/',env=self.env,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        self.assertEqual(r.returncode,rc,r.stderr.decode()+r.stdout.decode())
        self.assertTrue(r.stdout.strip(), 'backend must emit JSON')
        self.assertLessEqual(len(r.stdout),1048576)
        self.assertNotIn(b'Traceback',r.stdout+r.stderr)
        return json.loads(r.stdout)

    def test_offline_box_is_private(self):
        self.assertEqual(os.environ['HOME'],'/home/test')
        for key in ('DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','HYPRLAND_INSTANCE_SIGNATURE','PYTHONPATH'):
            self.assertNotIn(key,os.environ)
        self.assertEqual(sorted(p.name for p in Path('/home').iterdir()),['test'])
        self.assertFalse(Path('/srv').exists())
        self.assertFalse(Path('/run/user').exists())
        interfaces = Path('/proc/net/dev').read_text().splitlines()[2:]
        self.assertTrue(all(s.strip().startswith('lo:') for s in interfaces))
        with socket.socket() as sock:
            sock.settimeout(.2)
            self.assertNotEqual(sock.connect_ex(('192.0.2.1',443)),0)

    def test_catalog_contract(self):
        result = self.cli('catalog')
        self.assertIsInstance(result['rows'],list)
        self.assertIsInstance(result['message'],str)
        self.assertIn('actions',result)
        self.assertIn('actionLabel',result)
        seen = set()
        for row in result['rows']:
            self.assertEqual(set(row)-{'id','label','detail','preview','color','glyph'},set())
            for key in ('id','label','detail'):
                self.assertIsInstance(row[key],str)
                self.assertTrue(row[key])
                self.assertLessEqual(len(row[key]),512)
            self.assertNotIn(row['id'],seen)
            seen.add(row['id'])
            if row.get('preview'):
                self.assertTrue(Path(row['preview']).is_absolute())
        self.assertEqual(self.calls(),[])

    def test_complete_nerd_mapping_has_selected_details(self):
        result = self.cli('catalog')
        rows = {r['id']:r for r in result['rows']}
        self.assertGreater(len(rows),10000)
        self.assertEqual(rows['cod-add'].get('glyph'),'\uea60')
        self.assertEqual(rows['cod-add']['label'],'cod add')
        self.assertIn('U+EA60',rows['cod-add']['detail'])
        self.assertEqual(result['actions'],['copy'])
        self.assertTrue(any(ord(r['glyph'])>0xffff for r in rows.values()))
        for r in rows.values():
            self.assertEqual(len(r['glyph']),1)
            n=ord(r['glyph'])
            self.assertTrue(0xe000<=n<=0xf8ff or 0xf0000<=n<=0xffffd or 0x100000<=n<=0x10fffd)

    def test_copy_has_literal_utf8_and_confirmed_helper_exit(self):
        self.shim('wl-copy')
        result=self.cli('action','--id','cod-add','--verb','copy','--apply')
        self.assertIn('ok',result)
        self.assertTrue(result['ok'])
        calls=self.calls()
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['argv'][1:],['--type','text/plain;charset=utf-8','--','\uea60'])
        self.assertEqual(calls[0]['stdin'],'')
        self.assertIn('accepted',result['message'].lower())

    def test_untrusted_database_rows_are_bounded_and_validated(self):
        copy=self.home/'runtime/backend.py'
        copy.parent.mkdir()
        copy.write_bytes(BACKEND.read_bytes())
        data=copy.parent/'data/glyphs.tsv'
        data.parent.mkdir()
        def run(text,rc=0):
            data.write_text(text)
            r=subprocess.run(['/usr/bin/python3',str(copy),'catalog'],env=self.env,capture_output=True,timeout=5)
            self.assertEqual(r.returncode,rc,r.stderr.decode())
            self.assertNotIn(b'Traceback',r.stdout+r.stderr)
            return json.loads(r.stdout)
        raw='\uea60\tvalid\n\uea61\tvalid\nA\tplain\n\uea60\tbad name\n\uea60\tbad\textra\n\uea60\t'+('a'*97)+'\n\U000f0001\tsupplementary\n'
        rows=run(raw)['rows']
        self.assertEqual([r['id'] for r in rows],['valid','supplementary'])
        self.assertFalse(run('界'*349526,1)['ok'])
        self.assertFalse(run('\uea60\tx\n'*20000,1)['ok'])
        data.unlink()
        os.mkfifo(data)
        r=subprocess.run(['/usr/bin/python3',str(copy),'catalog'],env=self.env,capture_output=True,timeout=5)
        self.assertEqual(r.returncode,1)
        self.assertFalse(json.loads(r.stdout)['ok'])

    def test_copy_requires_explicit_apply_known_id_and_exact_verb(self):
        self.shim('wl-copy')
        for args in [('action','--id','cod-add','--verb','copy'),('action','--id','$(touch BAD)','--verb','copy','--apply'),('action','--id','cod-add','--verb','restore','--apply'),('catalog','--apply'),('invalid',),('action','--id','cod-add','--verb','copy','--apply','--unknown')]:
            self.assertFalse(self.cli(*args,rc=1)['ok'])
        self.assertEqual(self.calls(),[])

    def test_copy_missing_failed_and_timed_out_helper_is_failure(self):
        args=('action','--id','cod-add','--verb','copy','--apply')
        self.assertFalse(self.cli(*args,rc=1)['ok'])
        self.shim('wl-copy',rc=4)
        self.assertFalse(self.cli(*args,rc=1)['ok'])
        self.shim('wl-copy',body='time.sleep(30)')
        self.assertIn('timed out',self.cli(*args,rc=1)['message'])

    def test_copy_full_membership_beyond_displayed_256(self):
        row=self.cli('catalog')['rows'][-1]
        self.shim('wl-copy')
        self.assertTrue(self.cli('action','--id',row['id'],'--verb','copy','--apply')['ok'])
        self.assertEqual(self.calls()[0]['argv'][-1],row.get('glyph'))

    def test_independent_deadline_survives_backend_termination(self):
        import time
        pass
        self.shim('wl-copy',body='import signal\nchild=os.fork()\nif child == 0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN)\n time.sleep(30)\n sys.exit(0)\n(Path(os.environ["HOME"])/"child.pid").write_text(str(child))\ntime.sleep(30)')
        proc=subprocess.Popen(['/usr/bin/python3',str(BACKEND),'action','--id','cod-add','--verb','copy','--apply'],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pidfile=self.home/'child.pid'
        deadline=time.monotonic()+2
        while not pidfile.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue(pidfile.exists())
        pid=int(pidfile.read_text())
        proc.terminate();proc.wait(timeout=2)
        deadline=time.monotonic()+5
        def running():
            statfile=Path('/proc')/str(pid)/'stat'
            return statfile.exists() and statfile.read_text().split()[2] not in ('Z','X')
        while running() and time.monotonic()<deadline:
            time.sleep(.05)
        alive=running()
        if alive:
            os.kill(pid,9)
        self.assertFalse(alive,'helper outlived its deadline after backend termination')

if __name__ == '__main__':
    unittest.main()
