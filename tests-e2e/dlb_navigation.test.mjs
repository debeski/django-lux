import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import {chromium} from 'playwright';
const web=new URL('../tools/dlb-viewer/web/',import.meta.url);

test('Slow model responses cannot replace a newer selection or overview',async()=>{
 const server=http.createServer((req,res)=>{
  const file=req.url==='/'?'index.html':req.url.replace('/static/','');
  res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html');
  res.end(fs.readFileSync(new URL(file,web)));
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch();
 try {
  for(const width of [1440,390]) {
   const page=await browser.newPage({viewport:{width,height:800}});
   const errors=[];page.on('pageerror',err=>errors.push(err.message));
   let finish;
   await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    let data={loaded:true,unlocked:true,meta:{encryption:{scheme:'none'}},manifest:{models:[{model:'sample.slow',count:50},{model:'sample.fast',count:50}],files:[]}};
    if(url.pathname==='/api/model') {
     const key=url.searchParams.get('key');
     if(key==='sample.slow') await new Promise(r=>finish=r);
     data={key,total:50,offset:0,limit:50,records:[{pk:1,fields:{title:key}}]};
    }
    await route.fulfill({json:data});
   });
   await page.goto(`http://127.0.0.1:${server.address().port}`);
   const requestPromise=page.waitForRequest('**/api/model?*');
   await page.locator('[data-model="sample.slow"]').click();
   await requestPromise;
   await page.locator('[data-model="sample.fast"]').click();
   await page.waitForFunction(()=>document.querySelector('#content table')!==null);
   const responsePromise=page.waitForResponse(r=>r.url().includes('/api/model?key=sample.slow'));
   finish();
   await responsePromise;
   await page.waitForFunction(()=>document.querySelector('#content h2').textContent==='sample.fast');
   const secondRequest=page.waitForRequest('**/api/model?*');
   await page.locator('[data-model="sample.slow"]').click();
   await secondRequest;
   await page.locator('[data-view="overview"]').click();
   const secondResponse=page.waitForResponse(r=>r.url().includes('/api/model?key=sample.slow'));
   finish();
   await secondResponse;
   assert.equal(await page.locator('#content h2').textContent(),'Backup overview');
   assert.deepEqual(errors,[]);await page.close();
  }
 } finally {await browser.close();await new Promise(r=>server.close(r));}
});
