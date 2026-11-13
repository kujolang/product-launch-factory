"""Bounded local artifacts and exact-version handoffs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
RUNS = RUNTIME / 'runs'
FACTORIES = RUNTIME / 'factories'


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(value if isinstance(value, str) else json.dumps(value, indent=2)+'\n')
        os.replace(tmp, path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()
    return path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def confined(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative:
        raise ValueError('Invalid relative path')
    parts = Path(relative)
    if parts.is_absolute() or '..' in parts.parts:
        raise ValueError('Path escapes artifact root')
    p = root
    for part in parts.parts:
        p = p / part
        if p.is_symlink():
            raise ValueError('Symlinks are not accepted')
    if p.resolve() == root or not p.resolve().is_relative_to(root):
        raise ValueError('Path escapes artifact root')
    return p


def inventory(root, exclude=()):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected plain artifact directory')
    result = {}
    total = 0
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            raise ValueError('Artifact tree contains a symlink')
        if p.is_dir():
            continue
        if not p.is_file():
            raise ValueError('Artifact tree contains a special file')
        if rel in exclude:
            continue
        total += p.stat().st_size
        if total > 512*1024*1024 or len(result) >= 12000:
            raise ValueError('Artifact inventory exceeds limits')
        result[rel] = digest(p)
    return result


def check_inventory(root, expected, exclude=()):
    actual = inventory(root, exclude)
    if actual != expected:
        changed = sorted(k for k in set(actual) | set(expected) if actual.get(k) != expected.get(k))
        raise ValueError('Artifact drift: '+', '.join(changed[:8]))
    return actual


def copy_tree(source, target):
    inventory(source)
    if Path(target).exists():
        raise ValueError('Refusing to replace an existing artifact tree')
    shutil.copytree(source, target)


def validate_brief(path):
    path = Path(path).resolve()
    if path.stat().st_size > 64000:
        raise ValueError('Brief exceeds 64 KB')
    brief = read(path)
    required = {'schema', 'title', 'audience', 'objective', 'voice', 'constraints', 'sources', 'evidence', 'video'}
    if set(brief) - {'visuals'} != required or brief['schema'] != 'kujo.product-launch.brief/v1':
        raise ValueError('Use the documented launch brief schema')
    for name in ['title', 'audience', 'objective', 'voice']:
        if not isinstance(brief[name], str) or not brief[name].strip() or len(brief[name]) > 8000:
            raise ValueError('Invalid brief '+name)
    if len(brief['title']) > 180:
        raise ValueError('Title must be at most 180 characters')
    if not isinstance(brief['constraints'], list) or len(brief['constraints']) > 15 or any(not isinstance(x, str) or len(x)>1500 for x in brief['constraints']):
        raise ValueError('Use up to 15 short constraints')
    if not isinstance(brief['sources'], list) or not 1 <= len(brief['sources']) <= 8:
        raise ValueError('Provide 1–8 captured text sources')
    import re
    from urllib.parse import urlsplit
    seen = set()
    for s in brief['sources']:
        if set(s) != {'id', 'path', 'url'} or not re.fullmatch('[a-z][a-z0-9-]{0,39}', s['id']) or s['id'] in seen:
            raise ValueError('Invalid or duplicate source')
        seen.add(s['id'])
        p = confined(path.parent, s['path'])
        if not p.is_file() or p.stat().st_size > 100000 or not p.read_text().strip():
            raise ValueError('Sources must be nonempty UTF-8 files under 100 KB')
        url = urlsplit(s['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Source provenance needs a public HTTPS URL')
    evidence = brief['evidence']
    if set(evidence) != {'kind', 'path'} or evidence['kind'] not in ['software-export', 'webops-package']:
        raise ValueError('Provide Software Factory or WebOps evidence')
    inventory(confined(path.parent, evidence['path']))
    video = brief['video']
    if set(video) - {'duration', 'narration'} or 'duration' not in video or not isinstance(video['duration'], (int, float)) or not 12 <= video['duration'] <= 60:
        raise ValueError('Video duration must be 12–60 seconds')
    if video.get('narration') is not None and not isinstance(video['narration'], dict):
        raise ValueError('Narration must be an explicit authorization/receipt object')
    visuals = brief.get('visuals', [])
    if not isinstance(visuals, list) or len(visuals)>3:
        raise ValueError('Use at most three product visuals')
    visual_ids = set()
    for visual in visuals:
        if set(visual) != {'id', 'path', 'url', 'description', 'rights'} or not re.fullmatch('[a-z][a-z0-9-]{0,39}', visual['id']):
            raise ValueError('Invalid visual registration')
        if visual['id'] in visual_ids or visual['id'] in ['launch-website', 'kujo-logo', 'departure-mono', 'narration', 'music']:
            raise ValueError('Duplicate or reserved visual ID')
        visual_ids.add(visual['id'])
        p = confined(path.parent, visual['path'])
        if p.suffix.lower() not in ['.png', '.jpg', '.jpeg'] or p.stat().st_size > 5000000:
            raise ValueError('Use a local PNG/JPEG under 5 MB')
        if not all(isinstance(visual[k], str) and visual[k].strip() for k in ['url', 'description', 'rights']):
            raise ValueError('Visual source, description and rights are required')
    if len(brief.get('visuals', [])) > 4:
        raise ValueError('Use at most four product visuals')
    return brief


def seal(run):
    run = Path(run)
    package = run / 'package'
    files = inventory(package, ['manifest.json'])
    if not files:
        raise ValueError('Cannot seal an empty launch')
    manifest = {'schema': 'kujo.product-launch.package/v1', 'run': run.name,
                'files': files, 'inputHash': identity(inventory(run/'input')),
                'reviewRequired': ['editorial', 'website', 'video-playback-and-listening'],
                'deploymentAuthorized': False}
    write(package/'manifest.json', manifest)
    return digest(package/'manifest.json')


def verify(run):
    run = Path(run)
    m = read(run/'package/manifest.json')
    expected_id = read(run/'state.json')['id'] if (run/'state.json').exists() else run.name
    if m.get('schema') != 'kujo.product-launch.package/v1' or m.get('run') != expected_id:
        raise ValueError('Invalid launch package identity')
    check_inventory(run/'package', m['files'], ['manifest.json'])
    if identity(inventory(run/'input')) != m['inputHash']:
        raise ValueError('Captured inputs changed; approval is invalid')
    checksum = digest(run/'package/manifest.json')
    approval = read(run/'approval.json') if (run/'approval.json').exists() else None
    approved = bool(approval and approval.get('packageSha256') == checksum and approval.get('videoReviewed') is True)
    return {'ok': True, 'packageSha256': checksum, 'files': len(m['files']),
            'approvalValid': approved, 'deploymentAuthorized': False}


def approve(run, expected, reviewer, video_reviewed):
    if not reviewer.strip() or len(reviewer)>200 or not video_reviewed:
        raise ValueError('Explicit reviewer and full video review acknowledgment required')
    result = verify(run)
    if result['packageSha256'] != expected:
        raise ValueError('Approval must name the current exact package hash')
    write(Path(run)/'approval.json', {'schema': 'kujo.product-launch.approval/v1',
          'packageSha256': expected, 'reviewer': reviewer, 'videoReviewed': True,
          'recordedAt': now(), 'scope': 'local-launch-package-only', 'deploymentAuthorized': False})
    return verify(run)
