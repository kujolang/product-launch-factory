#!/usr/bin/env python3
"""Versioned, resumable handoffs between the existing Kujo factories."""
import argparse
import fcntl
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from core import ROOT, RUNTIME, RUNS, FACTORIES, now, read, write, digest, identity
from core import confined, inventory, check_inventory, copy_tree, validate_brief, seal, verify, approve

STAGES = ['source', 'editorial', 'website', 'video', 'package']
NAMES = {'source': 'Source evidence', 'editorial': 'Publishing House',
         'website': 'WebOps', 'video': 'VideoOps', 'package': 'Launch review'}
ARTIFACT_CSP = "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; script-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"


def run_path(name):
    if not re.fullmatch(r'[a-z0-9-]{1,90}', name):
        raise ValueError('Invalid run ID')
    return confined(RUNS, name)


def event(run, stage, status, detail):
    with (run/'events.jsonl').open('a') as out:
        out.write(json.dumps({'at': now(), 'stage': stage, 'status': status, 'detail': detail})+'\n')


def command(run, label, args, cwd=None, lock_fd=None, timeout=3600):
    logs = run/'logs'
    logs.mkdir(exist_ok=True)
    started = time.monotonic()
    with (logs/(label+'.log')).open('a') as out:
        process = subprocess.Popen([str(x) for x in args], cwd=cwd or ROOT,
                    stdout=out, stderr=subprocess.STDOUT,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                    pass_fds=(() if lock_fd is None else (lock_fd,)), start_new_session=True)
        write(logs/(label+'-process.json'), {'pid': process.pid, 'startedAt': now(), 'command': [str(x) for x in args]})
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    receipt = {'command': [str(x) for x in args], 'exitCode': code,
               'durationSeconds': round(time.monotonic()-started, 3), 'finishedAt': now()}
    write(logs/(label+'-receipt.json'), receipt)
    if code:
        raise ValueError(label+' failed; inspect logs/'+label+'.log')
    return receipt


def doctor():
    checks = []
    for name, pin in read(ROOT/'sources.lock.json')['repositories'].items():
        path = FACTORIES/name
        try:
            actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
            dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=path, text=True).strip()
            ok = not path.is_symlink() and actual == pin['commit'] and not dirty
            if name != 'software-factory':
                ok = ok and (path/'node_modules').is_dir() and (path/'.runtime/deps').is_dir()
        except (OSError, subprocess.CalledProcessError):
            ok = False
        checks.append({'name': name, 'ok': ok})
    checks.append({'name': 'ffmpeg', 'ok': bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))})
    return {'ok': all(x['ok'] for x in checks), 'checks': checks,
            'providerConfigured': (RUNTIME/'provider/auth.json').is_file(), 'deploymentEnabled': False}


def authenticate_children():
    auth = RUNTIME/'provider/auth.json'
    if not auth.is_file():
        raise ValueError('Run npm run login before live campaigns')
    for name in ['publishing-house-factory', 'webops-factory', 'videoops-factory']:
        dest = FACTORIES/name/'.runtime/provider'
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = dest/'auth.json'
        if not target.exists():
            with target.open('xb') as out:
                out.write(auth.read_bytes())
            target.chmod(0o600)


def initialize(brief_path):
    path = Path(brief_path).resolve()
    brief = validate_brief(path)
    rid = time.strftime('%Y%m%d-%H%M%S', time.gmtime())+'-'+uuid.uuid4().hex[:8]
    run = run_path(rid)
    (run/'input/sources').mkdir(parents=True)
    frozen = {**brief, 'sources': [], 'visuals': []}
    for source in brief['sources']:
        target = 'sources/'+source['id']+'.txt'
        shutil.copyfile(confined(path.parent, source['path']), run/'input'/target)
        frozen['sources'].append({**source, 'path': target})
    for visual in brief.get('visuals', []):
        src = confined(path.parent, visual['path'])
        target = 'visuals/'+visual['id']+src.suffix.lower()
        (run/'input/visuals').mkdir(exist_ok=True)
        shutil.copyfile(src, run/'input'/target)
        frozen['visuals'].append({**visual, 'path': target, 'sha256': digest(src)})
    copy_tree(confined(path.parent, brief['evidence']['path']), run/'input/evidence')
    frozen['evidence'] = {**brief['evidence'], 'path': 'evidence'}
    write(run/'input/brief.json', frozen)
    write(run/'input/factories.json', read(ROOT/'sources.lock.json'))
    write(run/'input-seal.json', inventory(run/'input'))
    state = {'schema': 'kujo.product-launch.run/v1', 'id': rid, 'title': brief['title'],
             'status': 'ready', 'startedAt': now(), 'stage': 'source', 'stages': [],
             'mode': 'live', 'deploymentAuthorized': False}
    write(run/'state.json', state)
    event(run, 'source', 'ready', 'Launch brief and source evidence captured')
    return run


