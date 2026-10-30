"""Verify tabletop touch-controller dimensions in the office image."""
import json
from pathlib import Path
from tests.browser.test_seats import open_page
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright=playwright_sync()
ANNOTATIONS=json.loads((Path(__file__).parents[2]/"docs/design/meeting-av-annotations.json").read_text())


def test_tabletop_touch_controllers_have_compact_source_dimensions(tmp_path):
    with HQ(tmp_path/"hq.sqlite3") as hq,playwright.sync_playwright() as driver:
        browser,page,errors=open_page(driver,hq.url+"/?demo=1")
        result=page.evaluate("""async parts=>{
          const image=new Image();image.src='/office-modern.png';await image.decode();
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
