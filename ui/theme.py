"""
ui/theme.py
===========
Shared visual design: a realistic "campus" look.

Light stone background, navy + brass accents, soft physical shadows, serif
headings, and physically-lit Three.js scenes (campus building, timetable board).

  * inject_css()      - global stylesheet
  * page_header()     - plain editorial page heading
  * stat_cards()      - paper-card KPIs
  * pipeline_3d()     - compiler phase stepper
  * timetable_grid()  - weekly grid as HTML
  * hero_3d()         - 3D campus scene
  * timetable_3d()    - 3D timetable board
"""

from __future__ import annotations

import html
import re
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=JetBrains+Mono:wght@400;600&display=swap');
:root{
  --bg:#e4e7ea; --paper:#fbfbfa; --line:#cfd4d9; --ink:#1b2430; --mut:#5d6874;
  --navy:#1f3a5f; --brass:#a87b2a; --ok:#2f7d55; --bad:#b4403a;
  --shadow:0 1px 1px rgba(20,30,45,.08), 0 6px 14px -4px rgba(20,30,45,.16), 0 18px 32px -12px rgba(20,30,45,.18);
}
html, body, [class*="css"], .stApp{ font-family:'Inter',sans-serif; color:var(--ink); }
.stApp{ background:var(--bg); }
.block-container{ padding-top:1.2rem; max-width:1240px; }
h1,h2,h3,h4{ font-family:'Source Serif 4',serif; font-weight:600; letter-spacing:-.005em; color:var(--ink); }
header[data-testid="stHeader"]{ background:rgba(228,231,234,.92); backdrop-filter:blur(6px); border-bottom:1px solid var(--line); }

/* page heading */
.ph{ margin:6px 0 22px; padding-bottom:14px; border-bottom:1px solid var(--line); }
.ph .eyebrow{ font-size:.72rem; font-weight:600; letter-spacing:.14em; text-transform:uppercase; color:var(--brass); margin-bottom:4px;}
.ph h1{ font-family:'Source Serif 4',serif; font-size:2.05rem; font-weight:700; margin:0; padding:0; color:var(--ink);}
.ph p{ margin:.4rem 0 0; color:var(--mut); max-width:800px; font-size:.98rem;}

/* paper stat cards */
.stat-grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin:4px 0 18px;}
.stat{ background:var(--paper); border:1px solid var(--line); border-radius:6px; padding:16px 18px; box-shadow:var(--shadow);
  transition:transform .2s ease, box-shadow .2s ease; }
.stat:hover{ transform:translateY(-3px) rotateX(2deg); }
.stat .val{ font-family:'Source Serif 4',serif; font-size:2.3rem; font-weight:700; color:var(--navy); line-height:1.05;}
.stat .lab{ font-size:.72rem; color:var(--mut); text-transform:uppercase; letter-spacing:.12em; font-weight:600; margin-top:4px;}

/* stepper */
.pipe{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin:8px 0 22px;}
.node{ position:relative; background:var(--paper); border:1px solid var(--line); border-radius:6px; padding:14px 16px;
  box-shadow:var(--shadow); }
