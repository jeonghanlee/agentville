"""Real bounded AV artwork composition and source-pixel terminal dimensions."""
import json
from pathlib import Path
import pytest
from tests.browser.test_seats import open_page
from tests.browser.paint_compare import capture_artwork, compare_artwork
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright=playwright_sync()
ANNOTATIONS=json.loads((Path(__file__).parents[2]/"docs/design/meeting-av-annotations.json").read_text())


@pytest.mark.parametrize("width",[1440,720])
def test_meeting_av_edits_stay_within_measured_regions(tmp_path,width):
    with HQ(tmp_path/"hq.sqlite3") as hq,playwright.sync_playwright() as driver:
        browser,page,errors=open_page(driver,hq.url+"/?demo=seats",width)
        playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        page.locator("#setting-daylight").select_option("day",force=True)
        page.add_style_tag(content="#characters,#characters *,.selection-outline{visibility:hidden!important}")
        parts=ANNOTATIONS["display_parts"]
        actual=page.evaluate("async()=>{const {ARTWORK_PATCHES}=await import('/layout.js');return ARTWORK_PATCHES.filter(p=>p.id.startsWith('av-')).map(({id,bounds})=>({id,bounds}))}")
        assert actual==parts
        for part in parts:
            playwright.expect(page.locator('.artwork-patch [data-artwork-edit="'+part["id"]+'"]')).to_have_count(1)
        edited,frame=capture_artwork(page)
        page.locator('[data-artwork-edit^="av-"]').evaluate_all("nodes=>nodes.forEach(n=>n.style.visibility='hidden')")
        original,final_frame=capture_artwork(page)
        assert frame==final_frame
        regions=[]
        for part in parts:
            x,y,width_source,height_source=part["bounds"]
            regions.append([[x,y],[x+width_source,y],[x+width_source,y+height_source],[x,y+height_source]])
        result=compare_artwork(page,edited,original,regions,frame)
        (tmp_path/"capture-frame.json").write_text(json.dumps(frame,indent=2)+"\n")
        (tmp_path/"av-pixels.json").write_text(json.dumps(result,indent=2)+"\n")
        if result["outside"]:
            (tmp_path/"edited.png").write_bytes(edited);(tmp_path/"original.png").write_bytes(original)
        assert result["outside"]==0 and all(n>5 for n in result["counts"]),result
        assert not errors
        browser.close()


def test_tabletop_touch_controllers_have_compact_source_dimensions(tmp_path):
    with HQ(tmp_path/"hq.sqlite3") as hq,playwright.sync_playwright() as driver:
        browser,page,errors=open_page(driver,hq.url+"/?demo=1")
        result=page.evaluate("""async parts=>{
          const image=new Image();image.src='/office-meeting-av.png';await image.decode();
          const c=document.createElement('canvas');c.width=1536;c.height=1024;const ctx=c.getContext('2d');ctx.drawImage(image,0,0);
          return parts.filter(p=>p.id.includes('controller')).map(p=>{
            const [x,y,w,h]=p.bounds,data=ctx.getImageData(x,y,w,h).data,points=[];
            for(let v=0;v<h;v++)for(let u=0;u<w;u++){const i=(v*w+u)*4;if(data[i+2]>data[i]+22&&data[i+2]>data[i+1]+8)points.push([u,v]);}
            return {id:p.id,pixels:points.length,width:points.length?Math.max(...points.map(p=>p[0]))-Math.min(...points.map(p=>p[0]))+1:0};
          });
        }""",ANNOTATIONS["display_parts"])
        assert len(result)==2 and all(row["pixels"]>10 and 0<row["width"]<=ANNOTATIONS["controller_width_limit_pixels"] for row in result),result
        (tmp_path/"av-source-dimensions.json").write_text(json.dumps(result,indent=2)+"\n")
        assert not errors
        browser.close()
