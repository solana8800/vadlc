"""Flat, checksummed private runtime assets; no upstream source changes needed."""
import argparse
import hashlib
import json
import pathlib
import re
import struct
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGETS = {'darwin-arm64': 'aarch64-apple-darwin', 'linux-x64': 'x86_64-unknown-linux-gnu', 'win32-x64': 'x86_64-pc-windows-msvc'}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def package(binary, platform, version, source_commit, out, source_root=ROOT):
    if platform not in TARGETS or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?', version) or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('invalid release identity')
    if binary.is_symlink() or not binary.is_file() or binary.stat().st_size > 200 * 1024 * 1024:
        raise ValueError('release binary must be regular and at most 200 MiB')
    with binary.open('rb') as stream:
        header = stream.read(4096)
        valid = False
        if platform == 'darwin-arm64': valid = header[:4] == b'\xcf\xfa\xed\xfe' and len(header) >= 8 and struct.unpack_from('<I', header, 4)[0] == 0x100000c
        if platform == 'linux-x64': valid = header[:6] == b'\x7fELF\x02\x01' and len(header) >= 20 and struct.unpack_from('<H', header, 18)[0] == 62
        if platform == 'win32-x64' and len(header) >= 64 and header[:2] == b'MZ':
            stream.seek(struct.unpack_from('<I', header, 60)[0]); valid = stream.read(6) == b'PE\0\0\x64\x86'
        if not valid: raise ValueError('binary architecture mismatch')
    for name in ('LICENSE', 'NOTICE'):
        p = source_root / name
        if p.is_symlink() or not p.is_file() or not p.stat().st_size: raise ValueError('missing nonempty legal notice')
    name = 'v-adlc-agent-server' + ('.exe' if platform == 'win32-x64' else '')
    manifest = {'schemaVersion': 1, 'engine': 'v-adlc-agent-server', 'protocol': 'app-server-v2', 'version': version, 'sourceCommit': source_commit,
                'platforms': {platform: {'file': name, 'sha256': digest(binary)}}}
    support = ['codex-windows-sandbox-setup.exe', 'codex-command-runner.exe'] if platform == 'win32-x64' else []
    for file in support:
        helper = binary.parent / file
        if helper.is_symlink() or not helper.is_file() or helper.stat().st_size > 200 * 1024 * 1024: raise ValueError('missing Windows sandbox helper')
        with helper.open('rb') as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b'MZ': raise ValueError('invalid Windows sandbox helper')
            stream.seek(struct.unpack_from('<I', header, 60)[0])
            if stream.read(6) != b'PE\0\0\x64\x86': raise ValueError('helper architecture mismatch')
    if support: manifest['supportFiles'] = {file: digest(binary.parent / file) for file in support}
    out.mkdir(parents=True, exist_ok=True)
    asset = out / f'v-adlc-agent-server-v{version}-{platform}.{"zip" if platform == "win32-x64" else "tar.gz"}'
    with tempfile.TemporaryDirectory() as directory:
        stage = pathlib.Path(directory)
        import shutil
        shutil.copyfile(binary, stage / name); (stage / name).chmod(0o755)
        for legal in ('LICENSE', 'NOTICE'): shutil.copyfile(source_root / legal, stage / legal)
        (stage / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        for file in support: shutil.copyfile(binary.parent / file, stage / file)
        names = [name, 'runtime-manifest.json', 'LICENSE', 'NOTICE', *support]
        if platform == 'win32-x64':
            with zipfile.ZipFile(asset, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for file in names: archive.write(stage / file, file)
        else:
            with tarfile.open(asset, 'w:gz', compresslevel=9) as archive:
                for file in names: archive.add(stage / file, arcname=file)
    asset.with_name(asset.name + '.sha256').write_text(f'{digest(asset)}  {asset.name}\n')
    return asset

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=pathlib.Path, required=True)
    parser.add_argument('--platform', choices=TARGETS, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    print(package(args.binary, args.platform, args.version, commit, args.out))
