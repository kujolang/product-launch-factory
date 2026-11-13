"""Fresh-runner installation qualification; no account credentials or model calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

root = Path.cwd()
evidence = root / 'onboarding-evidence'
evidence.mkdir(exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='launch-onboarding-'))
home = work / 'home'
home.mkdir()
repo = work / 'factory'
env = {**os.environ, 'HOME': str(home), 'npm_config_cache': str(home / 'npm'),
       'PIP_CACHE_DIR': str(home / 'pip'), 'XDG_CACHE_HOME': str(home / 'cache'),
       'PLAYWRIGHT_BROWSERS_PATH': str(home / 'browsers'), 'GIT_CONFIG_NOSYSTEM': '1'}
for key in list(env):
    if any(word in key.upper() for word in ('TOKEN', 'API_KEY', 'SECRET')):
        env.pop(key)
receipt = {'ok': False, 'baseline': 'Fresh GitHub Ubuntu 24.04 runner; Git, Node 26.12.1 and Python 3.12 provisioned before timing',
           'emptyApplicationCaches': True, 'providerCalls': 0, 'loginTested': False, 'steps': []}
start = time.monotonic()
def run(name, command, cwd=repo):
    tick = time.monotonic()
    with (evidence / (name + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    receipt['steps'].append({'name': name, 'seconds': round(time.monotonic()-tick, 3), 'exitCode': result.returncode})
    print(name, receipt['steps'][-1], flush=True)
    result.check_returncode()
try:
    run('clone', ['git', 'clone', 'https://github.com/kujolang/product-launch-factory.git', str(repo)], work)
    run('checkout', ['git', 'checkout', '--detach', os.environ['GITHUB_SHA']])
    receipt['commit'] = os.environ['GITHUB_SHA']
    run('system-packages', ['sudo', 'apt-get', 'update'])
    run('ffmpeg', ['sudo', 'apt-get', 'install', '-y', 'ffmpeg'])
    run('npm-ci', ['npm', 'ci'])
    run('browser-system-libraries', ['node', 'node_modules/playwright/cli.js', 'install-deps', 'chromium'])
    run('setup', ['npm', 'run', 'setup'])
    run('doctor', ['python3', 'src/launch.py', 'doctor'])
    doctor = json.loads((evidence / 'doctor.log').read_text())
    assert doctor['ok'] and not doctor['providerConfigured']
    receipt['readyBeforeLoginSeconds'] = round(time.monotonic()-start, 3)
    run('verify', ['npm', 'run', 'verify'])
    run('demo', ['npm', 'run', 'demo'])
    run('browser-smoke', ['node', 'scripts/test-onboarding-browser.mjs'])
    receipt['ok'] = True
finally:
    receipt['totalSeconds'] = round(time.monotonic()-start, 3)
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
