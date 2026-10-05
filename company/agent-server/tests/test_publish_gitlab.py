import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import urllib.error

spec = importlib.util.spec_from_file_location('publish_gitlab', Path(__file__).parents[1] / 'publish_gitlab.py')
publisher = importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


class PublishTest(unittest.TestCase):
    def assets(self, root):
        for platform, ext in [('darwin-arm64','tar.gz'),('linux-x64','tar.gz'),('win32-x64','zip')]:
            name=f'v-adlc-agent-server-v0.2.34-{platform}.{ext}'
            (root/name).write_bytes(platform.encode())
            (root/(name+'.sha256')).write_text(hashlib.sha256(platform.encode()).hexdigest()+'  '+name+'\n')

    def test_DIST05_three_assets_and_checksums_target_gitlab(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.assets(root);calls=[]
            publisher.publish(root,'0.2.34','a'*40,'synthetic',lambda *args:calls.append(args))
            self.assertEqual(len(calls),5)
            self.assertTrue(all(c[0]=='PUT' and '/v-adlc-agent-server/0.2.34/' in c[1] for c in calls))
            self.assertEqual(calls[-1][2]['sourceCommit'],'a'*40)
            self.assertFalse(any('/releases' in c[1] for c in calls))

    def test_DIST06_missing_tampered_symlink_or_invalid_identity_never_writes(self):
        for defect in ['missing','tampered','symlink','version','commit','token']:
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.assets(root);calls=[]
                p=root/'v-adlc-agent-server-v0.2.34-linux-x64.tar.gz'
                if defect=='missing':p.unlink()
                if defect=='tampered':p.write_bytes(b'tampered')
                if defect=='symlink':p.unlink();p.symlink_to(root/'v-adlc-agent-server-v0.2.34-darwin-arm64.tar.gz')
                with self.assertRaises(ValueError):
                    publisher.publish(root,'../bad' if defect=='version' else '0.2.34','bad' if defect=='commit' else 'a'*40,'' if defect=='token' else 'synthetic',lambda *args:calls.append(args))
                self.assertEqual(calls,[])

    def test_DIST07_redirect_does_not_forward_publish_credentials(self):
        self.assertIsNone(publisher.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))


