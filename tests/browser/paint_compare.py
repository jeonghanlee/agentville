"""Native screenshot comparisons in the displayed SVG's actual source coordinates."""
import base64
import math
import time

# A single 8-bit channel step accommodates native compositing quantization.
CHANNEL_TOLERANCE = 1


def capture_artwork(page):
    world=page.locator("#world")
    world.scroll_into_view_if_needed()
    page.evaluate("document.fonts.ready.then(()=>true)")
    page.evaluate("""()=>Promise.all([...new Set([...document.querySelectorAll('#world image')].map(n=>n.href.baseVal))].map(async url=>{const image=new Image();image.src=url;await image.decode();}))""")
    page.add_style_tag(content="#world,#world *{transition:none!important;animation:none!important}")
    page.evaluate("""()=>{const node=document.querySelector('#world'),r=node.getBoundingClientRect(),d=devicePixelRatio;node.style.left=(parseFloat(node.style.left)||0)+(Math.round(r.left*d)/d-r.left)+'px';node.style.top=(parseFloat(node.style.top)||0)+(Math.round(r.top*d)/d-r.top)+'px';}""")
    time.sleep(.8)
    frame=page.evaluate("""()=>{const node=document.querySelector('.presentation-layer'),m=node.getScreenCTM(),r=document.querySelector('#world').getBoundingClientRect();return {box:[r.left+scrollX,r.top+scrollY,r.width,r.height],matrix:[m.a,m.b,m.c,m.d,m.e+scrollX,m.f+scrollY],dpr:devicePixelRatio}}""")
    x,y,width,height=frame["box"]
    clip={"x":math.floor(x),"y":math.floor(y),"width":math.ceil(x+width)-math.floor(x),"height":math.ceil(y+height)-math.floor(y)}
    frame["clip"]=clip
    return page.screenshot(clip=clip,animations="disabled"),frame


def compare_artwork(page,before,after,regions,frame):
    return page.evaluate("""async({before,after,regions,frame,tolerance})=>{
      const decode=async t=>createImageBitmap(new Blob([Uint8Array.from(atob(t),c=>c.charCodeAt(0))]));
      const [first,last]=await Promise.all([decode(before),decode(after)]),canvas=document.createElement('canvas');
      if(first.width!==last.width||first.height!==last.height)throw new Error('Capture dimensions changed');
      canvas.width=first.width;canvas.height=first.height;const ctx=canvas.getContext('2d');
      ctx.drawImage(first,0,0);const a=ctx.getImageData(0,0,first.width,first.height).data;
      ctx.clearRect(0,0,first.width,first.height);ctx.drawImage(last,0,0);const b=ctx.getImageData(0,0,first.width,first.height).data;
      const transform=new DOMMatrix(frame.matrix),inverse=transform.inverse(),scale=Math.min(Math.hypot(transform.a,transform.b),Math.hypot(transform.c,transform.d));
      const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.style.cssText='width:0;height:0;position:absolute';document.body.append(svg);
      const shapes=regions.map(points=>{const p=document.createElementNS(ns,'polygon');p.setAttribute('points',points.map(v=>v.join(',')).join(' '));p.setAttribute('stroke-width',3/scale);svg.append(p);return p;});
      const counts=regions.map(()=>0);let inside=0,outside=0,rawOutside=0,maximumOutside=0;
      for(let y=0;y<first.height;y++)for(let x=0;x<first.width;x++){
        const i=(y*first.width+x)*4,delta=Math.max(...[0,1,2,3].map(c=>Math.abs(a[i+c]-b[i+c])));if(!delta)continue;
        const point=new DOMPoint(frame.clip.x+(x+.5)/frame.dpr,frame.clip.y+(y+.5)/frame.dpr).matrixTransform(inverse);
        const index=shapes.findIndex(p=>p.isPointInFill(point)||p.isPointInStroke(point));
        if(index>=0){inside++;counts[index]++;}else{rawOutside++;maximumOutside=Math.max(maximumOutside,delta);if(delta>tolerance)outside++;}
      }
      svg.remove();first.close();last.close();return {inside,counts,outside,rawOutside,maximumOutside,tolerance};
    }""",{"before":base64.b64encode(before).decode(),"after":base64.b64encode(after).decode(),"regions":regions,"frame":frame,"tolerance":CHANNEL_TOLERANCE})
