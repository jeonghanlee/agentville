"""Single-floor routes checked against independent pixel annotations in Chromium."""

import json
from pathlib import Path

import pytest

from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
ANNOTATIONS = Path(__file__).parent / "fixtures" / "unified-image-annotations.json"


@pytest.fixture(scope="module")
def geometry(tmp_path_factory):
    annotations = json.loads(ANNOTATIONS.read_text())
    with HQ(tmp_path_factory.mktemp("floor-clearance") / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.goto(hq.url + "/favicon.svg")
        value = page.evaluate("""async data => {
          const scene = await import('/floor.js');
          const {SEATS,seatFoot} = await import('/seats.js');
          const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
          document.documentElement.append(svg);
          const polygon = points => {
            const node = document.createElementNS(svg.namespaceURI,'polygon');
            node.setAttribute('points',points.map(p=>p.join(',')).join(' '));svg.append(node);return node;
          };
          const slab = polygon(data.floor), contacts = Object.entries(data.contacts).map(([id,points])=>[id,polygon(points),points]);
          const inside = (p,shape) => shape.isPointInFill(new DOMPoint(...p));
          const turn = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
          const crosses = (a,b,c,d) => turn(a,b,c)*turn(a,b,d)<0 && turn(c,d,a)*turn(c,d,b)<0;
          const hull = points => {
            points.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);const lower=[],upper=[];
            for(const p of points){while(lower.length>1&&turn(lower.at(-2),lower.at(-1),p)<=0)lower.pop();lower.push(p);}
            for(const p of [...points].reverse()){while(upper.length>1&&turn(upper.at(-2),upper.at(-1),p)<=0)upper.pop();upper.push(p);}
            return lower.slice(0,-1).concat(upper.slice(0,-1));
          };
          // Pixel dimensions retain the contract independently of production feet() and footprint tables.
          const foot = (p,half) => {const x=p[0]*15.36,y=p[1]*10.24;
            return [[x-half,y-7.168],[x+half,y-7.168],[x+half,y+1.536],[x-half,y+1.536]];};
          const failures=[], checked=new Set();
          const check = (a,b,own=[],wide=true) => {
            const key=JSON.stringify([a,b,own,wide]);if(checked.has(key))return;checked.add(key);
            const swept=hull([...foot(a,wide?23:20.736),...foot(b,wide?23:20.736)]);
            const edges=swept.map((p,i)=>[p,swept[(i+1)%swept.length]]);
            if(swept.some(p=>!inside(p,slab)) || edges.some(([a,b])=>data.floor.some((c,i)=>crosses(a,b,c,data.floor[(i+1)%data.floor.length]))))
              failures.push({kind:'slab',a,b});
            const shape=polygon(swept);
            for(const [id,node,points] of contacts) {
              if(own.includes(id))continue;
              if(swept.some(p=>inside(p,node)) || points.some(p=>inside(p,shape))
                || edges.some(([a,b])=>points.some((c,i)=>crosses(a,b,c,points[(i+1)%points.length]))))
                failures.push({kind:'contact',id,a,b});
            }
            shape.remove();
          };
          for(const [a,b] of scene.LINKS) check(scene.NODES[a],scene.NODES[b]);
          let routes=0;
          for(const a of Object.values(scene.NODES)) for(const b of Object.values(scene.NODES)) {
            const path=scene.route(a,b);routes++;
            for(let i=1;i<path.length;i++)check(path[i-1],path[i]);
          }
          for(const seat of SEATS) {
            const side=scene.NODES[seat.approach];check(side,side);
            if(seat.facing!=='lying')check(side,seatFoot(seat),seat.footprints,false);
          }
          const first=Object.keys(scene.NODES)[0],seen=new Set([first]),open=[first];
          while(open.length)for(const id of scene.neighbourIds(open.shift()))if(!seen.has(id)){seen.add(id);open.push(id);}
          svg.remove();return {failures,routes,segments:checked.size,nodes:Object.keys(scene.NODES).length,connected:seen.size,
            foot:scene.FOOT,seats:SEATS.map(s=>({id:s.id,scene:s.scene,desk:Boolean(s.workstation),facing:s.facing}))};
        }""", annotations)
        browser.close()
        return value


def test_graph_and_every_route_keep_46_pixel_clearance(geometry):
    assert geometry["connected"] == geometry["nodes"]
    assert geometry["routes"] == geometry["nodes"] ** 2
    assert geometry["segments"] > geometry["nodes"]
    assert not geometry["failures"], geometry["failures"][:20]
    assert geometry["foot"] == {"half": 1.35, "back": .7, "front": .15}


def test_single_floor_has_twenty_desks_and_ten_facility_seats(geometry):
    seats = geometry["seats"]
    assert len(seats) == 30
    assert {seat["scene"] for seat in seats} == {"main"}
    expected = {"studio0": 6, "studio1": 6, "studio2": 4, "studio3": 2, "common": 2, "meeting": 6, "fika": 3, "infirmary": 1}
    for room, count in expected.items():
        assert [seat["id"] for seat in seats if seat["id"].startswith(room + ".")] == [f"{room}.{i}" for i in range(count)]
    assert sum(seat["desk"] for seat in seats) == 20