.node .n{ width:26px; height:26px; border-radius:50%; display:grid; place-items:center; font-weight:600; font-size:.8rem;
  background:var(--navy); color:#fff; margin-bottom:8px; box-shadow:inset 0 -2px 0 rgba(0,0,0,.25), 0 2px 4px rgba(0,0,0,.25);}
.node .t{ font-weight:600; font-size:.92rem; color:var(--ink);}
.node .d{ font-size:.76rem; color:var(--mut); margin-top:2px;}
.node .s{ margin-top:8px; font-size:.7rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase;}
.s-ok{color:var(--ok)} .s-bad{color:var(--bad)} .s-idle{color:var(--mut)}
.node.ok .n{ background:var(--ok);} .node.bad .n{ background:var(--bad);}
.node.idle .n{ background:#8a95a1; }

/* widgets */
div[data-testid="stMetric"]{ background:var(--paper); border:1px solid var(--line); padding:12px 14px; border-radius:6px; box-shadow:var(--shadow);}
.stButton>button, .stDownloadButton>button{ border-radius:6px; font-weight:500; border:1px solid #b9c0c7; background:linear-gradient(#fff,#eceff1); color:var(--ink);
  box-shadow:0 2px 0 #aab2ba, 0 4px 8px -2px rgba(20,30,45,.2); transition:transform .1s, box-shadow .1s;}
.stButton>button:hover, .stDownloadButton>button:hover{ border-color:var(--navy); color:var(--navy);}
.stButton>button:active, .stDownloadButton>button:active{ transform:translateY(2px); box-shadow:0 0 0 #aab2ba, 0 1px 2px rgba(20,30,45,.25);}
.stButton>button[kind="primary"]{ background:linear-gradient(#2c4f7c,#1f3a5f); color:#fff; border-color:#16294a; box-shadow:0 2px 0 #0f1f38, 0 5px 10px -2px rgba(20,30,45,.35);}
.stButton>button[kind="primary"]:hover{ color:#fff; filter:brightness(1.1);}
.stButton>button[kind="primary"]:active{ box-shadow:0 0 0 #0f1f38;}
button[data-baseweb="tab"]{ font-weight:500; }
div[data-baseweb="tab-highlight"]{ background:var(--brass); height:3px; }
textarea, input{ font-family:'JetBrains Mono',monospace !important; }
div[data-testid="stDataFrame"], div[data-testid="stCodeBlock"], div[data-testid="stExpander"]{
  border:1px solid var(--line); border-radius:6px; box-shadow:var(--shadow); overflow:hidden; background:var(--paper);}
div[data-testid="stAlert"]{ border-radius:6px; }
iframe{ border-radius:8px; box-shadow:var(--shadow); }

/* timetable grid */
.tt{ width:100%; border-collapse:separate; border-spacing:5px;}
.tt th{ padding:10px; border-radius:4px; font-size:.78rem; letter-spacing:.1em; text-transform:uppercase; color:#fff; background:var(--navy);
  box-shadow:0 2px 0 #0f1f38;}
.tt td.t{ font-weight:600; color:var(--mut); text-align:center; width:64px; font-size:.8rem;}
.tt td.c{ vertical-align:top; min-width:125px; height:62px; padding:4px; background:var(--paper); border:1px solid var(--line); border-radius:4px;}
.slot{ padding:7px 9px; border-radius:4px; margin-bottom:4px; color:#fff; font-size:.76rem; line-height:1.3; background:var(--a);
  box-shadow:0 2px 0 rgba(0,0,0,.3), 0 4px 6px -2px rgba(0,0,0,.3); transition:transform .15s;}
.slot:hover{ transform:translateY(-3px); }
.slot b{ font-size:.84rem;} .slot span{ opacity:.9; display:block; font-size:.7rem;}
</style>
"""

# muted, paint-like colours (fill, unused)
_PALETTE = [
    ("#2f5d8a", ""), ("#a8642a", ""), ("#4d7c59", ""), ("#8a3b3b", ""),
    ("#5b4b8a", ""), ("#2d7f87", ""), ("#8d7a2c", ""), ("#6b4f3a", ""),
]
_PALETTE_HEX = [0x2f5d8a, 0xa8642a, 0x4d7c59, 0x8a3b3b, 0x5b4b8a, 0x2d7f87, 0x8d7a2c, 0x6b4f3a]

_THREE = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"

_HERO_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;overflow:hidden;background:#cfd9e3;font-family:sans-serif}
#c{width:100%;height:100%;display:block;cursor:grab}
.cap{position:absolute;left:14px;bottom:10px;color:#2b3a4a;font-size:12px;opacity:.75}
</style></head><body><canvas id="c"></canvas><div class="cap">Drag to look around · scroll to zoom</div>
<script src="__THREE__"></script><script>
const cv=document.getElementById('c');
const R=new THREE.WebGLRenderer({canvas:cv,antialias:true});R.setPixelRatio(Math.min(devicePixelRatio,2));
R.shadowMap.enabled=true;R.shadowMap.type=THREE.PCFSoftShadowMap;
const S=new THREE.Scene();S.background=new THREE.Color(0xbcd3e8);S.fog=new THREE.Fog(0xbcd3e8,30,70);
const C=new THREE.PerspectiveCamera(42,1,.1,200);
S.add(new THREE.HemisphereLight(0xdfeaff,0x6b6a55,.8));
const sun=new THREE.DirectionalLight(0xfff1d6,1.15);sun.position.set(14,20,10);sun.castShadow=true;
sun.shadow.mapSize.set(2048,2048);const sc=sun.shadow.camera;sc.left=-25;sc.right=25;sc.top=25;sc.bottom=-25;sc.far=70;S.add(sun);
function mat(c,r=.85,m=0){return new THREE.MeshStandardMaterial({color:c,roughness:r,metalness:m})}
function box(w,h,d,m,x,y,z,cast=true){const b=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m);b.position.set(x,y,z);b.castShadow=cast;b.receiveShadow=true;S.add(b);return b}
// ground, lawn, path
const ground=new THREE.Mesh(new THREE.PlaneGeometry(120,120),mat(0x7d9a5e,1));ground.rotation.x=-Math.PI/2;ground.receiveShadow=true;S.add(ground);
box(3.2,.06,18,mat(0xc9c2b2,.95),0,.03,9,false);
box(22,.06,3,mat(0xc9c2b2,.95),0,.03,4.5,false);
// facade texture with windows
function facade(w,h,cols,rows,base){const c=document.createElement('canvas');c.width=512;c.height=256;const g=c.getContext('2d');
 g.fillStyle=base;g.fillRect(0,0,512,256);
 for(let i=0;i<cols;i++)for(let j=0;j<rows;j++){const x=(i+.5)*512/cols-14,y=(j+.5)*256/rows-17;
  g.fillStyle='#6c7b8a';g.fillRect(x-2,y-2,32,38);g.fillStyle='#9fb8cc';g.fillRect(x,y,28,34);
  g.fillStyle='rgba(255,255,255,.35)';g.fillRect(x,y,28,10);g.fillStyle='#6c7b8a';g.fillRect(x+13,y,2,34);}
 const t=new THREE.CanvasTexture(c);t.anisotropy=4;return t}
const brick=0xa65d45,stone=0xd8d2c2;
function wing(w,h,d,x,z,col,cols){const tex=facade(w,h,cols,3,'#'+col.toString(16).padStart(6,'0'));
 const side=mat(col);const front=new THREE.MeshStandardMaterial({map:tex,roughness:.85});
 const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),[side,side,side,side,front,front]);m.position.set(x,h/2,z);m.castShadow=m.receiveShadow=true;S.add(m);
 box(w+.4,.35,d+.4,mat(stone),x,h+.17,z)}
wing(9,6,5,-7.5,-2,brick,8);wing(9,6,5,7.5,-2,brick,8);wing(6,8,5.4,0,-2,0xb86a50,5);
// entrance portico with columns
box(7,.3,2.6,mat(stone),0,3.4,1.4);
for(let i=-3;i<=3;i+=1.5){const cl=new THREE.Mesh(new THREE.CylinderGeometry(.22,.26,3.3,20),mat(0xeeeadf,.6));cl.position.set(i,1.65,2.2);cl.castShadow=true;S.add(cl)}
box(7.4,.5,3,mat(stone),0,3.75+.0,1.4);
const ped=new THREE.Mesh(new THREE.ConeGeometry(3.9,1.2,4),mat(stone));ped.rotation.y=Math.PI/4;ped.scale.set(1,1,.42);ped.position.set(0,4.6,1.4);ped.castShadow=true;S.add(ped);
for(let s=0;s<4;s++)box(7.6-s*.2,.15,3.4+s*.4-1.2,mat(0xcfc9ba),0,.08+s*.15,3.2+s*.0+ (3-s)*.1,false);
// clock tower
box(2,4.2,2,mat(0xb86a50),0,10,-2);box(2.5,.4,2.5,mat(stone),0,12.3,-2);
const roof=new THREE.Mesh(new THREE.ConeGeometry(1.6,2.2,4),mat(0x3d5a73,.6,.2));roof.rotation.y=Math.PI/4;roof.position.set(0,13.6,-2);roof.castShadow=true;S.add(roof);
const clk=new THREE.Mesh(new THREE.CircleGeometry(.6,32),mat(0xf4f1e8,.5));clk.position.set(0,10.6,-.98);S.add(clk);
const hand=box(.06,.42,.03,mat(0x222222),0,10.75,-.95,false);
// trees
function tree(x,z,s){const tr=new THREE.Mesh(new THREE.CylinderGeometry(.14*s,.2*s,1.4*s,8),mat(0x5b4333));tr.position.set(x,.7*s,z);tr.castShadow=true;S.add(tr);
 for(let i=0;i<3;i++){const l=new THREE.Mesh(new THREE.IcosahedronGeometry((1.1-i*.2)*s,1),mat(i?0x4f7a3f:0x3f6b35,.95));l.position.set(x+(i-1)*.2*s,(1.8+i*.7)*s,z);l.castShadow=true;S.add(l)}}
[[-12,4],[-12,10],[12,4],[12,10],[-5.5,13],[5.5,13],[-16,-3],[16,-3],[-9,16],[9,16]].forEach((p,i)=>tree(p[0],p[1],1+(i%3)*.15));
// lamp posts
[-2.2,2.2].forEach(x=>[8,13].forEach(z=>{box(.08,2,.08,mat(0x333a40,.4,.6),x,1,z);const b=new THREE.Mesh(new THREE.SphereGeometry(.16,12,12),new THREE.MeshStandardMaterial({color:0xfff2c8,emissive:0xffe9a8,emissiveIntensity:.6}));b.position.set(x,2.1,z);S.add(b)}));
let ry=.5,rx=.3,dist=34,drag=false,lx=0,ly=0;
cv.addEventListener('pointerdown',e=>{drag=true;lx=e.clientX;ly=e.clientY;cv.style.cursor='grabbing'});
addEventListener('pointerup',()=>{drag=false;cv.style.cursor='grab'});
addEventListener('pointermove',e=>{if(drag){ry-=(e.clientX-lx)*.006;rx=Math.max(.08,Math.min(1.1,rx+(e.clientY-ly)*.004));lx=e.clientX;ly=e.clientY}});
cv.addEventListener('wheel',e=>{e.preventDefault();dist=Math.max(16,Math.min(52,dist+e.deltaY*.03))},{passive:false});
function fit(){const w=cv.clientWidth,h=cv.clientHeight;R.setSize(w,h,false);C.aspect=w/h;C.updateProjectionMatrix()}
addEventListener('resize',fit);fit();
(function loop(t){requestAnimationFrame(loop);if(!drag)ry+=.0012;
 C.position.set(Math.sin(ry)*Math.cos(rx)*dist,Math.sin(rx)*dist+3,Math.cos(ry)*Math.cos(rx)*dist+4);C.lookAt(0,4,2);R.render(S,C)})(0);
</script></body></html>""".replace("__THREE__", _THREE)

_TT3D_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#d9dde1;overflow:hidden;font-family:sans-serif}
#c{width:100%;height:100%;display:block;cursor:grab}
#tip{position:absolute;pointer-events:none;padding:8px 12px;border-radius:4px;background:#fbfbfa;color:#1b2430;font-size:13px;border:1px solid #b9c0c7;box-shadow:0 6px 14px rgba(0,0,0,.25);display:none}
.cap{position:absolute;left:14px;bottom:10px;color:#3a4552;font-size:12px}
</style></head><body><canvas id="c"></canvas><div id="tip"></div>
<div class="cap">Drag to rotate · scroll to zoom · hover a block for details</div>
<script src="__THREE__"></script><script>
const D=__DATA__, DAYS=__DAYS__, TIMES=__TIMES__, COL=__COLS__;
const cv=document.getElementById('c'),tip=document.getElementById('tip');
const R=new THREE.WebGLRenderer({canvas:cv,antialias:true});R.setPixelRatio(Math.min(devicePixelRatio,2));
R.shadowMap.enabled=true;R.shadowMap.type=THREE.PCFSoftShadowMap;R.setClearColor(0xd9dde1);
const S=new THREE.Scene();S.fog=new THREE.Fog(0xd9dde1,26,60);
const C=new THREE.PerspectiveCamera(42,1,.1,100);
S.add(new THREE.HemisphereLight(0xffffff,0x8a8f95,.85));
const sun=new THREE.DirectionalLight(0xfff4e0,1.1);sun.position.set(8,14,6);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);
const sc=sun.shadow.camera;sc.left=-14;sc.right=14;sc.top=14;sc.bottom=-14;sc.far=50;S.add(sun);
const W=DAYS.length,H=TIMES.length,CELL=1.25;
// wooden desk with printed grid
const bw=W*CELL+1.6,bd=H*CELL+1.6;
function deskTex(){const c=document.createElement('canvas');c.width=1024;c.height=1024;const g=c.getContext('2d');
 g.fillStyle='#8a6a48';g.fillRect(0,0,1024,1024);
 for(let i=0;i<260;i++){g.strokeStyle='rgba('+(60+Math.random()*40)+','+(40+Math.random()*30)+',20,'+(.05+Math.random()*.1)+')';g.lineWidth=1+Math.random()*2;
  const y=Math.random()*1024;g.beginPath();g.moveTo(0,y);g.bezierCurveTo(300,y+Math.random()*14-7,700,y+Math.random()*14-7,1024,y+Math.random()*10-5);g.stroke()}
 const t=new THREE.CanvasTexture(c);return t}
const desk=new THREE.Mesh(new THREE.BoxGeometry(bw+1,.5,bd+1),new THREE.MeshStandardMaterial({map:deskTex(),roughness:.6}));
desk.position.y=-.25;desk.receiveShadow=true;S.add(desk);
// paper planner sheet
function sheetTex(){const c=document.createElement('canvas');c.width=1024;c.height=1024;const g=c.getContext('2d');
 g.fillStyle='#f6f4ee';g.fillRect(0,0,1024,1024);g.strokeStyle='#c4c0b4';g.lineWidth=2;
 const cw=1024/ (W+1), ch=1024/(H+1);
 for(let i=0;i<=W+1;i++){g.beginPath();g.moveTo(i*cw,0);g.lineTo(i*cw,1024);g.stroke()}
 for(let j=0;j<=H+1;j++){g.beginPath();g.moveTo(0,j*ch);g.lineTo(1024,j*ch);g.stroke()}
 g.fillStyle='#2a3340';g.font='bold 26px sans-serif';g.textAlign='center';
 DAYS.forEach((d,i)=>g.fillText(d.slice(0,3),(i+1.5)*cw,ch*.62));
 TIMES.forEach((t,j)=>g.fillText(t,cw*.5,(j+1.5)*ch+9));
 return new THREE.CanvasTexture(c)}
const sheet=new THREE.Mesh(new THREE.BoxGeometry(bw,.05,bd),new THREE.MeshStandardMaterial({map:sheetTex(),roughness:.95}));
sheet.position.y=.025;sheet.receiveShadow=true;S.add(sheet);
// blocks (wooden-core painted tiles with course label on top)
const ids=[...new Set(D.map(d=>d.c))],meshes=[],stack={};
function topTex(d,col){const c=document.createElement('canvas');c.width=256;c.height=256;const g=c.getContext('2d');
 g.fillStyle='#'+col.toString(16).padStart(6,'0');g.fillRect(0,0,256,256);g.fillStyle='rgba(255,255,255,.1)';g.fillRect(0,0,256,10);
 g.fillStyle='#fff';g.textAlign='center';g.font='bold 54px sans-serif';g.fillText(d.c,128,118);
 g.font='36px sans-serif';g.globalAlpha=.9;g.fillText(d.r,128,172);g.font='26px sans-serif';g.fillText(String(d.tn).slice(0,12),128,214);
 return new THREE.CanvasTexture(c)}
D.forEach(d=>{const i=DAYS.indexOf(d.d),j=TIMES.indexOf(d.t);if(i<0||j<0)return;
 const k=i+'_'+j,lvl=stack[k]=(stack[k]||0)+1,col=COL[ids.indexOf(d.c)%COL.length],h=.35+(d.dur||1)*.3;
 const side=new THREE.MeshStandardMaterial({color:col,roughness:.55,metalness:.05});
 const top=new THREE.MeshStandardMaterial({map:topTex(d,col),roughness:.5});
 const m=new THREE.Mesh(new THREE.BoxGeometry(1.0,h,1.0),[side,side,top,side,side,side]);
 const x=(-(W-1)/2+i)*CELL,z=(-(H-1)/2+j)*CELL;
 m.position.set(x,.05+(lvl-1)*(h+.02)+h/2,z);m.castShadow=m.receiveShadow=true;m.userData={d:d,y:m.position.y};S.add(m);meshes.push(m)});
let ry=-.5,rx=.8,dist=Math.max(W,H)*1.7+6,drag=false,lx=0,ly=0,mx=-1,my=-1;
cv.addEventListener('pointerdown',e=>{drag=true;lx=e.clientX;ly=e.clientY;cv.style.cursor='grabbing'});
addEventListener('pointerup',()=>{drag=false;cv.style.cursor='grab'});
addEventListener('pointermove',e=>{if(drag){ry-=(e.clientX-lx)*.007;rx=Math.max(.2,Math.min(1.45,rx+(e.clientY-ly)*.006));lx=e.clientX;ly=e.clientY}mx=e.clientX;my=e.clientY});
cv.addEventListener('wheel',e=>{e.preventDefault();dist=Math.max(6,Math.min(36,dist+e.deltaY*.02))},{passive:false});
const ray=new THREE.Raycaster(),v=new THREE.Vector2();let hov=null;
function fit(){const w=cv.clientWidth,h=cv.clientHeight;R.setSize(w,h,false);C.aspect=w/h;C.updateProjectionMatrix()}
addEventListener('resize',fit);fit();
(function loop(){requestAnimationFrame(loop);
 C.position.set(Math.sin(ry)*Math.cos(rx)*dist,Math.sin(rx)*dist,Math.cos(ry)*Math.cos(rx)*dist);C.lookAt(0,0,0);
 const r=cv.getBoundingClientRect();v.set(((mx-r.left)/r.width)*2-1,-((my-r.top)/r.height)*2+1);ray.setFromCamera(v,C);
 const hit=ray.intersectObjects(meshes)[0];hov=hit?hit.object:null;
 meshes.forEach(m=>{const up=m===hov?.18:0;m.position.y+=(m.userData.y+up-m.position.y)*.25});
 if(hov&&!drag){const d=hov.userData.d;tip.style.display='block';tip.style.left=(mx-r.left+14)+'px';tip.style.top=(my-r.top+14)+'px';
  tip.innerHTML='<b>'+d.c+'</b><br>'+d.d+', '+d.t+'<br>Room '+d.r+'<br>'+d.tn}else tip.style.display='none';
 R.render(S,C)})();
</script></body></html>"""


_EMOJI = re.compile(r"^[^\w(]+\s*")


def inject_css() -> None:
    """Inject the global stylesheet. Call once per run from app.py."""
    st.html(_CSS)


def page_header(title: str, subtitle: str = "", tag: str = "") -> None:
    """Plain editorial page heading (leading emoji in titles are dropped)."""
    title = _EMOJI.sub("", title)
    eyebrow = f'<div class="eyebrow">{html.escape(tag)}</div>' if tag else ""
    st.html(
        f'<div class="ph">{eyebrow}<h1>{html.escape(title)}</h1>'
        f'<p>{html.escape(subtitle)}</p></div>'
    )


def stat_cards(items: list[tuple]) -> None:
    """items: (icon, label, value, ...); icon and colours are ignored in this design."""
    cards = "".join(
        f'<div class="stat"><div class="val">{value}</div><div class="lab">{html.escape(label)}</div></div>'
        for _icon, label, value, *_ in items
    )
    st.html(f'<div class="stat-grid">{cards}</div>')


def pipeline_3d(states: list[tuple[str, str, str, str]]) -> None:
    """states: (title, description, status['ok'|'bad'|'idle'], status_label)."""
    nodes = ""
    for i, (title, desc, status, label) in enumerate(states, 1):
        nodes += (
            f'<div class="node {status}">'
            f'<div class="n">{i}</div><div class="t">{html.escape(title)}</div>'
            f'<div class="d">{html.escape(desc)}</div>'
            f'<div class="s s-{status}">{html.escape(label)}</div></div>'
        )
    st.html(f'<div class="pipe">{nodes}</div>')


def timetable_grid(entries: list[dict], days: list[str], times: list[str]) -> None:
    """Weekly timetable as HTML; one paint colour per course."""
    courses = sorted({e["course_id"] for e in entries})
    color = {c: _PALETTE[i % len(_PALETTE)][0] for i, c in enumerate(courses)}
    cell: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        cell.setdefault((e["time_slot"], e["day"]), []).append(e)

    head = "<tr><th></th>" + "".join(f"<th>{html.escape(d[:3])}</th>" for d in days) + "</tr>"
    rows = ""
    for t in times:
        tds = ""
        for d in days:
            blocks = ""
            for e in cell.get((t, d), []):
                blocks += (
                    f'<div class="slot" style="--a:{color[e["course_id"]]}"><b>{html.escape(e["course_id"])}</b>'
                    f'<span>{html.escape(e["room_id"])} · {html.escape(e["teacher_name"])}</span></div>'
                )
            tds += f'<td class="c">{blocks}</td>'
        rows += f'<tr><td class="t">{html.escape(t)}</td>{tds}</tr>'
    st.html(f'<table class="tt">{head}{rows}</table>')


def hero_3d(height: int = 430) -> None:
    """Lit 3D campus scene (Three.js, shadows, physically based materials)."""
    st.iframe(_HERO_HTML, height=height, alt="Interactive 3D model of a university campus")


def timetable_3d(entries: list[dict], days: list[str], times: list[str], height: int = 600) -> None:
    """3D planner: painted blocks standing on a printed sheet on a wooden desk."""
    import json
    data = [
        {"c": e["course_id"], "d": e["day"], "t": e["time_slot"], "r": e["room_id"],
         "tn": e["teacher_name"], "dur": int(e.get("duration") or 1)}
        for e in entries
    ]
    page = (_TT3D_HTML.replace("__THREE__", _THREE)
            .replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
            .replace("__DAYS__", json.dumps(days))
            .replace("__TIMES__", json.dumps(times))
            .replace("__COLS__", json.dumps(_PALETTE_HEX)))
    st.iframe(page, height=height, alt="Interactive 3D weekly timetable")
