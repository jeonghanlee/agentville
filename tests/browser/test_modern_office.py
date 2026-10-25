"""Calibrated poses, distinct meeting Projects and real entrance arrivals."""
import json
import re
from pathlib import Path

from tests.browser.test_seats import open_page, placements, roster
from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
ANNOTATIONS = json.loads((Path(__file__).parent / "fixtures/modern-image-annotations.json").read_text())


def test_every_seat_supports_all_twelve_appearances(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page(viewport={"width":1536,"height":1024}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        html = '<!doctype html><html><link rel="stylesheet" href="/app.css"><body style="margin:0"><div id="world" style="position:relative;width:1536px;height:1024px"></div></body></html>'
        page.route("**/_calibrated-poses", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto(hq.url + "/_calibrated-poses")
        result = page.evaluate("""async annotations => {
          const {SEATS}=await import('/seats.js');
          const {character,prepareAppearances}=await import('/art.js');
          const {seatedCharacter,seatedWorkstation,applySeatedMetrics}=await import('/seated.js');
          const seeds=Array.from({length:12},(_,i)=>'pose-'+i),looks=new Set(),hands=[],sizes=[];
          prepareAppearances(seeds);const world=document.getElementById('world');
          for(const seat of SEATS)for(const seed of seeds){
            const native=character(seed,seat.workstation?'working':'idle','','normal',false,seat.facing,seatedWorkstation(seat));
            looks.add(native.dataset.look);const sprite=seatedCharacter(native,seat),node=document.createElement('div');
            node.className='agent seated';node.style.left=seat.position[0]+'%';node.style.top=seat.position[1]+'%';
            node.append(sprite);world.append(node);applySeatedMetrics(node,seat);
            const bounds=node.getBoundingClientRect();sizes.push([bounds.width,bounds.height]);
            const target=annotations.seats.find(item=>item.id===seat.id),upper=node.querySelector('.employee-sprite');
            if(target.workstation)for(const [index,reach]of [...upper.querySelectorAll('.keyboard-reach')].entries()){
              const rect=upper.querySelector('clipPath[id$="-'+(index?'right':'left')+'"] rect');
              const p=new DOMPoint(Number(rect.getAttribute('x'))+Number(rect.getAttribute('width'))/2,
                Number(rect.getAttribute('y'))+Number(rect.getAttribute('height'))/2).matrixTransform(reach.getScreenCTM());
              hands.push(Math.hypot(p.x-target.workstation[index][0],p.y-target.workstation[index][1]));
            }
            node.remove();
          }
          return {looks:[...looks],sizes,handChecks:hands.length,maximumHandError:Math.max(...hands)};
        }""", ANNOTATIONS)
        assert len(result["looks"]) == 12
        assert len(result["sizes"]) == 720
        assert all(width > 0 and height > 0 for width, height in result["sizes"])
        assert result["handChecks"] == 480 and result["maximumHandError"] < .02
        assert not errors
        browser.close()


def test_two_rooms_keep_distinct_projects_and_independent_exit_clocks(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.goto(hq.url + "/favicon.svg")
        result = page.evaluate("""async () => {
          const {observe,createObservations,meetingsInRooms}=await import('/meeting.js');
          const rooms=[{id:'meeting',capacity:6},{id:'meeting-east',capacity:6}];
          let rows=[...Array.from({length:7},(_,i)=>['a'+i,'alpha','working']),
            ...Array.from({length:2},(_,i)=>['b'+i,'bravo','working']),
            ...Array.from({length:4},(_,i)=>['c'+i,'charlie','working'])];
          let observations=createObservations(),previous={};const records=[];
          const step=(at,{restart=false,closed=[]}={})=>{
            const state={branches:[{branch_id:'b1'}],agents:rows.map(([agent_id,project_id])=>({branch_id:'b1',agent_id,project_id,presence:'on_duty'})),
              activities:rows.map(([agent_id,,state])=>({branch_id:'b1',agent_id,state}))};
            observations=observe(observations,state,at*1000,{restart});
            previous=meetingsInRooms(state,observations,previous,at*1000,'live',closed,rooms);
            records.push(previous.b1.map(meeting=>({room:meeting.room,project:meeting.project_id,count:meeting.members.length})));
          };
          step(0);step(60);
          rows=rows.map(([id,project,state])=>[id,project,project==='alpha'?'waiting':state]);step(61);
          rows=rows.map(([id,project,state])=>[id,project,project==='alpha'?'working':state]);step(62);
          step(122);step(123,{restart:true});
          rows=rows.map(([id,project,state])=>[id,project,project==='bravo'?'idle':state]);step(124);step(153.9);step(154);
          step(183);step(184,{closed:[{kind:'project',id:'charlie',closed:true}]});
          return records;
        }""")
        assert result[0] == []
        assert result[1] == [{"room":"meeting","project":"alpha","count":6}, {"room":"meeting-east","project":"charlie","count":4}]
        assert result[2] == [{"room":"meeting","project":"bravo","count":2}, {"room":"meeting-east","project":"charlie","count":4}]
        assert result[3:8] == [result[2]] * 5
        assert result[8] == [{"room":"meeting-east","project":"charlie","count":4}]
        assert result[9] == [{"room":"meeting","project":"alpha","count":6}, {"room":"meeting-east","project":"charlie","count":4}]
        assert result[10] == [{"room":"meeting","project":"alpha","count":6}]
        browser.close()


def test_live_arrival_walks_from_front_entrance_to_a_free_desk(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 1)])
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, motion="no-preference")
        playwright.expect(page.locator("#characters .agent")).to_have_count(1)
        page.clock.pause_at(page.evaluate("Date.now() / 1000 + 1"))
        before = placements(page)[0]
        hq.advance(); hq.send(payload=roster(hq, [("alpha", 2)]))
        newcomer = page.locator('#characters .agent[data-employee-key=\'["b1","alpha-1"]\']')
        playwright.expect(newcomer).to_have_class(re.compile(r"\bwalking\b"))
        entry = page.evaluate("async () => (await import('/office-layout.js')).ENTRANCE")
        position = newcomer.evaluate("node=>[parseFloat(node.style.left),parseFloat(node.style.top)]")
        assert max(abs(a-b) for a,b in zip(position, entry)) < .001
        page.clock.run_for(30000)
        playwright.expect(newcomer).to_have_class(re.compile(r"\bseated\b"))
        after = placements(page)
        assert len({(row["room"],row["index"]) for row in after}) == 2
        assert next(row for row in after if row["key"] == before["key"])["index"] == before["index"]
        assert not errors
        browser.close()
