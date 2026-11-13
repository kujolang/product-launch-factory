#!/usr/bin/env python3
"""Install public, pinned child factories; never read personal sibling checkouts."""
import json
import fcntl
import re
import tempfile
import shutil
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'


def run(args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True, timeout=900,
                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def main():
    started = time.monotonic()
    RUNTIME.mkdir(exist_ok=True)
    guard = (RUNTIME / 'setup.lock').open('a')
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('Another setup process is active') from None
    try:
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        for name, source in lock['repositories'].items():
            if not re.fullmatch(r'[a-z][a-z0-9-]+', name) or not re.fullmatch(r'[a-f0-9]{40}', source['commit']) or source['url'] != f'https://github.com/kujolang/{name}.git':
                raise ValueError('Unexpected dependency origin')
            dest = RUNTIME / 'factories' / name
            dest.parent.mkdir(exist_ok=True)
            if not dest.exists():
                staging = Path(tempfile.mkdtemp(prefix=name+'-', dir=dest.parent))
                try:
                    run(['git', 'init', '-q'], staging)
                    run(['git', 'remote', 'add', 'origin', source['url']], staging)
                    run(['git', 'sparse-checkout', 'set', '--no-cone', '/*',
                         '!/docs/media/*.mp4', '!/docs/media/*.zip'], staging)
                    run(['git', '-c', 'credential.helper=', 'fetch', '--filter=blob:none',
                         '--depth=1', 'origin', source['commit']], staging)
                    run(['git', 'checkout', '--detach', 'FETCH_HEAD'], staging)
                    staging.rename(dest)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dest, text=True).strip()
            dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=dest, text=True).strip()
            if head != source['commit'] or dirty or dest.is_symlink():
                raise ValueError(f'{name} differs from its pin; preserve it before reinstalling')
            # Software evidence verification uses only Node built-ins. Building new
            # software is a separate, explicit Workcell setup, never an intake effect.
            if name != 'software-factory':
                run(['npm', 'ci'], dest)
                run(['npm', 'run', 'setup'], dest)
        run(['node', 'node_modules/.bin/playwright', 'install', 'chromium', '--only-shell'])
        receipt = {'ok': True, 'durationSeconds': round(time.monotonic()-started, 3),
                   'sources': lock['repositories'], 'providerCalls': 0,
                   'softwareExecutionConfigured': False}
        (RUNTIME / 'setup.json').write_text(json.dumps(receipt, indent=2)+'\n')
    finally:
        guard.close()


if __name__ == '__main__':
    main()
