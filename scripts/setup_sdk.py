#!/usr/bin/env python3
"""Install a pinned, locally supplied EGO SDK. No downloads or root operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((Path(__file__).parent / 'sdk_manifest.json').read_text())


def architecture():
    if platform.system() != 'Linux':
        raise ValueError('Only Linux is supported by this installer.')
    name = platform.machine().lower()
    name = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(name, name)
    if name not in MANIFEST['platforms']:
        raise ValueError(f'Unsupported architecture: {name}')
    return name


def validate_sdk(root, arch):
    for relative in ('include/libobsensor/ObSensor.hpp', 'lib/OrbbecSDKConfig.cmake',
                     'lib/libOrbbecSDK.so', 'lib/extensions', 'shared/install_udev_rules.sh'):
        if not (root / relative).exists():
            raise ValueError(f'Incomplete SDK: missing {root / relative}')
    with (root / 'lib/libOrbbecSDK.so').open('rb') as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:4] != b'\x7fELF' or header[4:6] != b'\x02\x01':
        raise ValueError('Expected a 64-bit little-endian ELF SDK library.')
    machine = struct.unpack('<H', header[18:20])[0]
    if machine != {'x86_64': 62, 'aarch64': 183}[arch]:
        raise ValueError(f'SDK library does not match host architecture {arch}.')


def checked_members(archive, destination):
    """Reject paths/links outside the new staging directory and special files."""
    root = destination.resolve()
    members = archive.getmembers()
    for member in members:
        path = root / member.name
        if Path(member.name).is_absolute() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Unsafe archive path: {member.name}')
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError(f'Unsupported archive entry: {member.name}')
        if member.issym() or member.islnk():
            target = (path.parent if member.issym() else root) / member.linkname
            if Path(member.linkname).is_absolute() or not target.resolve().is_relative_to(root):
                raise ValueError(f'Unsafe archive link: {member.name}')
    return members


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2)
        stream.write('\n')
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def selected_root(install_dir, arch):
    state = json.loads((install_dir / 'current.json').read_text())
    expected = MANIFEST['platforms'][arch]
    if state['arch'] != arch or state['sha256'] != expected['sha256']:
        raise ValueError('Installed SDK selection differs from the pinned manifest; run setup again.')
    root = Path(state['root'])
    validate_sdk(root, arch)
    return root


def install(archive_path, install_dir, arch):
    expected = MANIFEST['platforms'][arch]
    digest = hashlib.sha256()
    # Hash and extract from the same open file descriptor.
    with archive_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        if digest.hexdigest() != expected['sha256']:
            raise ValueError(f"SDK checksum mismatch for {arch}. Expected {expected['directory']}.tar.gz\n"
                             f"Expected SHA256: {expected['sha256']}\nActual SHA256: {digest.hexdigest()}")
        install_dir.mkdir(parents=True, exist_ok=True)
        target = install_dir / MANIFEST['version'] / arch
        state = {'root': str(target), 'arch': arch, 'version': MANIFEST['version'],
                 'sha256': expected['sha256'], 'archive': expected['directory'] + '.tar.gz'}
        if target.exists():
            marker = target / '.sdk-install.json'
            if not marker.exists() or json.loads(marker.read_text()) != state:
                raise ValueError(f'Refusing to replace existing unmanaged SDK: {target}')
            validate_sdk(target, arch)
        else:
            with tempfile.TemporaryDirectory(prefix='.staging-', dir=install_dir) as staging:
                staging = Path(staging)
                stream.seek(0)
                with tarfile.open(fileobj=stream, mode='r:gz') as archive:
                    members = checked_members(archive, staging)
                    archive.extractall(staging, members=members)
                extracted = staging / expected['directory']
                validate_sdk(extracted, arch)
                atomic_json(extracted / '.sdk-install.json', state)
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted.rename(target)
        atomic_json(install_dir / 'current.json', state)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--archive', type=Path, help='Vendor Linux .tar.gz for this machine')
    action.add_argument('--print-root', action='store_true', help='Print validated installed SDK path')
    parser.add_argument('--install-dir', type=Path, default=PROJECT / '.local/ego-sdk')
    args = parser.parse_args()
    try:
        arch = architecture()
        folder = args.install_dir.expanduser().resolve()
        if args.print_root:
            print(selected_root(folder, arch))
        else:
            root = install(args.archive.expanduser().resolve(), folder, arch)
            print(f'SDK ready: {root}\nNext: ./scripts/build.sh')
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(f'SDK setup failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
