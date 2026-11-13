/** Isolated adapter around the pinned VideoOps Factory; no model-written code runs. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {acquireNarration,narrationInputs,regular} from '../scripts/video-media.mjs';
const own=path.resolve(import.meta.dirname,'..');
const digest=v=>createHash('sha256').update(v).digest('hex');
const hash=async p=>digest(await fs.readFile(p));
const json=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const save=async(p,v)=>{await fs.writeFile(p+'.tmp',JSON.stringify(v,null,2)+'\n');await fs.rename(p+'.tmp',p);};
async function exists(p){try{await fs.access(p);return true;}catch{return false;}}
async function command(bin,args,{cwd,log,timeout=2100000}={}){
 return new Promise((resolve,reject)=>{
  const child=spawn(bin,args,{cwd,stdio:['ignore','pipe','pipe'],detached:process.platform!=='win32'});let output='',bytes=0,timed=false,writes=Promise.resolve();
  const kill=signal=>{try{if(process.platform==='win32')child.kill(signal);else process.kill(-child.pid,signal);}catch{}};
  const timer=setTimeout(()=>{timed=true;kill('SIGTERM');},timeout);
  const deadline=setTimeout(()=>kill('SIGKILL'),timeout+5000);
  const read=b=>{bytes+=b.length;if(bytes<8000000){output+=b.toString();if(log)writes=writes.then(()=>fs.appendFile(log,b));}else kill('SIGTERM');};
  child.stdout.on('data',read);child.stderr.on('data',read);
  child.on('error',e=>{clearTimeout(timer);clearTimeout(deadline);reject(e);});
  child.on('close',async code=>{clearTimeout(timer);clearTimeout(deadline);try{await writes;if(code!==0||timed||bytes>=8000000)throw Error(`${path.basename(bin)} failed (${code}); see ${log||'command diagnostics'}`);resolve(output);}catch(e){reject(e);}});
 });
}
export async function validateRequest(r){
 if(!r||!path.isAbsolute(r.workspace||'')||!path.isAbsolute(r.factoryRoot||''))throw Error('Absolute workspace and factoryRoot required');
 if(r.workspace===r.factoryRoot||r.workspace.startsWith(r.factoryRoot+path.sep))throw Error('Video workspace must be outside the pinned factory');
 if(typeof r.title!=='string'||!r.title.trim()||r.title.length>180||typeof r.objective!=='string'||!r.objective.trim()||r.objective.length>8000)throw Error('Bounded title and objective required');
 if(!Number.isFinite(r.duration)||r.duration<3||r.duration>60)throw Error('Duration must be 3–60 seconds');
 if(!Array.isArray(r.facts)||!r.facts.length||r.facts.length>30||r.facts.some(f=>typeof f.text!=='string'||!f.text||f.text.length>2000||typeof f.source!=='string'||!f.source||f.source.length>2000))throw Error('Sourced facts required');
 if(!Array.isArray(r.images)||!r.images.length||r.images.length>4)throw Error('Supply 1–4 registered evidence images');
 const ids=new Set(['kujo-logo','departure-mono','narration','music']);
 for(const a of r.images){if(!/^[-a-z0-9]{1,64}$/.test(a.id)||ids.has(a.id)||typeof a.source!=='string'||!a.source)throw Error('Invalid image identity/provenance');ids.add(a.id);await regular(a.path);const b=await fs.readFile(a.path);if(b.length>20000000||!(/^[a-f0-9]{64}$/.test(a.sha256))||digest(b)!==a.sha256)throw Error('Image checksum/size mismatch');if(!(b.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))||b[0]===255&&b[1]===216&&b[2]===255))throw Error('Only PNG/JPEG evidence accepted');}
 if(r.narration?.enabled){const n=r.narration;if(!path.isAbsolute(n.mediaWorkspace||''))throw Error('Narration requires an absolute mediaWorkspace');if(n.receiptPath){await regular(n.receiptPath);}else{if(n.authorize!==true||!n.requestPath||!n.authorizationPath)throw Error('Narration needs explicit request and scoped authorization');await regular(n.requestPath);await regular(n.authorizationPath);}}
 if(r.music){await regular(r.music.path);if(typeof r.music.source!=='string'||!r.music.source||typeof r.music.rights!=='string'||!r.music.rights||await hash(r.music.path)!==r.music.sha256||(await fs.stat(r.music.path)).size>128000000)throw Error('Music needs matching bytes, source and rights');}
 await narrationInputs(r.narration);return r;
}
async function requestHash(r){const inputs={...r,narrationInputs:await narrationInputs(r.narration),factoryCommit:(await command('git',['rev-parse','HEAD'],{cwd:r.factoryRoot})).trim(),overlaySha256:await hash(path.join(own,'scripts/video-static-template.mjs'))};if(r.narration?.enabled){inputs.narration={...r.narration};for(const k of ['requestPath','authorizationPath','receiptPath','audioPath'])if(r.narration[k])inputs.narration[k+'Sha256']=await hash(r.narration[k]);}return digest(JSON.stringify(inputs));}
async function bootstrap(r,job){
 const commit=(await command('git',['rev-parse','HEAD'],{cwd:r.factoryRoot})).trim();
 if((await command('git',['status','--porcelain','--untracked-files=no'],{cwd:r.factoryRoot})).trim())throw Error('Pinned VideoOps checkout has tracked changes');
 await fs.mkdir(job,{recursive:true});const tracked=(await command('git',['ls-files','-z'],{cwd:r.factoryRoot})).split('\0').filter(Boolean);const manifest=[];
 for(const file of tracked.filter(f=>/^(src\/|bin\/|assets\/|package(?:-lock)?\.json$)/.test(f))){const from=path.join(r.factoryRoot,file);await regular(from);const to=path.join(job,file);await fs.mkdir(path.dirname(to),{recursive:true});await fs.copyFile(from,to);manifest.push({path:file,sha256:await hash(from)});}
 await fs.mkdir(path.join(job,'.runtime/provider'),{recursive:true});
 for(const name of ['node_modules','.runtime/deps','.runtime/venv']){const source=path.join(r.factoryRoot,name);await fs.access(source);await fs.symlink(source,path.join(job,name),'dir');}
 const auth=path.join(r.factoryRoot,'.runtime/provider/auth.json');await regular(auth);await fs.copyFile(auth,path.join(job,'.runtime/provider/auth.json'));await fs.chmod(path.join(job,'.runtime/provider/auth.json'),0o600);
 const registry=await json(path.join(job,'assets/catalog.json'));registry.assets=registry.assets.filter(a=>['departure-mono','kujo-logo'].includes(a.id));
 for(const a of r.images){const file=a.id+(path.extname(a.path).toLowerCase()==='.jpg'?'.jpg':'.png');await fs.copyFile(a.path,path.join(job,'assets',file));registry.assets.push({id:a.id,file,kind:'image',sha256:a.sha256,source:a.source,rights:a.rights||'Source owner supplied this evidence for the authorized campaign'});}
 await save(path.join(job,'assets/catalog.json'),registry);
 await fs.rename(path.join(job,'src/template.mjs'),path.join(job,'src/template-original.mjs'));
 const wrapper=path.join(own,'scripts/video-static-template.mjs');await fs.copyFile(wrapper,path.join(job,'src/template.mjs'));
 const jobFiles=await Promise.all([...new Set([...manifest.map(f=>f.path),'src/template-original.mjs',...registry.assets.map(a=>'assets/'+a.file)])].map(async p=>({path:p,sha256:await hash(path.join(job,p))})));
 const provenance={commit,files:manifest,staticTemplateSha256:await hash(wrapper),jobFiles,description:'Pinned factory controller with registered launch assets and an explicitly hashed static template overlay'};await save(path.join(r.workspace,'factory-provenance.json'),provenance);return provenance;
}
async function probe(p){return JSON.parse(await command('ffprobe',['-v','error','-show_format','-show_streams','-of','json',p],{timeout:60000}));}
async function checkComposition(job,composition,log){
 for(const action of ['lint','check']){const result=JSON.parse(await command(path.join(job,'node_modules/.bin/hyperframes'),[action,composition,'--json'],{cwd:composition,log,timeout:180000}));if(!result.ok||result.browserSkipped)throw Error('Narrated composition '+action+' failed');}
}
export async function runVideo(input){
 const r=await validateRequest(input);await fs.mkdir(r.workspace,{recursive:true});const lock=path.join(r.workspace,'.video-lock');let handle;
 try{handle=await fs.open(lock,'wx');await handle.writeFile(String(process.pid));}catch{throw Error('Video workspace is locked; inspect the owner before retrying');}
 try{
 const fingerprint=await requestHash(r),marker=path.join(r.workspace,'request-fingerprint.json'),resultPath=path.join(r.workspace,'result.json');
 if(await exists(marker)){if((await json(marker)).sha256!==fingerprint)throw Error('Request changed: use a new immutable video workspace');}else await save(marker,{sha256:fingerprint});
 if(await exists(resultPath)){const result=await json(resultPath);for(const f of result.files)if(await hash(f.path)!==f.sha256)throw Error('Completed video artifact drift');return result;}
 const job=path.join(r.workspace,'factory-job'),provenancePath=path.join(r.workspace,'factory-provenance.json');const provenance=await exists(provenancePath)?await json(provenancePath):await bootstrap(r,job);
 for(const f of provenance.jobFiles)if(await hash(path.join(job,f.path))!==f.sha256)throw Error('Job source drift');
 const runs=path.join(job,'.runtime/runs');let children=await exists(runs)?await fs.readdir(runs):[];
 if(!children.length){const brief={schema:'kujo.videoops.brief/v1',id:'launch-'+fingerprint.slice(0,12),title:r.title,request:`${r.objective}\nUse only supplied claims and evidence. Start with a concrete benefit, show actual supplied product screens, end with the Kujo bumper. No captions, scene labels or invented metrics. This stage renders silent visuals; any authorized voice is attached by the coordinator after this run.`,facts:r.facts,assetIds:['departure-mono','kujo-logo',...r.images.map(a=>a.id)],width:1920,height:1080,fps:30,duration:r.duration,cta:r.cta||'Build your next factory with Kujo · kujolang.ai',audio:'silent'};await save(path.join(job,'launch-brief.json'),brief);await command(process.execPath,[path.join(job,'bin/videoops-factory.mjs'),'run',path.join(job,'launch-brief.json')],{cwd:job,log:path.join(r.workspace,'video-runner.log')});children=await fs.readdir(runs);}
 if(children.length!==1)throw Error('Expected one immutable child VideoOps run');
 const child=path.join(runs,children[0]),state=await json(path.join(child,'state.json'));await save(path.join(r.workspace,'child-run.json'),{id:state.id,workspace:child});if(state.status!=='REVIEW_INCOMPLETE')throw Error(`Child VideoOps run is ${state.status}; inspect evidence and start a new attempt`);
 let candidate=path.join(child,'output/draft.mp4'),narration=null;const output=path.join(child,'output');
 if(r.narration?.enabled||r.music){
 const inputs=[...await narrationInputs(r.narration),...(r.music?[{kind:'music',...r.music}]:[])];const generatorEvidence=path.join(output,'narration-inputs.json');const textInput=inputs.find(x=>x.kind==='narrationText');await save(generatorEvidence,{inputs,script:textInput?await fs.readFile(textInput.path,'utf8'):null,facts:r.facts,duration:r.duration,policy:'Only explicitly authorized canonical speech or registered music; preserve original; no perceptual approval'});
 const generatorReview=path.join(child,'narration-generation');await command(process.execPath,[path.join(own,'scripts/video-review.mjs'),job,generatorReview,generatorEvidence,'media-generator'],{cwd:job,log:path.join(r.workspace,'narration-generator.log')});
 }
 if(r.narration?.enabled){
 const inputs=await narrationInputs(r.narration);
 narration=await acquireNarration(r.narration,r.factoryRoot);const audioMeta=await probe(narration.audioPath);const speechDuration=Number(audioMeta.format.duration);if(!Number.isFinite(speechDuration)||speechDuration>r.duration-0.6)throw Error('Narration does not fit; revise the approved script or duration, never trim speech');
 const voice=path.join(child,'assets/launch-narration.wav');await command('ffmpeg',['-y','-v','error','-i',narration.audioPath,'-af',`loudnorm=I=-16:TP=-2:LRA=11,adelay=200:all=1,apad,atrim=duration=${r.duration}`,'-ar','48000','-ac','2',voice],{timeout:120000});
 await fs.copyFile(narration.receiptPath,path.join(output,'narration-receipt.json'));await fs.copyFile(narration.audioPath,path.join(output,'narration-source.wav'));await fs.copyFile(narration.originalPath,path.join(output,'narration-original.media'));if(await hash(path.join(output,'narration-source.wav'))!==narration.sha256||await hash(path.join(output,'narration-original.media'))!==narration.originalSha256||await hash(path.join(output,'narration-receipt.json'))!==narration.receiptSha256)throw Error('Narration changed during acquisition handoff');
 for(const input of inputs.filter(x=>x.kind==='narrationText'))await fs.copyFile(input.path,path.join(output,'narration-text.txt'));
 const composition=path.join(child,'production/hyperframes');await fs.copyFile(voice,path.join(composition,'assets/launch-narration.wav'));const htmlPath=path.join(composition,'index.html');let html=await fs.readFile(htmlPath,'utf8');html=html.replace(/<audio id="launch-narration"[^>]*><\/audio>/g,'');html=html.replace('</div><script>window.__timelines',`<audio id="launch-narration" class="clip" src="assets/launch-narration.wav" data-start="0" data-duration="${r.duration}" data-track-index="10"></audio></div><script>window.__timelines`);await fs.writeFile(htmlPath,html);await checkComposition(job,composition,path.join(r.workspace,'narration-composition.log'));
 candidate=path.join(output,'launch.mp4');await command('ffmpeg',['-y','-v','error','-i',path.join(output,'draft.mp4'),'-i',voice,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',candidate],{timeout:120000});
 narration={...narration,speechDuration,normalizedSha256:await hash(voice),listening:'not_attested'};
 }
 if(r.music){
 const source=path.join(output,'music-source.wav');await fs.copyFile(r.music.path,source);if(await hash(source)!==r.music.sha256)throw Error('Music changed during handoff');const mixed=path.join(child,'assets/launch-audio.wav');
 const inputs=['-y','-v','error','-stream_loop','-1','-i',source];if(narration)inputs.push('-i',path.join(child,'assets/launch-narration.wav'));
 const fade=Math.max(0,r.duration-0.4);const filters=narration?`[0:a]volume=0.12,atrim=duration=${r.duration},afade=t=out:st=${fade}:d=0.4[m];[1:a][m]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.794:level=0[out]`:`[0:a]volume=0.12,atrim=duration=${r.duration},afade=t=out:st=${fade}:d=0.4[out]`;
 await command('ffmpeg',[...inputs,'-filter_complex',filters,'-map','[out]','-ar','48000','-ac','2',mixed],{timeout:120000});candidate=path.join(output,'launch.mp4');await command('ffmpeg',['-y','-v','error','-i',path.join(output,'draft.mp4'),'-i',mixed,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',candidate],{timeout:120000});
 const composition=path.join(child,'production/hyperframes');await fs.copyFile(mixed,path.join(composition,'assets/launch-audio.wav'));const index=path.join(composition,'index.html');let html=await fs.readFile(index,'utf8');html=html.replace(/<audio id="launch-narration"[^>]*><\/audio>/g,'');html=html.replace(/<audio id="launch-audio"[^>]*><\/audio>/g,'');await fs.writeFile(index,html.replace('</div><script>window.__timelines',`<audio id="launch-audio" class="clip" src="assets/launch-audio.wav" data-start="0" data-duration="${r.duration}" data-track-index="10"></audio></div><script>window.__timelines`));await checkComposition(job,composition,path.join(r.workspace,'music-composition.log'));
 }
 const metadata=await probe(candidate),video=metadata.streams.find(s=>s.codec_type==='video');const duration=Number(metadata.format.duration);if(!video||video.width!==1920||video.height!==1080||video.r_frame_rate!=='30/1'||Math.abs(duration-r.duration)>0.12)throw Error('Final candidate metadata mismatch');if(Boolean(metadata.streams.find(s=>s.codec_type==='audio'))!==Boolean(narration||r.music))throw Error('Final audio presence mismatch');
 await command('ffmpeg',['-v','error','-xerror','-i',candidate,'-f','null','-'],{timeout:180000});const candidateSha256=await hash(candidate);
 const evidence={candidateSha256,duration,facts:r.facts,metadata,narration,music:r.music||null,technical:'PASS',perceptual:'REVIEW_INCOMPLETE',missingCapabilities:(narration||r.music)?['visual_playback','audio_listening']:['visual_playback']};const review=path.join(output,'launch-review.json');await save(review,evidence);
 if(narration||r.music){await command(process.execPath,[path.join(own,'scripts/video-review.mjs'),job,path.join(child,'narration-review'),review],{cwd:job,log:path.join(r.workspace,'narration-review.log')});const bin=path.join(job,'.runtime/venv/bin/videoops');await command(bin,['review','render-attempt','--workspace',child,'--attempt-id','narration-1','--outcome','succeeded']);await command(bin,['review','submit-candidate','--workspace',child,'--candidate','output/launch.mp4','--render-attempt-id','narration-1']);const decision={version:'videoops-review-decision/v1',id:'narration-technical-1',candidate_sha256:candidateSha256,technical:'PASS',perceptual:'REVIEW_INCOMPLETE',reviewer:{identity:'product-launch video adapter',type:'technical_tool',capabilities_exercised:['deterministic_validation']},evidence:['output/launch-review.json','narration-review/planning/video-critic.json'],defects:[],reviewed_at:new Date().toISOString()};if(await exists(path.join(output,'narration-decision.json'))){const previous=await json(path.join(output,'narration-decision.json'));if(previous.candidate_sha256!==candidateSha256)throw Error('Narrated candidate changed during resume');decision.reviewed_at=previous.reviewed_at;}await save(path.join(output,'narration-decision.json'),decision);await command(bin,['review','record','--workspace',child,'--decision',path.join(output,'narration-decision.json'),'--authorize-local']);}
 if(await requestHash(r)!==fingerprint)throw Error('Video inputs changed while work was running');
 const inputs=[...(r.music?[{kind:'music',...r.music}]:[]),...r.images.map(a=>({kind:'image',path:a.path,sha256:a.sha256})),...await narrationInputs(r.narration)];
 const extra=narration?[path.join(output,'narration-original.media'),path.join(output,'narration-inputs.json'),path.join(child,'narration-generation/planning/media-generator.json'),path.join(child,'narration-review/planning/video-critic.json'),path.join(child,'production/hyperframes/index.html')]:[];if(r.music)extra.push(path.join(output,'music-source.wav'),path.join(child,'assets/launch-audio.wav'));if(r.music&&!narration)extra.push(path.join(output,'narration-inputs.json'),path.join(child,'narration-generation/planning/media-generator.json'),path.join(child,'narration-review/planning/video-critic.json'));if(await exists(path.join(output,'narration-text.txt')))extra.push(path.join(output,'narration-text.txt'));
 for(const name of (await fs.readdir(path.join(child,'planning'))).filter(n=>n.endsWith('.json')))extra.push(path.join(child,'planning',name));extra.push(path.join(child,'state.json'),path.join(child,'events.jsonl'),path.join(child,'assets/registry.json'));
 const files=await Promise.all([candidate,review,provenancePath,...extra,...(narration?[path.join(child,'assets/launch-narration.wav'),path.join(output,'narration-receipt.json'),path.join(output,'narration-source.wav')]:[])].map(async p=>({path:p,sha256:await hash(p)})));
 const exportRoot=path.join(r.workspace,'export');await fs.rm(exportRoot,{recursive:true,force:true});await fs.mkdir(exportRoot,{recursive:true});await fs.mkdir(path.join(exportRoot,'evidence'),{recursive:true});
 await fs.copyFile(candidate,path.join(exportRoot,'launch.mp4'));await fs.cp(path.join(child,'production/hyperframes'),path.join(exportRoot,'composition'),{recursive:true});
 for(const f of files){if(f.path===candidate)continue;const label=path.relative(child,f.path).replaceAll(path.sep,'__').replaceAll('..','up');await fs.copyFile(f.path,path.join(exportRoot,'evidence',label));}
 await fs.copyFile(path.join(job,'assets/DepartureMono-LICENSE.txt'),path.join(exportRoot,'composition/assets/DepartureMono-LICENSE.txt'));
 const publicFiles=[];async function inventory(dir){for(const entry of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())await inventory(p);else{await regular(p);publicFiles.push({path:path.relative(exportRoot,p),sha256:await hash(p)});}}}await inventory(exportRoot);await save(path.join(exportRoot,'manifest.json'),{schema:'kujo.product-launch.video-export/v1',candidateSha256,duration,childRunId:state.id,status:'REVIEW_INCOMPLETE',files:publicFiles});for(const f of publicFiles)files.push({path:path.join(exportRoot,f.path),sha256:f.sha256});files.push({path:path.join(exportRoot,'manifest.json'),sha256:await hash(path.join(exportRoot,'manifest.json'))});
 const result={schema:'kujo.product-launch.video/v1',status:'REVIEW_INCOMPLETE',exportRoot,childRun:state.id,childRunId:state.id,childWorkspace:child,candidateSha256,duration,durationSeconds:duration,videoPath:candidate,paths:{video:candidate,review,state:path.join(child,'state.json'),events:path.join(child,'events.jsonl'),composition:path.join(child,'production/hyperframes')},factory:{commit:provenance.commit,provenancePath},narration,music:r.music||null,inputs,files};await save(resultPath,result);return result;
 }finally{await handle.close();await fs.unlink(lock);}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){try{const file=process.argv[2];if(!file)throw Error('Usage: node src/video.mjs REQUEST_JSON');console.log(JSON.stringify(await runVideo(await json(file))));}catch(e){console.error(e.message);process.exitCode=1;}}
