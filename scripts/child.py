#!/usr/bin/env python3
"""Invoke the pinned factories through their real Python entry points."""
import importlib.util
import json
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text())
root = Path(request['factoryRoot'])
workspace = Path(request['workspace'])
workspace.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root/'src'))
spec = importlib.util.spec_from_file_location('child_factory', root/'src/factory.py')
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)
factory.RUNS = workspace/'child-runs'
factory.RUNS.mkdir(exist_ok=True)

if request['kind'] == 'publishing':
    marker = workspace/'child.json'
    if marker.exists():
        state = Path(json.loads(marker.read_text())['path'])
        house = factory.load_operator().House(state, factory.DEPS)
        item = factory.read(state/'items/campaign.json')
        if item['status'] == 'blocked':
            house.resume('campaign')
    else:
        state = factory.initialize(request['brief'])
        factory.write(marker, {'id': state.name, 'path': str(state)})
    result = factory.advance(state)
    if result['status'] != 'approval_required':
        raise ValueError('Publishing House did not reach review: '+result['status'])
    checksum = factory.verify_package(state)
    factory.write(workspace/'result.json', {'childRun': state.name, 'path': str(state),
                  'packageSha256': checksum, 'status': result['status']})
elif request['kind'] == 'webops':
    prior = sorted(factory.RUNS.glob('*/state.json'))
    ready = [p for p in prior if factory.read(p)['status'] == 'approval_required']
    if ready:
        state = ready[-1].parent
    else:
        if factory.execute(request['brief'], fixture=False):
            raise ValueError('WebOps blocked; inspect child evidence before retrying')
        state = sorted(factory.RUNS.glob('*/state.json'))[-1].parent
    result = factory.verify(state)
    factory.write(workspace/'result.json', {**result, 'childRun': state.name,
                  'path': str(state), 'status': 'approval_required'})
else:
    raise ValueError('Unsupported child adapter')
