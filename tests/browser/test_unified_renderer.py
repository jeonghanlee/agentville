"""Actual renderer targets against image annotations at the accepted actor scale."""

import json
from pathlib import Path

import pytest

from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
ANNOTATIONS = Path(__file__).parent / "fixtures" / "unified-image-annotations.json"

HTML = """<!doctype html><html><link rel="stylesheet" href="/app.css">
<style>body{margin:0}#world{position:relative;aspect-ratio:3/2}.agent *{animation:none!important;transition:none!important}</style>
<div id="world"></div></html>"""

MEASURE = """async data => {
  const {character,prepareAppearances}=await import('/art.js');
  const {applyLayoutMetrics}=await import('/layout.js');
  const world=document.querySelector('#world');
  world.style.width='100%';applyLayoutMetrics(world);
  const desks=data.seats.filter(seat=>seat.workstation);
  const seeds=Array.from({length:12},(_,i)=>'target-'+i);prepareAppearances(seeds);
  const records=[];
  for(const seat of desks) for(const facing of ['front','back','front-right','back-left']) {
    const node=document.createElement('div');node.className='agent seated';node.dataset.seatFacing=facing;
    const position=[seat.anchor[0]/15.36,seat.anchor[1]/10.24,facing];
    Object.assign(node.style,{left:position[0]+'%',top:position[1]+'%',width:data.actor_width_percent+'%'});
    const sprite=character(seeds[records.length%12],'working','','normal',false,facing,{seat:position,keys:seat.workstation});
    node.append(sprite);world.append(node);
    const arms=[...sprite.querySelectorAll('path[stroke-width="2.3"]')];
    const ends=arms.map(arm=>arm.getPointAtLength(arm.getTotalLength()));
    const mouse=new DOMPoint(ends[1].x+parseFloat(sprite.style.getPropertyValue('--mouse-x')),
      ends[1].y+parseFloat(sprite.style.getPropertyValue('--mouse-y')));
    const actual=[ends[0],ends[1],mouse].map((p,i)=>{
      const q=new DOMPoint(p.x,p.y).matrixTransform(arms[Math.min(i,1)].getScreenCTM());return [q.x,q.y];
    });
    const bounds=world.getBoundingClientRect();
    const expected=seat.workstation.map(([x,y])=>[bounds.x+x/1536*bounds.width,bounds.y+y/1024*bounds.height]);
    records.push({seat:seat.id,facing,actual,expected});
  }
  return records;
}"""


@pytest.mark.parametrize("width", [1440, 720])
def test_working_hands_follow_measured_actor_scale(tmp_path, width):
    data = json.loads(ANNOTATIONS.read_text())
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page(viewport={"width": width, "height": 1100}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/renderer-targets", lambda route: route.fulfill(body=HTML, content_type="text/html"))
        page.goto(hq.url + "/renderer-targets")
        records = page.evaluate(MEASURE, data)
        assert not errors
        browser.close()
    assert len(records) == 80
    for record in records:
        for actual, expected in zip(record["actual"], record["expected"]):
            assert max(abs(a - b) for a, b in zip(actual, expected)) < 1, record


def test_walking_sole_contact_strips_fit_the_retained_foot_envelope(tmp_path):
    annotations = json.loads(ANNOTATIONS.read_text())
    html = HTML.replace(".agent *{animation:none!important;transition:none!important}", ".agent{transition:none!important}")
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/walking-contacts", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto(hq.url + "/walking-contacts")
        rows = page.evaluate("""async patches => {
          const {character,prepareAppearances}=await import('/art.js');
          const {applyLayoutMetrics}=await import('/layout.js');
          const world=document.querySelector('#world');world.style.width='1536px';applyLayoutMetrics(world);
          const seeds=Array.from({length:12},(_,i)=>'sole-'+i);prepareAppearances(seeds);const rows=[];
          for(const seed of seeds)for(const view of ['front','back'])for(const facing of ['left','right'])for(let phase=0;phase<16;phase++){
            const index=rows.length,x=index%16*80+40,y=Math.floor(index/16)*110+92;
            const node=document.createElement('div');node.className='agent coffee-standing walking';
            node.dataset.walkView=view;node.dataset.coffeeFacing=facing;
            Object.assign(node.style,{left:x+'px',top:y+'px'});
            const sprite=character(seed,'idle','coffee-walk','normal',false,'walking');node.append(sprite);world.append(node);
            rows.push({node,view,facing,phase,x,y,look:Number(sprite.dataset.look)});
          }
          await new Promise(requestAnimationFrame);
          for(const row of rows){
            row.node.style.setProperty('--walk-phase',String(row.phase/16));
            for(const animation of row.node.getAnimations({subtree:true})){
              animation.pause();animation.currentTime=0;
            }
          }
          await new Promise(requestAnimationFrame);
          const origin=world.getBoundingClientRect();
          return rows.map(({node,view,facing,phase,x,y,look})=>{
            const points=[];
            // Every actual animated copy bounds the independently annotated contact strips conservatively.
            for(const image of node.querySelectorAll('.walk-'+view+' image'))for(const [px,py,w,h] of patches[view][look%6])
              for(const [u,v] of [[px,py],[px+w,py],[px+w,py+h],[px,py+h]]){
                const p=new DOMPoint(u,v).matrixTransform(image.getScreenCTM());points.push([p.x-origin.x-x,p.y-origin.y-y]);
              }
            return {look,view,facing,phase,points,
              bounds:[Math.min(...points.map(p=>p[0])),Math.max(...points.map(p=>p[0])),
                Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[1]))]};
          });
        }""", annotations["sole_patches"])
        assert not errors
        browser.close()
    assert len(rows) == 768 and len({row["look"] for row in rows}) == 12
    for row in rows:
        assert row["points"], row
    outside = [row for row in rows if not all(
        -20.736 <= x <= 20.736 and -7.168 <= y <= 1.536 for x, y in row["points"])]
    assert not outside, [(row["look"], row["view"], row["facing"], row["phase"], row["bounds"])
                         for row in outside[:5]]