def source_stage(run, out, lock_fd):
    brief = read(run/'input/brief.json')
    evidence = run/'input/evidence'
    if brief['evidence']['kind'] == 'software-export':
        command(run, 'software-evidence', ['node', FACTORIES/'software-factory/factory/evidence.mjs', 'verify', evidence], lock_fd=lock_fd)
        result = {'factory': 'software-factory', 'operation': 'portable-evidence-verification',
                  'manifestSha256': digest(evidence/'manifest.json'), 'newSoftwareBuild': False}
    else:
        # The selected product already exists. Verify its retained WebOps package
        # without pretending a fresh Software Factory build took place.
        manifest = read(evidence/'package.json')
        if manifest.get('schema') != 'kujo.webops-factory.package/v1' or not manifest.get('files'):
            raise ValueError('Invalid WebOps evidence package')
        for f in manifest['files']:
            if digest(confined(evidence, f['path'])) != f['sha256']:
                raise ValueError('Product evidence drift: '+f['path'])
        state = read(evidence/'state.json')
        if state['status'] != 'approval_required' or read(evidence/'after-findings.json'):
            raise ValueError('Example product evidence did not pass its supported checks')
        result = {'factory': 'webops-factory', 'operation': 'existing-product-evidence',
                  'manifestSha256': digest(evidence/'package.json'), 'productRun': state['id'],
                  'counts': state['counts'], 'newSoftwareBuild': False}
    write(out/'verification.json', result)
    for source in brief['sources']:
        shutil.copyfile(run/'input'/source['path'], out/(source['id']+'.txt'))
    return result


def editorial_stage(run, out, lock_fd):
    brief = read(run/'input/brief.json')
    work = run/'work/editorial'
    work.mkdir(parents=True, exist_ok=True)
    if not (work/'sources').exists():
        copy_tree(run/'input/sources', work/'sources')
    publishing = {k: brief[k] for k in ['title', 'audience', 'objective', 'voice', 'constraints', 'sources']}
    publishing['schema'] = 'kujo.publishing-house-factory.brief/v1'
    publishing['constraints'] = publishing['constraints']+[
        'Produce the article, newsletter, exactly three social posts and landing copy from captured evidence. Do not invent features or omit limitations.',
        'This is a draft launch package, not publication. Preserve exact claims and source references for downstream factories.']
    write(work/'brief.json', publishing)
    request = write(work/'request.json', {'kind': 'publishing', 'factoryRoot': str(FACTORIES/'publishing-house-factory'),
                    'workspace': str(work), 'brief': str(work/'brief.json')})
    command(run, 'publishing-house', [sys.executable, ROOT/'scripts/child.py', request], lock_fd=lock_fd)
    result = read(work/'result.json')
    child = Path(result['path'])
    copy_tree(child, out/'campaign')
    write(out/'child.json', result)
    return result


