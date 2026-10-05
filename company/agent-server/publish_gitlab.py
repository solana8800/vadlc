"""Publish native CI artifacts to the company distribution repo, never GitHub Releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

API = 'https://gitlab.vinsmartfuture.tech/api/v4/projects/15759'


def release_files(directory, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?', version):
        raise ValueError('invalid release version')
    files = []
    for platform, suffix in [('darwin-arm64', 'tar.gz'), ('linux-x64', 'tar.gz'), ('win32-x64', 'zip')]:
        name = f'v-adlc-agent-server-v{version}-{platform}.{suffix}'
        asset = directory / name
        checksum = directory / (name + '.sha256')
        if asset.is_symlink() or checksum.is_symlink() or not asset.is_file() or not checksum.is_file():
            raise ValueError('all three regular platform archives and checksums are required')
        h = hashlib.sha256()
        with asset.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
        if checksum.read_text().split() != [h.hexdigest(), name]:
            raise ValueError('archive checksum mismatch')
        files.append(asset)
    sums = directory / 'SHA256SUMS.txt'
    if sums.is_symlink(): raise ValueError('unsafe checksum output')
    sums.write_text(''.join((directory / (p.name + '.sha256')).read_text().strip() + '\n' for p in files))
    return [*files, sums]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never send a publishing credential to object storage/another host.


def publish(directory, version, source_commit, token, request=None):
    if not token or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('GitLab token and exact source commit required')
    files = release_files(directory, version)  # Validate every artifact before any write.
    opener = urllib.request.build_opener(NoRedirect())
    def call(method, path, data=None):
        headers = {'PRIVATE-TOKEN': token}
        if isinstance(data, dict):
            data = json.dumps(data).encode(); headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        with opener.open(req, timeout=300) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    call = request or call
    base = f'/packages/generic/v-adlc-agent-server/{version}'
    for file in files:
        call('PUT', base + '/' + file.name, file.read_bytes())
    call('PUT', base + '/release-metadata.json', dict(version=version, sourceCommit=source_commit, sourceRepository='https://github.com/solana8800/vadlc'))
    return API + base

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('dist'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    try:
        print(publish(args.directory, args.version, args.source_commit, os.environ.get('GITLAB_RELEASE_TOKEN', '')))
    except (ValueError, OSError, urllib.error.URLError):
        parser.exit(1, 'GitLab publication failed; check artifacts, token, network and release tag. Credentials are not logged.\n')
