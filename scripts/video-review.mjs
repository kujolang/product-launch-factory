/** Separate tool-free critic call after narration changes the candidate hash. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [job,workspace,evidencePath,role='video-critic']=process.argv.slice(2);
if(!job||!workspace||!evidencePath)throw Error('Expected job, review workspace, evidence JSON');
await fs.mkdir(path.join(workspace,'planning'),{recursive:true});
const {propose}=await import(pathToFileURL(path.join(job,'src/agent.mjs')).href);
const {judgmentSchema}=await import(pathToFileURL(path.join(job,'src/contracts.mjs')).href);
const evidence=JSON.parse(await fs.readFile(evidencePath,'utf8'));
if(!['video-critic','media-generator'].includes(role))throw Error('Unsupported review role');
const evidenceHash=createHash('sha256').update(JSON.stringify(evidence)).digest('hex');
const binding=path.join(workspace,'evidence-binding.json');let cached;try{cached=JSON.parse(await fs.readFile(binding,'utf8'));}catch{}
if(cached&&cached.sha256!==evidenceHash)throw Error('Role review evidence changed during resume');
let result;if(cached){result=JSON.parse(await fs.readFile(path.join(workspace,'planning',role+'.json'),'utf8'));}else{result=await propose(role,`Role ${role}: review the exact technical handoff for a narrated launch candidate. Check the recorded source facts, duration, audio preservation and required review limits. You cannot hear or watch this text-only call. ACCEPT means technical handoff only; visual playback, pronunciation and listening remain REVIEW_INCOMPLETE. Do not imply publication or human approval. ${JSON.stringify(evidence)}`,judgmentSchema,workspace);await fs.writeFile(binding,JSON.stringify({sha256:evidenceHash}));}
if(result.decision!=='ACCEPT')throw Error('Independent narrated-candidate critic blocked: '+result.reason);
console.log(JSON.stringify(result));
