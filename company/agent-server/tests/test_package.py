import hashlib
import importlib.util
import json
import pathlib
import struct
import tarfile
import tempfile
import unittest
import zipfile
spec = importlib.util.spec_from_file_location('release_package', pathlib.Path(__file__).resolve().parents[1] / 'package.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

class Contract(unittest.TestCase):
    def test_flat_archives_for_all_platforms(self):
        headers = {'darwin-arm64': b'\xcf\xfa\xed\xfe' + struct.pack('<I',0x100000c) + b'\0'*56,
                   'linux-x64': b'\x7fELF\x02\x01' + b'\0'*12 + struct.pack('<H',62) + b'\0'*44,
                   'win32-x64': b'MZ' + b'\0'*58 + struct.pack('<I',64) + b'PE\0\0\x64\x86'}
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); (root/'LICENSE').write_text('license'); (root/'NOTICE').write_text('notice')
            binary = root/'binary'
            for platform, header in headers.items():
                with self.subTest(platform=platform):
                    binary.write_bytes(header)
                    asset = p.package(binary,platform,'0.2.33','a'*40,root/'out',root)
                    if asset.suffix == '.zip':
                        with zipfile.ZipFile(asset) as z: files={n:z.read(n) for n in z.namelist()}
                    else:
                        with tarfile.open(asset) as z: files={m.name:z.extractfile(m).read() for m in z.getmembers()}
                    self.assertEqual(len(files),4)
                    self.assertTrue(all('/' not in name for name in files))
                    manifest=json.loads(files['runtime-manifest.json']); entry=manifest['platforms'][platform]
                    self.assertEqual(hashlib.sha256(files[entry['file']]).hexdigest(),entry['sha256'])
                    self.assertTrue(asset.with_name(asset.name+'.sha256').read_text().startswith(p.digest(asset)))
    def test_invalid_identity_architecture_or_legal_files_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);binary=root/'binary';binary.write_bytes(b'foreign binary')
            for version in ['../escape','bad version','0.2.33']:
                with self.assertRaises(ValueError):p.package(binary,'linux-x64',version,'a'*40,root/'out',root)
            self.assertFalse((root/'out').exists())
