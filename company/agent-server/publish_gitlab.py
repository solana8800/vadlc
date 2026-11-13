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
PLATFORMS = [('darwin-arm64', 'tar.gz'), ('linux-x64', 'tar.gz'), ('linux-arm64', 'tar.gz'), ('win32-x64', 'zip')]


def checked_asset(directory, version, platform, suffix):
    """One regular archive whose .sha256 sidecar matches it."""
    name = f'v-adlc-agent-server-v{version}-{platform}.{suffix}'
    asset = directory / name
    checksum = directory / (name + '.sha256')
    if asset.is_symlink() or checksum.is_symlink() or not asset.is_file() or not checksum.is_file():
        raise ValueError('regular platform archive and checksum are required')
    h = hashlib.sha256()
    with asset.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    if checksum.read_text().split() != [h.hexdigest(), name]:
        raise ValueError('archive checksum mismatch')
    return asset


def release_files(directory, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?', version):
        raise ValueError('invalid release version')
    files = [checked_asset(directory, version, platform, suffix) for platform, suffix in PLATFORMS]
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


def _download(path, token):
    """GET a package file: GitLab answers with a redirect to object storage, which is fetched without the token."""
    request = urllib.request.Request(API + path, headers={'PRIVATE-TOKEN': token})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        location = error.headers.get('Location') if error.code in (301, 302, 303, 307, 308) else None
        if not location or not location.startswith('https://'):
            raise
    with urllib.request.urlopen(location, timeout=60) as response:  # nosec B310 - https checked above
        return response.read()


def add_platform(directory, version, platform, token, request=None, download=None):
    """Add one platform to an already-published version (same sourceCommit), e.g. linux-arm64 to 1.0.13.

    The existing archives and release-metadata.json are left as they are; SHA256SUMS.txt is published again with
    the new line appended. A platform already listed is refused: published bytes are never replaced."""
    suffixes = dict(PLATFORMS)
    if not token or platform not in suffixes or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?', version):
        raise ValueError('GitLab token, a known platform and a valid version are required')
    asset = checked_asset(directory, version, platform, suffixes[platform])
    base = f'/packages/generic/v-adlc-agent-server/{version}'
    existing = (download or (lambda path: _download(path, token)))(base + '/SHA256SUMS.txt').decode()
    lines = [line for line in existing.splitlines() if line.strip()]
    if not lines or any(len(line.split()) != 2 or not re.fullmatch('[0-9a-f]{64}', line.split()[0]) for line in lines):
        raise ValueError('published SHA256SUMS.txt is not a checksum list')
    if any(line.split()[1] == asset.name for line in lines):
        raise ValueError(f'{asset.name} is already published; never replace published bytes')
    new_line = (directory / (asset.name + '.sha256')).read_text().strip()
    sums = directory / 'SHA256SUMS.txt'
    if sums.is_symlink(): raise ValueError('unsafe checksum output')
    sums.write_text('\n'.join([*lines, new_line]) + '\n')
    opener = urllib.request.build_opener(NoRedirect())
    def call(method, path, data=None):
        req = urllib.request.Request(API + path, data=data, headers={'PRIVATE-TOKEN': token}, method=method)
        with opener.open(req, timeout=300) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    call = request or call
    call('PUT', base + '/' + asset.name, asset.read_bytes())
    call('PUT', base + '/SHA256SUMS.txt', sums.read_bytes())
    return API + base + '/' + asset.name

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('dist'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-commit', help='full commit of a new release (all platforms)')
    parser.add_argument('--add-platform', choices=[p for p, _ in PLATFORMS],
                        help='add one platform to an already-published version instead of a new release')
    args = parser.parse_args()
    token = os.environ.get('GITLAB_RELEASE_TOKEN', '')
    try:
        if args.add_platform:
            print(add_platform(args.directory, args.version, args.add_platform, token))
        else:
            print(publish(args.directory, args.version, args.source_commit or '', token))
    except (ValueError, OSError, urllib.error.URLError):
        parser.exit(1, 'GitLab publication failed; check artifacts, token, network and release tag. Credentials are not logged.\n')
