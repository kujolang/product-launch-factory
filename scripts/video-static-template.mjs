/** Static product evidence profile around the pinned factory's trusted compiler. */
import {compileTemplate as compileOriginal} from './template-original.mjs';
export function compileTemplate(plan,assets){
  const files=compileOriginal(plan,assets);
  for(const [name,html] of Object.entries(files)){
    if(!name.startsWith('compositions/'))continue;
    const animations=html.match(/^tl\.fromTo\([^\n]+\);$/gm)||[];
    if(animations.length!==1)throw Error('Unsupported upstream template animation shape');
    files[name]=html.replace(animations[0],'// Static evidence: visible from the first frame.');
  }
  return files;
}
