/** Check the hydrated GitHub player, including playback and seeking. No listening claim. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium,webkit}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const manifest=JSON.parse(await fs.readFile(process.argv[2]||'docs/media/product-launch-demo/manifest.json','utf8'));
const duration=manifest.duration;const results=[];
for(const [name,engine,launch,context] of [
 ['Chrome desktop',chromium,{channel:'chrome'},{viewport:{width:1440,height:1000}}],
 ['WebKit phone emulation',webkit,{},{viewport:{width:390,height:844},isMobile:true,hasTouch:true}]
]){
 const browser=await engine.launch({headless:true,...launch});
 try{
  const page=await browser.newPage(context);
  await page.goto('https://github.com/kujolang/product-launch-factory',{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('video').first().waitFor({state:'attached',timeout:30000});
  await page.waitForTimeout(5000);
  await page.locator('video').first().evaluate(el=>{const d=el.closest('details');if(d)d.open=true});
  await page.waitForTimeout(1500);
  const video=page.locator('video').first();await video.waitFor({state:'visible'});await video.scrollIntoViewIfNeeded();await page.bringToFront();
  await video.evaluate(el=>el.muted=true);await video.click();await video.evaluate(el=>el.play());
  await page.waitForFunction(()=>document.querySelector('video')?.currentTime>.2,{},{timeout:30000});
  const initial=await video.evaluate(el=>({duration:el.duration,time:el.currentTime,width:el.videoWidth,height:el.videoHeight,error:el.error?.message||null}));
  assert(Math.abs(initial.duration-duration)<.2);assert.equal(initial.width,1920);assert.equal(initial.error,null);
  const seekAt=duration-4;await video.evaluate((el,t)=>{el.currentTime=t},seekAt);
  await page.waitForFunction(t=>document.querySelector('video')?.currentTime>t+.2,seekAt,{timeout:15000});
  const seek=await video.evaluate(el=>({time:el.currentTime,error:el.error?.message||null}));assert.equal(seek.error,null);
  results.push({name,...initial,seek});console.log(name+' passed');
 }finally{await browser.close()}
}
await fs.writeFile(process.argv[3]||'docs/media/product-launch-demo/readme-playback.json',JSON.stringify({ok:true,results,listening:'not_attested',phone:'emulation, not physical device'},null,2)+'\n');
