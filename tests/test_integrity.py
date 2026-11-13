import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import core
import launch

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.run=self.root/'test-run';(self.run/'input').mkdir(parents=True)
        core.write(self.run/'input/brief.json',{'title':'test'})
        core.write(self.run/'package/article.md','Reviewed article')
    def tearDown(self): self.temp.cleanup()
    def test_paths_reject_escape_and_symlink(self):
        (self.root/'link').symlink_to(self.run,target_is_directory=True)
        for name in ['../outside','/etc/passwd','link/input','.',r'a\b']:
            with self.subTest(name=name),self.assertRaises(ValueError):core.confined(self.root,name)
    def test_inventory_rejects_symlinks(self):
        (self.run/'package/link').symlink_to(self.run/'input')
        with self.assertRaises(ValueError):core.inventory(self.run/'package')
    def test_approval_requires_exact_hash_and_video_acknowledgment(self):
        h=core.seal(self.run)
        with self.assertRaises(ValueError):core.approve(self.run,'0'*64,'test reviewer',True)
        with self.assertRaises(ValueError):core.approve(self.run,h,'test reviewer',False)
        self.assertTrue(core.approve(self.run,h,'test reviewer',True)['approvalValid'])
        self.assertFalse(core.verify(self.run)['deploymentAuthorized'])
    def test_changed_added_deleted_outputs_invalidate(self):
        for mutation in ['changed','added','deleted']:
            with self.subTest(mutation=mutation):
                p=self.run/'package/article.md';core.write(p,'Reviewed article')
                extra=self.run/'package/extra';extra.unlink(missing_ok=True)
                core.seal(self.run)
                if mutation=='changed':p.write_text('Unreviewed')
                elif mutation=='added':extra.write_text('Unreviewed')
                else:p.unlink()
                with self.assertRaises(ValueError):core.verify(self.run)
    def test_input_drift_invalidates_approval(self):
        h=core.seal(self.run);core.approve(self.run,h,'test reviewer',True)
        core.write(self.run/'input/brief.json',{'title':'changed'})
        with self.assertRaises(ValueError):core.verify(self.run)
    def test_resealed_package_loses_old_approval(self):
        h=core.seal(self.run);core.approve(self.run,h,'test reviewer',True)
        core.write(self.run/'package/article.md','Revised article');core.seal(self.run)
        self.assertFalse(core.verify(self.run)['approvalValid'])
    def test_resume_verifies_completed_stage_and_reuses_no_calls(self):
        core.write(self.run/'input-seal.json',core.inventory(self.run/'input'))
        core.write(self.run/'state.json',{'id':'test-run','stages':[]})
        # First stage succeeds; second fails. Resume must not invoke source again.
        calls=[]
        def source(run,out,fd):calls.append('source');core.write(out/'proof.json',{'ok':True});return {'ok':True}
        def blocked(*args):raise ValueError('intentional child failure')
        core.write(self.run/'input/factories.json',{'repositories':{}})
        core.write(self.run/'input-seal.json',core.inventory(self.run/'input'))
        with patch.object(launch,'doctor',return_value={'ok':True}),patch.object(launch,'authenticate_children'),patch.object(launch,'source_stage',source),patch.object(launch,'editorial_stage',blocked):
            self.assertEqual(launch.advance(self.run)['status'],'blocked')
            self.assertEqual(launch.advance(self.run)['status'],'blocked')
            self.assertEqual(calls,['source'])
            core.write(self.run/'stages/source/proof.json',{'ok':False})
            result=launch.advance(self.run)
            self.assertIn('Artifact drift',result['error'])
            self.assertEqual(calls,['source'])
    def test_export_and_recorded_import_preserve_integrity_without_approval(self):
        core.write(self.run/'state.json',{'id':'test-run','mode':'live','stages':[]})
        core.write(self.run/'events.jsonl','')
        core.write(self.run/'handoffs/source.json',{'outputHash':'fixture'})
        h=core.seal(self.run);core.approve(self.run,h,'test reviewer',True)
        target=self.root/'docs/example-run'
        launch.export_campaign(self.run,target)
        self.assertFalse((target/'approval.json').exists())
        self.assertTrue(core.verify(target)['ok'])
        with patch.object(launch,'ROOT',self.root),patch.object(launch,'RUNS',self.root/'recorded'):
            result=launch.import_demo();self.assertEqual(result['providerCalls'],0)
            replay=self.root/'recorded/test-run'
            self.assertEqual(core.read(replay/'state.json')['mode'],'recorded')
            with self.assertRaisesRegex(ValueError,'read-only'):launch.advance(replay)
            core.write(replay/'package/article.md','Changed')
            with self.assertRaises(ValueError):launch.import_demo()

    def test_child_nonzero_is_not_success(self):
        with self.assertRaises(ValueError):launch.command(self.run,'failure',[sys.executable,'-c','raise SystemExit(7)'])
        self.assertEqual(core.read(self.run/'logs/failure-receipt.json')['exitCode'],7)

if __name__=='__main__':unittest.main()