def landing(run, target):
    adaptations = read(run/'stages/editorial/campaign/output/adaptations.json')
    doc = adaptations['landing']
    brief = read(run/'input/brief.json')
    target.mkdir(parents=True, exist_ok=True)
    image = ''
    if brief.get('visuals'):
        visual = brief['visuals'][0]
        src = run/'input'/visual['path']
        name = 'product'+src.suffix
        shutil.copyfile(src, target/name)
        image = '<img class="product" src="'+name+'" alt="'+html.escape(visual['description'], quote=True)+'">'
    body = ''.join('<p>'+html.escape(block['text'])+'</p>' for block in doc['blocks'])
    title = html.escape(doc['title'])
    source = html.escape(brief['sources'][0]['url'], quote=True)
    # Search description is a WebOps responsibility; it is intentionally absent
    # from this copy-only handoff rather than invented by the coordinator.
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><link rel="stylesheet" href="style.css"></head><body><header><b>Kujo</b><span>PRODUCT LAUNCH</span></header><main><div class="eyebrow">A CLEARER WAY TO WORK</div><h1>'+title+'</h1><a class="cta" href="'+source+'">Explore the project ↗</a>'+image+'<section>'+body+'</section><aside>Review candidate · Nothing deployed</aside></main><footer>Built with Kujo · kujolang.ai</footer></body></html>'
    write(target/'index.html', page)
    write(target/'style.css', 'html{background:#f5f5f0;color:#171919;font-family:Arial,sans-serif}body{margin:0}header,footer{padding:24px 6%;border-bottom:1px solid #c5c7c3;display:flex;justify-content:space-between}header b{font-size:28px;letter-spacing:-2px}header span,.eyebrow,footer,aside{font:12px monospace;letter-spacing:2px}main{max-width:1080px;margin:70px auto;padding:0 6%}h1{font-size:clamp(38px,6vw,72px);letter-spacing:-3px;line-height:1.05;max-width:1000px;margin:24px 0 36px}.cta{display:inline-block;background:#171919;color:#fff;padding:18px 24px;text-decoration:none;font-weight:bold}.product{display:block;width:100%;height:auto;margin-top:48px;border:1px solid #b9bcb8}section{max-width:780px;margin:56px 0}p{font-size:19px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}aside{padding:25px 0;border-top:1px solid #a8aba6}footer{border-top:1px solid #c5c7c3;margin-top:60px}a:focus{outline:3px solid #777;outline-offset:4px}')


def website_stage(run, out, lock_fd):
    work = run/'work/website'
    work.mkdir(parents=True, exist_ok=True)
    if not (work/'site').exists():
        landing(run, work/'site')
    write(work/'brief.json', {'title': read(run/'input/brief.json')['title']+' — launch website',
          'site': 'site', 'objective': 'Complete the supported checks on this reviewed static launch page. Derive search metadata only from its actual copy. Preserve all factual qualifications and design. No deployment.'})
    request = write(work/'request.json', {'kind': 'webops', 'factoryRoot': str(FACTORIES/'webops-factory'),
                    'workspace': str(work), 'brief': str(work/'brief.json')})
    command(run, 'webops', [sys.executable, ROOT/'scripts/child.py', request], lock_fd=lock_fd)
    result = read(work/'result.json')
    copy_tree(Path(result['path']), out/'inspection')
    write(out/'child.json', result)
    return result


def video_stage(run, out, lock_fd):
    brief = read(run/'input/brief.json')
    evidence = read(run/'stages/editorial/campaign/phases/evidence-dossier.json')['result']
    facts = [{'text': c['text'], 'source': next(s['url'] for s in brief['sources'] if s['id'] == c['sourceId'])} for c in evidence['claims']]
    images = []
    for visual in brief.get('visuals', []):
        images.append({'id': visual['id'], 'path': str(run/'input'/visual['path']),
                       'sha256': visual['sha256'], 'source': visual['url'], 'rights': visual['rights']})
    screenshot = run/'stages/website/inspection/evidence/after/lens/screenshots/desktop.png'
    images.append({'id': 'launch-website', 'path': str(screenshot), 'sha256': digest(screenshot),
                   'source': 'Verified launch website from this run', 'rights': 'Owner-authorized campaign screenshot'})
    work = run/'work/video'
    work.mkdir(parents=True, exist_ok=True)
    request = write(work/'request.json', {'workspace': str(work), 'factoryRoot': str(FACTORIES/'videoops-factory'),
            'title': brief['title'], 'objective': brief['objective'], 'facts': facts, 'images': images,
            'duration': brief['video']['duration'], 'narration': brief['video'].get('narration', {'enabled': False})})
    command(run, 'videoops', ['node', ROOT/'src/video.mjs', request], lock_fd=lock_fd)
    result = read(work/'result.json')
    # The adapter exports a public artifact tree separate from its private job
    # checkout and credential home. Never recursively copy a whole worker tree.
    export = Path(result['exportRoot'])
    copy_tree(export, out/'production')
    write(out/'child.json', result)
    return result


def package_stage(run, out, lock_fd):
    package = run/'package'
    if package.exists():
        shutil.rmtree(package)
    package.mkdir()
    for name in ['article.md', 'newsletter.md', 'social.md', 'article.json', 'adaptations.json']:
        shutil.copyfile(run/'stages/editorial/campaign/output'/name, package/name)
    write(package/'evidence.json', read(run/'stages/editorial/campaign/phases/evidence-dossier.json')['result'])
    copy_tree(run/'stages/website/inspection/candidate', package/'website')
    copy_tree(run/'stages/video/production', package/'video')
    copy_tree(run/'handoffs', package/'handoffs')
    copy_tree(run/'input', package/'source-evidence')
    copy_tree(run/'stages/website/inspection/evidence', package/'website-checks')
    copy_tree(run/'stages/editorial/campaign/proposals', package/'editorial-proposals')
    write(package/'README.md', '# Launch review package\n\nReview the article, newsletter, three social posts, website and video. Handoffs and source evidence identify the exact inputs. Video listening and human editorial review remain required. Nothing has been deployed.\n')
    checksum = seal(run)
    write(out/'receipt.json', {'packageSha256': checksum, 'status': 'approval_required'})
    return verify(run)


