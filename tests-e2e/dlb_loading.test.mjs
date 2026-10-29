import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import {chromium} from 'playwright';

const web = new URL('../tools/dlb-viewer/web/', import.meta.url);
const encrypted = {loaded:true, unlocked:false, source:'sample.dlb', meta:{encryption:{scheme:'fernet'}}};
const plain = {...encrypted, meta:{encryption:{scheme:'none'}}};
const ready = {...plain, unlocked:true, manifest:{models:[], files:[]}};

test('DLB loading remains visible through open/unlock, blocks duplicates, and recovers from errors', async () => {
  const server = http.createServer((req,res) => {
    const file = req.url === '/' ? 'index.html' : req.url.replace('/static/','');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(fs.readFileSync(new URL(file,web)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch();
  try {
    for (const width of [1440,390]) {
      const page=await browser.newPage({viewport:{width,height:800}});
      const errors=[]; page.on('pageerror',e=>errors.push(e.message));
      let opens=0, unlocks=0, mode='plain', fail=false, initial=false;
      await page.route('**/api/**', async route=>{
        const url=new URL(route.request().url());
        let data={loaded:false};
        if(url.pathname==='/api/state') data=initial?plain:data;
        if(url.pathname.startsWith('/api/open-')) {
          opens++;
          await new Promise(r=>setTimeout(r,250));
          if(fail) return route.fulfill({status:400,json:{error:'Invalid backup'}});
          data=mode==='plain'?plain:encrypted;
        }
        if(url.pathname==='/api/unlock') {
          unlocks++;
          await new Promise(r=>setTimeout(r,350));
          if(fail) return route.fulfill({status:401,json:{error:'Incorrect password'}});
          data=ready;
        }
        await route.fulfill({json:data});
      });
      const base=`http://127.0.0.1:${server.address().port}`;
      await page.goto(base);
      await page.locator('.path-open summary').click();
      await page.locator('#path-input').fill('/backup.dlb');
      await page.locator('#path-btn').click();
      await page.waitForFunction(()=>!document.querySelector('#loading').hidden);
      assert.equal(await page.locator('#app').evaluate(n=>n.inert),true);
      await page.evaluate(()=>document.querySelector('#path-btn').click());
      await page.waitForFunction(()=>document.querySelector('#loading-label').textContent.includes('merging'));
      await page.waitForFunction(()=>!document.querySelector('#screen-browse').hidden && document.querySelector('#loading').hidden);
      assert.equal(opens,1);assert.equal(unlocks,1);
      assert.equal(await page.locator('#app').evaluate(n=>n.inert),false);

      await page.reload(); mode='encrypted';
      await page.locator('#file-input').setInputFiles({name:'large.dlb',mimeType:'application/octet-stream',buffer:Buffer.alloc(2*1024*1024)});
      await page.waitForFunction(()=>!document.querySelector('#loading').hidden);
      await page.waitForFunction(()=>!document.querySelector('#screen-unlock').hidden && document.querySelector('#loading').hidden);
      fail=true;
      await page.locator('#password-input').fill('wrong');
      await page.locator('#unlock-btn').click();
      await page.waitForFunction(()=>!document.querySelector('#loading').hidden);
      await page.waitForFunction(()=>!document.querySelector('#unlock-error').hidden && document.querySelector('#loading').hidden);
      assert.equal(await page.locator('#unlock-error').textContent(),'Incorrect password');
      fail=false;
      await page.locator('#unlock-btn').click();
      await page.waitForFunction(()=>!document.querySelector('#screen-browse').hidden && document.querySelector('#loading').hidden);

      await page.reload();fail=true;
      await page.locator('.path-open summary').click();
      await page.locator('#path-input').fill('/bad.dlb');
      await page.locator('#path-btn').click();
      await page.waitForFunction(()=>!document.querySelector('#open-error').hidden && document.querySelector('#loading').hidden);
      assert.equal(await page.locator('#open-error').textContent(),'Invalid backup');
      fail=false;initial=true;
      await page.reload();
      await page.waitForFunction(()=>!document.querySelector('#loading').hidden);
      const box=await page.locator('.loading-card').boundingBox();
      assert.ok(box.x>=0 && box.x+box.width<=width);
      await page.waitForFunction(()=>!document.querySelector('#screen-browse').hidden && document.querySelector('#loading').hidden);
      assert.deepEqual(errors,[]);
      await page.close();
    }
  } finally {await browser.close();await new Promise(r=>server.close(r));}
});
