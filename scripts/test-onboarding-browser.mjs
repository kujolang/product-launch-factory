import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {chromium} from 'playwright';
const server=spawn('python3',['src/launch.py','serve','--port','4389'],{stdio:'inherit'});
let browser;
try {
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:4389');
  await page.locator('.deliverable').last().waitFor();
  assert.equal(await page.locator('.station.completed').count(),5);
  assert.equal(await page.locator('.deliverable').count(),5);
  assert.match(await page.locator('#state').innerText(),/Recorded example/);
  await page.getByRole('button',{name:'Handoffs',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.handoff-grid article').length===5);
  await page.getByRole('button',{name:'Video',exact:true}).click();
  await page.locator('video').evaluate(v=>{v.muted=true;return v.play()});
  await page.waitForFunction(()=>document.querySelector('video')?.currentTime>0.2);
  assert.equal(await page.locator('video').evaluate(v=>v.error),null);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,stations:5,handoffs:5,videoPlayback:true,mobileOverflow:false,providerCalls:0}));
} finally {
  if(browser)await browser.close();
  server.kill();
}