def narration_fingerprint(run):
    config = read(run/'input/brief.json')['video'].get('narration') or {}
    result = {}
    for key in ['requestPath', 'authorizationPath', 'receiptPath', 'audioPath']:
        if key in config:
            result[key] = digest(Path(config[key]))
    return result


def advance(run):
    run = Path(run)
    with (run/'runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This launch still has an active runner or child; do not start another') from None
        state = read(run/'state.json')
        if state.get('mode') == 'recorded':
            raise ValueError('Recorded campaigns are read-only; start a new live run')
        check_inventory(run/'input', read(run/'input-seal.json'))
        if not doctor()['ok']:
            raise ValueError('Dependency check failed; run npm run setup and doctor')
        authenticate_children()
        state['status'] = 'running'
        write(run/'state.json', state)
        stage_functions = [source_stage, editorial_stage, website_stage, video_stage, package_stage]
        try:
            for index, (name, operation) in enumerate(zip(STAGES, stage_functions)):
                deps = {s: read(run/'handoffs'/f'{s}.json')['outputHash'] for s in STAGES[:index]}
                signature = identity({'input': read(run/'input-seal.json'), 'dependencies': deps,
                                      'narration': narration_fingerprint(run) if name in ['video', 'package'] else None})
                handoff = run/'handoffs'/f'{name}.json'
                output = run/'stages'/name
                state['stage'] = name
                if handoff.exists():
                    prior = read(handoff)
                    if prior['inputHash'] != signature:
                        raise ValueError('Handoff input changed; start a new launch version')
                    check_inventory(output, prior['files'])
                    if name == 'package':
                        verify(run)
                    event(run, name, 'reused', 'Exact prior handoff verified; no repeated provider calls')
                    continue
                attempt = run/'work'/name/'input-signature.json'
                if attempt.exists() and read(attempt)['sha256'] != signature:
                    raise ValueError('Incomplete stage inputs changed; start a new launch version')
                write(attempt, {'sha256': signature})
                if output.exists():
                    history = run/'attempts'/name/(str(time.time_ns()))
                    history.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(output), str(history))
                output.mkdir(parents=True)
                stage = {'id': name, 'name': NAMES[name], 'status': 'running', 'startedAt': now()}
                state['stages'] = [s for s in state['stages'] if s['id'] != name]+[stage]
                write(run/'state.json', state)
                event(run, name, 'started', NAMES[name]+' received verified inputs')
                started = time.monotonic()
                result = operation(run, output, lock.fileno())
                files = inventory(output)
                receipt = {'schema': 'kujo.product-launch.handoff/v1', 'stage': name,
                           'next': STAGES[index+1] if index+1<len(STAGES) else 'human-review',
                           'inputHash': signature, 'outputHash': identity(files), 'files': files,
                           'factoryRevisions': read(run/'input/factories.json')['repositories'],
                           'result': result, 'finishedAt': now()}
                write(handoff, receipt)
                stage.update(status='completed', durationSeconds=round(time.monotonic()-started, 3), finishedAt=now())
                write(run/'state.json', state)
                event(run, name, 'completed', 'Exact output inventory sealed for the next factory')
            state['status'] = 'approval_required'
            state['packageSha256'] = verify(run)['packageSha256']
            state.pop('error', None)
        except Exception as error:
            state['status'] = 'blocked'
            state['error'] = str(error)
            for stage in state['stages']:
                if stage['status'] == 'running':
                    stage['status'] = 'blocked'
            event(run, state['stage'], 'blocked', str(error))
        state['updatedAt'] = now()
        write(run/'state.json', state)
        return state


