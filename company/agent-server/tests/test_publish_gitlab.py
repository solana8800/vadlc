import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock
import json

spec = importlib.util.spec_from_file_location('publish_gitlab', Path(__file__).parents[1] / 'publish_gitlab.py')
publisher = importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


class PublishTest(unittest.TestCase):
    def assets(self, root):
        for platform, ext in publisher.PLATFORMS:
            name=f'v-adlc-agent-server-v0.2.34-{platform}.{ext}'
            (root/name).write_bytes(platform.encode())
            (root/(name+'.sha256')).write_text(hashlib.sha256(platform.encode()).hexdigest()+'  '+name+'\n')

    def test_DIST05_all_assets_and_checksums_target_gitlab(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.assets(root);calls=[]
            publisher.publish(root,'0.2.34','a'*40,'synthetic',lambda *args:calls.append(args))
            self.assertEqual(len(calls),6)
            self.assertTrue(all(c[0]=='PUT' and '/v-adlc-agent-server/0.2.34/' in c[1] for c in calls))
            self.assertTrue(any(c[1].endswith('-linux-arm64.tar.gz') for c in calls))
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




    def test_DIST11_http_publisher_sends_only_company_urls_and_expected_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.assets(root);requests=[]
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self):return b'{}'
            class Opener:
                def open(self, request, timeout):requests.append(request);return Response()
            with mock.patch.object(publisher.urllib.request,'build_opener',return_value=Opener()):
                publisher.publish(root,'0.2.34','a'*40,'synthetic')
            self.assertEqual(len(requests),6)
            self.assertTrue(all(r.full_url.startswith(publisher.API+'/packages/generic/v-adlc-agent-server/0.2.34/') for r in requests))
            self.assertTrue(all(r.get_header('Private-token')=='synthetic' and r.method=='PUT' for r in requests))
            self.assertEqual(json.loads(requests[-1].data)['sourceCommit'],'a'*40)

    def published_sums(self):
        return ''.join(hashlib.sha256(p.encode()).hexdigest()+'  '+f'v-adlc-agent-server-v0.2.34-{p}.{e}\n'
                       for p, e in publisher.PLATFORMS if p != 'linux-arm64').encode()

    def test_DIST12_add_platform_appends_one_asset_and_the_checksum_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.assets(root);calls=[]
            publisher.add_platform(root,'0.2.34','linux-arm64','synthetic',lambda *args:calls.append(args),lambda path:self.published_sums())
            self.assertEqual([c[1].rsplit('/',1)[1] for c in calls],['v-adlc-agent-server-v0.2.34-linux-arm64.tar.gz','SHA256SUMS.txt'])
            sums=calls[1][2].decode().splitlines()
            self.assertEqual(len(sums),4)
            self.assertEqual(sums[:3],self.published_sums().decode().splitlines(),'published lines kept as they are')
            self.assertTrue(sums[3].endswith('-linux-arm64.tar.gz'))
            self.assertFalse(any('release-metadata' in c[1] for c in calls))

    def test_DIST13_add_platform_never_replaces_published_bytes_or_writes_on_bad_input(self):
        cases={'already':lambda root:None,'tampered':lambda root:(root/'v-adlc-agent-server-v0.2.34-linux-arm64.tar.gz').write_bytes(b'x'),
               'garbage':lambda root:None,'token':lambda root:None}
        for defect,prepare in cases.items():
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.assets(root);prepare(root);calls=[]
                published=self.published_sums()
                if defect=='already':published+=(hashlib.sha256(b'linux-arm64').hexdigest()+'  v-adlc-agent-server-v0.2.34-linux-arm64.tar.gz\n').encode()
                if defect=='garbage':published=b'<html>not a list</html>'
                with self.assertRaises(ValueError):
                    publisher.add_platform(root,'0.2.34','linux-arm64','' if defect=='token' else 'synthetic',lambda *args:calls.append(args),lambda path:published)
                self.assertEqual(calls,[])

