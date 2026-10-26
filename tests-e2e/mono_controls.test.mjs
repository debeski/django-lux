import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dlux/static');
const server=http.createServer((req,res)=>{
 const file=path.join(root,decodeURIComponent(req.url));
 if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type','text/css');res.end(fs.readFileSync(file));
});
function contrast(fg,bg){
 const lum=s=>{const c=s.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
 const a=lum(fg),b=lum(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
test('Mono header controls retain contrast and disclosure links have no clipping border',async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch();
 try {
  for(const lang of ['en','ar'])for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:600}}),base='http://127.0.0.1:'+server.address().port;
   await page.setContent(`<html class="theme-mono" dir="${lang==='ar'?'rtl':'ltr'}"><head>${['bootstrap/bootstrap.min.css','dlux/base/css/buttons.css','dlux/table_columns/css/main.css','dlux/themes/css/mono.css'].map(p=>`<link rel="stylesheet" href="${base}/${p}">`).join('')}</head><body><div class="dlux-table-columns"><div class="dlux-table-columns__headers"><div class="dlux-table-columns__header"><button class="btn btn-sm dlux-table-columns__handle">${lang==='ar'?'رقم المستند':'Reference number'}</button><button class="btn btn-sm px-1" data-column-move="-1">‹</button></div></div></div><button class="btn btn-link btn-sm px-0" data-disclosure>${lang==='ar'?'عرض المزيد':'Show all (6)'}</button></body></html>`);
   await page.waitForLoadState('networkidle');
   for(const selector of ['.dlux-table-columns__handle','[data-column-move]']){
    const b=page.locator(selector);
    for(const state of ['normal','hover','focus']){
     if(state==='hover')await b.hover();if(state==='focus')await b.focus();
     const style=await b.evaluate(n=>{const s=getComputedStyle(n);return {color:s.color,bg:s.backgroundColor};});
     assert.ok(contrast(style.color,style.bg)>=4.5,JSON.stringify({lang,width,state,...style}));
    }
   }
   const border=await page.locator('[data-disclosure]').evaluate(n=>getComputedStyle(n).borderTopWidth);assert.equal(border,'0px');await page.close();
  }
 }finally{await browser.close();await new Promise(r=>server.close(r));}
});