def statuses():
    records = []
    for p in sorted(RUNS.glob('*/state.json'), reverse=True)[:60]:
        state = read(p)
        if (p.parent/'package/manifest.json').exists():
            try:
                proof = verify(p.parent)
                state['status'] = 'approved_local' if proof['approvalValid'] else state['status']
            except (ValueError, OSError, KeyError) as error:
                state['status'] = 'stale'
                state['error'] = str(error)
        work = p.parent/'work'
        children = {}
        editorial = work/'editorial/child.json'
        if editorial.exists():
            child = Path(read(editorial)['path'])
            if child.is_relative_to(work) and (child/'items/campaign.json').exists():
                item = read(child/'items/campaign.json')
                children['editorial'] = {k: item[k] for k in ['status', 'phase_index', 'current_phase'] if k in item}
        for stage, pattern in [('website', 'website/child-runs/*/state.json'),
                               ('video', 'video/factory-job/.runtime/runs/*/state.json')]:
            matches = sorted(work.glob(pattern))
            if matches:
                item = read(matches[-1])
                children[stage] = {k: item[k] for k in ['status', 'phase', 'stage'] if k in item}
        state['children'] = children
        records.append(state)
    return records


def serve(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') not in [f'127.0.0.1:{port}', f'localhost:{port}']:
                self.send_error(403)
                return
            path = unquote(urlsplit(self.path).path)
            try:
                artifact = False
                if path == '/api/runs':
                    body = json.dumps(statuses()).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == '/':
                    file = ROOT/'web/index.html'
                elif path.startswith('/artifact/'):
                    parts = path.split('/')
                    relative = '/'.join(parts[3:])
                    if not relative.startswith(('package/', 'stages/', 'handoffs/', 'logs/')):
                        raise ValueError('Private artifact')
                    file = confined(run_path(parts[2]), relative)
                    artifact = True
                else:
                    self.send_error(404)
                    return
                size = file.stat().st_size
                start, end, code = 0, size-1, 200
                if self.headers.get('Range'):
                    match = re.fullmatch(r'bytes=(\d+)-(\d*)', self.headers['Range'])
                    if not match:
                        self.send_error(416)
                        return
                    start = int(match[1])
                    end = min(int(match[2]) if match[2] else end, end)
                    if start > end:
                        self.send_error(416)
                        return
                    code = 206
                self.send_response(code)
                self.send_header('Content-Type', mimetypes.guess_type(file)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(end-start+1))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                if code == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                if artifact:
                    self.send_header('Content-Security-Policy', ARTIFACT_CSP)
                self.end_headers()
                with file.open('rb') as stream:
                    stream.seek(start)
                    remaining = end-start+1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (ValueError, OSError, KeyError, IndexError):
                self.send_error(404)

        def log_message(self, *_):
            pass

    print(f'Product Launch Factory: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def import_demo():
    source = ROOT/'docs/example-run'
    state = read(source/'state.json')
    verify(source)
    target = run_path(state['id'])
    if target.exists():
        if read(target/'state.json').get('mode') != 'recorded':
            raise ValueError('A live campaign already uses this ID; refusing to replace it')
        verify(target)
    else:
        copy_tree(source, target)
        state['mode'] = 'recorded'
        state['recordedExample'] = True
        write(target/'state.json', state)
    return {'ok': True, 'run': state['id'], 'mode': 'recorded', 'providerCalls': 0}


def main():
    parser = argparse.ArgumentParser(description='Coordinate reviewed launch artifacts; no deployment.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('status')
    sub.add_parser('demo')
    sub.add_parser('run').add_argument('brief')
    sub.add_parser('resume').add_argument('run')
    sub.add_parser('verify').add_argument('run')
    p = sub.add_parser('approve')
    p.add_argument('run')
    p.add_argument('--package-sha256', required=True)
    p.add_argument('--reviewer', required=True)
    p.add_argument('--video-reviewed', action='store_true')
    p = sub.add_parser('serve')
    p.add_argument('--port', type=int, default=4384)
    args = parser.parse_args()
    if args.command == 'serve':
        serve(args.port)
        return 0
    if args.command == 'demo':
        result = import_demo()
    elif args.command == 'doctor':
        result = doctor()
    elif args.command == 'status':
        result = statuses()
    elif args.command == 'verify':
        result = verify(run_path(args.run))
    elif args.command == 'approve':
        result = approve(run_path(args.run), args.package_sha256, args.reviewer, args.video_reviewed)
    else:
        run = initialize(args.brief) if args.command == 'run' else run_path(args.run)
        print('Launch run: '+run.name, flush=True)
        result = advance(run)
    print(json.dumps(result, indent=2))
    return 1 if isinstance(result, dict) and (result.get('status') == 'blocked' or result.get('ok') is False) else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
