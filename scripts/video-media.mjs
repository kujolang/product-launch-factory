/** Acquire speech through the canonical runtime or verify a supplied canonical receipt. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const hash=async p=>createHash('sha256').update(await fs.readFile(p)).digest('hex');
export async function regular(p){
 if(typeof p!=='string'||!path.isAbsolute(p))throw Error('Use absolute media paths');
 const s=await fs.lstat(p);if(!s.isFile()||s.isSymbolicLink())throw Error('Media input must be a regular file');
 let current=path.parse(p).root;for(const segment of p.slice(current.length).split(path.sep)){current=path.join(current,segment);if((await fs.lstat(current)).isSymbolicLink())throw Error('Symlink media input rejected');}
 return p;
}
function contained(root,relative){
 if(typeof relative!=='string'||path.isAbsolute(relative)||relative.split(/[\\/]/).includes('..'))throw Error('Unsafe receipt path');
 const p=path.resolve(root,relative);if(!p.startsWith(path.resolve(root)+path.sep))throw Error('Receipt path escapes media workspace');return p;
}
function run(bin,args,cwd){
 const r=spawnSync(bin,args,{cwd,encoding:'utf8',timeout:360000,maxBuffer:8000000});
 if(r.error||r.status!==0)throw Error(`Canonical media ${args[1]||''} failed; inspect its workspace result (no automatic retry)`);
 return r.stdout;
}
export async function narrationInputs(n){
 if(!n?.enabled)return [];
 const refs=[];
 async function evidence(ref,kind){if(!ref)return;const p=contained(n.mediaWorkspace,ref.path);await regular(p);const sha256=await hash(p);if(sha256!==ref.sha256)throw Error('Narration referenced evidence drift');if(!refs.some(x=>x.path===p))refs.push({kind,path:p,sha256});}
 if(n.receiptPath){const receipt=JSON.parse(await fs.readFile(n.receiptPath,'utf8'));for(const ref of [receipt.original,...(receipt.derived||[])])await evidence(ref,'receiptMedia');if(receipt.manifest_path){const p=contained(n.mediaWorkspace,receipt.manifest_path);await regular(p);refs.push({kind:'usageRegistry',path:p,sha256:await hash(p)});}}

 for(const key of ['requestPath','authorizationPath','receiptPath','audioPath'])if(n[key]){await regular(n[key]);refs.push({kind:key,path:n[key],sha256:await hash(n[key])});}
 if(n.requestPath){
  const request=JSON.parse(await fs.readFile(n.requestPath,'utf8'));
  if(request.schema!=='videoops-media-request/v1'||request.capability!=='speech')throw Error('Canonical speech request required');
  const input=contained(n.mediaWorkspace,request.input?.path);await regular(input);const sha256=await hash(input);if(sha256!==request.input?.sha256)throw Error('Narration text drift');
  const text=await fs.readFile(input,'utf8');if(!text.trim()||text.length>500)throw Error('Narration must contain 1–500 characters');
  refs.push({kind:'narrationText',path:input,sha256});await evidence(request.rights?.evidence,'rightsEvidence');await evidence(request.budget?.estimate_evidence,'budgetEvidence');
  if(!n.receiptPath){
   const authority=JSON.parse(await fs.readFile(n.authorizationPath,'utf8'));for(const bound of authority.request_bounds||[])await evidence(bound.evidence,'scopeEvidence');for(const entitlement of authority.entitlements||[])await evidence(entitlement.evidence,'entitlementEvidence');
   if(request.budget?.max_cost!==0||!Number.isFinite(request.budget?.max_credits)||request.budget.max_credits>500||authority.max_cost!==0||authority.max_calls!==1||authority.max_credits>500||!authority.entitlements?.some(e=>e.capability==='speech'&&e.allowed===true&&e.no_overage===true))throw Error('Speech must be scoped to one included-allowance call, at most 500 credits, no overage');
  }
 }
 return refs;
}
export async function acquireNarration(n,factoryRoot){
 if(!n||n.enabled!==true)return null;
 await narrationInputs(n);
 let receiptPath=n.receiptPath,audioPath=n.audioPath,mediaWorkspace=n.mediaWorkspace,expectedFingerprint;
 if(!receiptPath){
  if(n.authorize!==true||!n.requestPath||!n.authorizationPath||!mediaWorkspace)throw Error('Narration generation requires an explicit request, scoped authorization and authorize:true');
  await regular(n.requestPath);await regular(n.authorizationPath);
  const request=JSON.parse(await fs.readFile(n.requestPath,'utf8'));
  if(request.schema!=='videoops-media-request/v1'||request.capability!=='speech'||!/^[-A-Za-z0-9_.]{1,100}$/.test(request.request_id))throw Error('Only canonical bounded speech requests are accepted');
  const authority=JSON.parse(await fs.readFile(n.authorizationPath,'utf8'));
  if(path.resolve(authority.workspace)!==path.resolve(mediaWorkspace)||authority.authorization_id!==request.authorization_id)throw Error('Speech authority is not bound to this workspace/request');
  const bin=path.join(factoryRoot,'.runtime/venv/bin/videoops');
  expectedFingerprint=JSON.parse(run(bin,['media','fingerprint','--workspace',mediaWorkspace,'--request',n.requestPath],factoryRoot)).fingerprint;
  const existing=path.join(mediaWorkspace,'media',request.request_id,'result.json');
  let found=false;try{await fs.access(existing);found=true;}catch{}
  if(!found){run(bin,['media','authorize','--workspace',mediaWorkspace,'--authorization',n.authorizationPath,'--authorize-local'],factoryRoot);
  run(bin,['media','generate','--workspace',mediaWorkspace,'--request',n.requestPath],factoryRoot);}
  receiptPath=path.join(mediaWorkspace,'media',request.request_id,'result.json');
 }
 await regular(receiptPath);const receipt=JSON.parse(await fs.readFile(receiptPath,'utf8'));
 if(expectedFingerprint&&receipt.fingerprint!==expectedFingerprint)throw Error('Cached speech receipt belongs to another request');
 if(receipt.schema!=='videoops-media-result/v1'||receipt.state!=='SUCCESS'||!['speech','local_import'].includes(receipt.capability)||!['live','local'].includes(receipt.verification))throw Error('Narration needs a successful non-fixture canonical speech/import receipt');
 if(!mediaWorkspace)throw Error('Supply mediaWorkspace to verify canonical paths and originals');
 if(!receipt.original||!Array.isArray(receipt.derived))throw Error('Narration receipt lacks original/derivative evidence');
 for(const asset of [receipt.original,...receipt.derived]){
  const p=contained(mediaWorkspace,asset.path);await regular(p);if(await hash(p)!==asset.sha256)throw Error('Narration source or derivative drift');
 }
 audioPath=audioPath||contained(mediaWorkspace,receipt.derived.find(x=>x.path.endsWith('.wav'))?.path);
 await regular(audioPath);const actual=await hash(audioPath);
 if(n.sha256&&n.sha256!==actual)throw Error('Narration audio hash changed');
 if(![receipt.original,...receipt.derived].some(x=>x.sha256===actual&&path.resolve(contained(mediaWorkspace,x.path))===path.resolve(audioPath)))throw Error('Narration audio does not match the canonical receipt');
 const registry=JSON.parse(await fs.readFile(contained(mediaWorkspace,receipt.manifest_path),'utf8'));
 const asset=registry.assets.find(x=>x.id===receipt.asset_id&&x.requirement_id===receipt.requirement_id);
 if(!asset||asset.usage_status!=='approved')throw Error('Narration usage must be explicitly approved in its source registry');
 return {audioPath,receiptPath,sha256:actual,receiptSha256:await hash(receiptPath),originalPath:contained(mediaWorkspace,receipt.original.path),originalSha256:receipt.original.sha256,requestId:receipt.request_id,verification:receipt.verification,usage:receipt.usage,model:receipt.model,voice:receipt.voice,rights:receipt.rights,listening:'not_attested'};
}
