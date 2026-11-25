import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dlux/static');
const themes=fs.readdirSync(path.join(root,'dlux/themes/css')).filter(f=>f.endsWith('.css')&&f!=='previews.css').map(f=>f.slice(0,-4));
const server=http.createServer((req,res)=>{
 const file=path.join(root,decodeURIComponent(req.url));
 if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type','text/css');res.end(fs.readFileSync(file));
});
const shells={
 public:{css:['bootstrap/bootstrap.min.css','dlux/public/css/public_base.css'],body:'dlux-public'},
 staff:{css:['bootstrap/bootstrap.min.css','dlux/base/css/main.css','dlux/base/css/buttons.css'],body:''},
};
function colours(value,under=[255,255,255]){
 const out=[],over=(c,a)=>c.map((v,i)=>v*a+under[i]*(1-a));
 for(const m of value.matchAll(/rgba?\(([^)]+)\)/g)){const p=m[1].split(/[ ,/]+/).filter(Boolean).map(Number);const a=p.length>3?p[3]:1;if(a>0)out.push(over(p.slice(0,3),a));}
 for(const m of value.matchAll(/color\(srgb ([^)]+)\)/g)){const p=m[1].split(/[ /]+/).filter(Boolean).map(Number);const a=p.length>3?p[3]:1;if(a>0)out.push(over(p.slice(0,3).map(v=>v*255),a));}
 return out;
}
function contrast(a,b){
 const lum=c=>{const l=c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return l[0]*.2126+l[1]*.7152+l[2]*.0722;};
 const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}

test('Text on accent-filled controls meets WCAG AA in every theme, both shells, LTR and RTL',async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch();
 const base='http://127.0.0.1:'+server.address().port,failures=[];
 try {
  for(const [shell,{css,body}] of Object.entries(shells))for(const theme of themes)for(const dir of ['ltr','rtl']){
   const page=await browser.newPage();
   const links=[...css.slice(0,1),...(shell==='staff'?css.slice(1):[]),`dlux/themes/css/${theme}.css`,...(shell==='public'?css.slice(1):[])];
   await page.setContent(`<html class="theme-${theme}" dir="${dir}"><head>${links.map(p=>`<link rel="stylesheet" href="${base}/${p}">`).join('')}</head><body class="${body}"><button class="btn btn-primary" data-probe data-hover>${dir==='rtl'?'تطبيق':'Apply'}</button>${shell==='public'?'<ul class="nav nav-pills"><li class="nav-item"><a class="nav-link active" data-probe href="#">All</a></li></ul><ul class="pagination"><li class="page-item active"><a class="page-link" data-probe href="#">2</a></li></ul><div class="list-group"><a class="list-group-item active" data-probe href="#">Item</a></div><span class="badge text-bg-primary" data-probe>3</span>':''}</body></html>`);
   await page.waitForLoadState('networkidle');
   await page.addStyleTag({content:'*,*::before,*::after{transition:none!important;animation:none!important}'});
   const probes=page.locator('[data-probe]');
   for(let i=0;i<await probes.count();i++){
    const probe=probes.nth(i);
    const hoverable=await probe.evaluate(n=>n.hasAttribute('data-hover'));
    for(const state of hoverable?['normal','hover']:['normal']){
     if(state==='hover')await probe.hover();
     const s=await probe.evaluate(n=>{const f=getComputedStyle(n.closest('[data-fill]')||n),c=getComputedStyle(n);return {cls:(n.closest('[data-fill]')||n).className,color:c.color,bg:f.backgroundColor,img:f.backgroundImage,page:getComputedStyle(document.body).backgroundColor};});
     const under=colours(s.page)[0]||[255,255,255],fg=colours(s.color,under)[0],fills=[...colours(s.bg,under),...colours(s.img,under)];
     if(!fills.length){failures.push({shell,theme,dir,state,...s,reason:'no fill'});continue;}
     const worst=Math.min(...fills.map(f=>contrast(fg,f)));
     if(worst<4.5)failures.push({shell,theme,dir,state,cls:s.cls,color:s.color,bg:s.bg,img:s.img.slice(0,120),ratio:worst.toFixed(2)});
    }
   }
   await page.close();
  }
 }finally{await browser.close();await new Promise(r=>server.close(r));}
 assert.deepEqual(failures,[],JSON.stringify(failures,null,1));
});
