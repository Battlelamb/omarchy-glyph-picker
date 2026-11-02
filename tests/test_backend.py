"""CLI tests: real adapters, synthetic local files, isolated executable shims."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / Path(json.loads((ROOT / 'manifest.json').read_text())['entryPoints']['overlay']).parent / 'backend.py'

class BackendTests(unittest.TestCase):
    def test_legacy_large_preferences_preserve_confirmed_action_and_usable_reads(self):
        # Seed an old valid store directly: new writes have a smaller aggregate budget.
        selected = self.cli('catalog')['rows'][0]['id']; verb = 'copy'; self.shim('wl-copy')
        prefs = self.cli('preferences')['preferences']
        prefs['collections'] = {'g'+str(g): [str(n).zfill(4)+'x'*252 for n in range(512)] for g in range(9)}
        base = Path(self.env.get('XDG_CONFIG_HOME', str(self.home/'.config')))
        store = base/'omarchy/lego/glyph-picker/preferences.json'
        store.parent.mkdir(parents=True, exist_ok=True)
        store.parent.parent.chmod(0o700); store.parent.chmod(0o700)
        raw = json.dumps(prefs, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertGreater(len(raw), 1048576)
        store.write_bytes(raw); store.chmod(0o600)
        result = subprocess.run(['/usr/bin/python3', str(BACKEND), 'action', '--id', selected, '--verb', verb, '--apply'], env=self.env, capture_output=True, timeout=12)
        value = json.loads(result.stdout)
        self.assertTrue(self.calls())
        self.assertEqual(result.returncode, 0, value)
        self.assertTrue(value['ok'], value)
        self.assertIn('warning', value['message'].lower())
        self.assertLessEqual(len(result.stdout), 1048576)
        self.assertNotIn('preferences', value)
        for command in ('preferences',):
            result = subprocess.run(['/usr/bin/python3', str(BACKEND), command], env=self.env, capture_output=True, timeout=12)
            value = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, value)
            self.assertNotIn('preferences', value)
            self.assertIn('warning', value['message'].lower())
            self.assertLessEqual(len(result.stdout), 1048576)
            if command == 'catalog': self.assertIn(selected, [row['id'] for row in value['rows']])
        reset = subprocess.run(['/usr/bin/python3', str(BACKEND), 'preferences', '--apply', '--payload', '{"reset":true}'], env=self.env, capture_output=True, timeout=8)
        self.assertEqual(reset.returncode, 0, reset.stdout)
        self.assertEqual(json.loads(reset.stdout)['preferences']['collections'], {})


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
        self.assertEqual(result['actions'][:1],['copy'])
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
        (copy.parent/'preferences.py').write_bytes((BACKEND.parent/'preferences.py').read_bytes())
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

    def test_copy_codepoint_uses_selected_mapping_not_input_text(self):
        self.shim('wl-copy')
        result=self.cli('action','--id','cod-add','--verb','copy-codepoint','--apply')
        self.assertTrue(result['ok'])
        self.assertEqual(self.calls()[0]['argv'][-1],'U+EA60')
        self.assertIn('code point',result['message'])
        self.assertIn('copy-codepoint',self.cli('catalog')['actions'])

    def test_preferences_read_is_nonmutating_and_catalog_exposes_schema(self):
        result=self.cli('preferences')
        self.assertTrue(result['ok'])
        self.assertEqual(result['preferences']['version'],1)
        self.assertEqual(result['preferences']['favorites'],[])
        self.assertIn('view',result['settingsSchema'])
        cat=self.cli('catalog')
        self.assertEqual(cat['preferences'],result['preferences'])
        self.assertEqual(cat['settingsSchema'],result['settingsSchema'])
        self.assertFalse((self.home/'.config').exists())

    def test_preferences_patch_is_explicit_bounded_exact_json_and_persistent(self):
        payload=json.dumps({'options':{'view':'favorites'},'collections':{'Work':['inert-id']}})
        for args in [('preferences','--payload',payload),('catalog','--payload',payload),('preferences','--id','')]:
            self.assertFalse(self.cli(*args,rc=1)['ok'])
        result=self.cli('preferences','--payload',payload,'--apply')
        self.assertEqual(result['preferences']['options']['view'],'favorites')
        self.assertEqual(result['preferences']['collections'],{'Work':['inert-id']})
        before=self.cli('preferences')['preferences']
        for raw in ['[]','null','{"options":{"view":"all","view":"recent"}}','{"options":{"view":NaN}}','{"recent":[]}','{"options":{"command":"sh"}}','{"options":{"view":"bad"}}',json.dumps({'options':{'x':'界'*6000}})]:
            self.assertFalse(self.cli('preferences','--payload',raw,'--apply',rc=1)['ok'])
            self.assertEqual(self.cli('preferences')['preferences'],before)
        self.assertEqual(self.calls(),[])

    def test_preferences_reset_only_exact_true_resets_saved_preferences(self):
        self.cli('preferences','--payload','{"options":{"view":"recent"},"favorites":["inert-id"]}','--apply')
        for raw in ['{"reset":1}','{"reset":false}','{"reset":true,"favorites":[]}']:
            self.assertFalse(self.cli('preferences','--payload',raw,'--apply',rc=1)['ok'])
        result=self.cli('preferences','--payload','{"reset":true}','--apply')
        self.assertEqual(result['preferences']['options']['view'],'all')
        self.assertEqual(result['preferences']['favorites'],[])
        self.assertEqual(self.cli('preferences')['preferences'],result['preferences'])

    def test_favorite_toggle_validates_membership_without_helper(self):
        self.shim('wl-copy')
        self.assertFalse(self.cli('action','--id','cod-add','--verb','favorite',rc=1)['ok'])
        self.assertFalse(self.cli('action','--id','unknown','--verb','favorite','--apply',rc=1)['ok'])
        result=self.cli('action','--id','cod-add','--verb','favorite','--apply')
        self.assertEqual(result['preferences']['favorites'],['cod-add'])
        self.assertTrue(next(r for r in self.cli('catalog')['rows'] if r['id']=='cod-add')['favorite'])
        self.assertEqual(self.cli('action','--id','cod-add','--verb','favorite','--apply')['preferences']['favorites'],[])
        self.assertEqual(self.calls(),[])

    def test_recent_records_only_accepted_copy_and_warns_on_storage_failure(self):
        args=('action','--id','cod-add','--verb','copy','--apply')
        self.shim('wl-copy',rc=4)
        self.cli(*args,rc=1)
        self.assertEqual(self.cli('preferences')['preferences']['recent'],[])
        self.shim('wl-copy')
        result=self.cli(*args)
        self.assertIn('preferences',result)
        self.assertEqual(result['preferences']['recent'],['cod-add'])
        pref=self.home/'.config/omarchy/lego/glyph-picker/preferences.json'
        pref.write_text('broken')
        result=self.cli(*args)
        self.assertTrue(result['ok'])
        self.assertIn('warning',result['message'].lower())
        self.assertEqual(pref.read_text(),'broken')

    def test_saved_collections_favorites_and_recent_filter_without_authorizing_ids(self):
        self.cli('preferences','--payload','{"favorites":["cod-add","absent"],"collections":{"Work":["cod-add","absent"]},"options":{"view":"favorites"}}','--apply')
        self.assertEqual([r['id'] for r in self.cli('catalog')['rows']],['cod-add'])
        self.cli('preferences','--payload','{"options":{"view":"all","collection":"Work"}}','--apply')
        self.assertEqual([r['id'] for r in self.cli('catalog')['rows']],['cod-add'])
        self.shim('wl-copy')
        self.cli('action','--id','cod-add','--verb','copy','--apply')
        self.cli('preferences','--payload','{"options":{"view":"recent","collection":""}}','--apply')
        self.assertEqual([r['id'] for r in self.cli('catalog')['rows']],['cod-add'])
        self.assertFalse(self.cli('action','--id','absent','--verb','copy','--apply',rc=1)['ok'])

    def test_five_named_collections_filter_real_mapping_and_copy_ignores_filters(self):
        examples={'developer':'dev-python','arrows':'md-arrow_left','media':'md-play','weather':'weather-day_sunny','status':'md-check_circle'}
        for category, ident in examples.items():
            self.cli('preferences','--payload',json.dumps({'options':{'category':category}}),'--apply')
            rows=self.cli('catalog')['rows']
            self.assertTrue(rows)
            self.assertIn(ident,{r['id'] for r in rows})
            self.assertTrue(all(r['collection']==category for r in rows))
            self.assertLess(len(rows),10000)
        self.shim('wl-copy')
        self.assertTrue(self.cli('action','--id','dev-python','--verb','copy','--apply')['ok'])
        before=self.cli('preferences')['preferences']
        self.assertFalse(self.cli('preferences','--payload','{"options":{"category":"../../bad"}}','--apply',rc=1)['ok'])
        self.assertEqual(self.cli('preferences')['preferences'],before)

    def test_full_catalog_and_maximum_favorites_fit_output_budget(self):
        rows=self.cli('catalog')['rows']
        favorites=[r['id'] for r in rows[:512]]
        self.cli('preferences','--payload',json.dumps({'favorites':favorites}),'--apply')
        result=self.cli('catalog')
        self.assertEqual(len(result['rows']),len(rows))
        self.assertEqual(sum(bool(r.get('favorite')) for r in result['rows']),512)

    def test_all_shipped_python_sources_compile(self):
        sources=sorted(p for p in ROOT.rglob('*.py') if 'release-output' not in p.parts)
        for source in sources:
            compile(source.read_bytes(),str(source),'exec')
        self.assertGreaterEqual(len(sources),4)

    def test_docs_reference_current_cli_and_only_existing_local_links(self):
        import re
        for name in ('README.md','BACKEND.md','NOTICE.backend.md'):
            text=(ROOT/name).read_text()
            self.assertNotIn('/home/leviathan',text)
            self.assertNotIn('/srv/projects',text)
            self.assertNotIn('runtime/0.2.1/',text)
            for target in re.findall(r'\]\(([^)]+)\)',text):
                if not target.startswith(('https://','http://','#')):
                    self.assertTrue((ROOT/target.split('#')[0]).is_file(),target)

if __name__ == '__main__':
    unittest.main()
