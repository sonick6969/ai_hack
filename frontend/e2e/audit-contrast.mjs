// Read-only visual audit against the isolated preview, never the user's database.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base=process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8012';
const output=path.resolve(import.meta.dirname,'../../artifacts/redesign');
fs.mkdirSync(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({locale:'ru-RU'});
const results=[];
for(const width of [1440,1280,390]) {
  await page.setViewportSize({width,height:1000});
  for(const section of ['queue','stock','imports','rules','audit','message','questions','parts','card']) {
    const tab=['message','questions','parts','card'].includes(section);
    await page.goto(tab?`${base}/?ticket=6`:section==='queue'?`${base}/`:`${base}/?section=${section}`);
    // Playwright baseURL is not configured for this stand-alone audit.
    if(tab && !page.url().startsWith(base)) throw new Error('Unexpected audit origin');
    await page.locator('.loading').waitFor({state:'hidden'});
    if(tab) await page.getByRole('tab',{name:({message:'Обращение',questions:'Уточнения',parts:'Детали',card:'Карточка'})[section],exact:true}).click();
    if(section==='card') await page.locator('.engineer-paper').waitFor();
    await page.evaluate(()=>document.fonts.ready);
    if(tab) await page.screenshot({path:path.join(output,`${section}-${width}.png`),fullPage:true});
    const audit=await page.evaluate(()=>{
      const parse=s=>{const values=s.match(/[\d.]+/g)?.map(Number);return values&&values.length>=3?[values[0],values[1],values[2],values[3]??1]:[0,0,0,0];};
      const over=(front,back)=>front.slice(0,3).map((v,i)=>v*front[3]+back[i]*(1-front[3]));
      const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((total,v,i)=>total+v*[.2126,.7152,.0722][i],0);
      const failures=[];let checked=0,min=99;
      for(const element of document.body.querySelectorAll('*')) {
        if(![...element.childNodes].some(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim()))continue;
        if(!element.getClientRects().length||element.closest('[aria-hidden="true"],[hidden],button:disabled,[disabled],svg,option'))continue;
        const style=getComputedStyle(element);
        if(style.visibility==='hidden'||style.opacity==='0')continue;
        const parents=[];for(let node=element;node;node=node.parentElement)parents.push(node);
        let background=[255,255,255];
        for(const parent of parents.reverse())background=over(parse(getComputedStyle(parent).backgroundColor),background);
        const color=over(parse(style.color),background),l1=luminance(color),l2=luminance(background);
        const ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);checked++;min=Math.min(min,ratio);
        if(ratio<4.49)failures.push({text:element.textContent.trim().slice(0,75),class:element.className,color:style.color,background,ratio:Number(ratio.toFixed(2))});
      }
      return {checked,min:Number(min.toFixed(2)),overflow:document.documentElement.scrollWidth>innerWidth,failures};
    });
    results.push({width,section,...audit});
  }
}
await browser.close();
fs.writeFileSync(path.join(output,'contrast-audit.json'),JSON.stringify(results,null,2));
const failures=results.filter(r=>r.failures.length||r.overflow);
console.log(JSON.stringify(failures.length?failures:{views:results.length,minimum:Math.min(...results.map(r=>r.min)),failures:0},null,2));
process.exitCode=failures.length?1:0;
