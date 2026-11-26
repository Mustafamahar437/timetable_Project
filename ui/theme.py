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
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{ --bg:#090b0f; --panel:#14171b; --line:#252a31; --fg:#e9ecf0; --mut:#8b929c; --acc:#2dd4bf; --code:#0e1115; --ok:#34d399; --bad:#f87171; }
html, body, [class*="css"], .stApp{ font-family:'Outfit',system-ui,sans-serif; color:var(--fg); }
.stApp{ background:
  radial-gradient(ellipse at 50% 0%, rgba(45,212,191,.10), transparent 55%),
  radial-gradient(ellipse at 100% 100%, rgba(139,92,246,.08), transparent 50%), var(--bg); }
/* full screen width, clear of the top menu bar (!important beats Streamlit's own rules) */
.stApp [data-testid="stMainBlockContainer"], .stApp .block-container{ padding:4.5rem 1rem 2rem !important; max-width:100% !important; }
/* the 3D phase map always fits the visible screen */
.st-key-phasemap iframe{ height:calc(100vh - 6rem) !important; height:calc(100dvh - 6rem) !important; min-height:380px; }
.st-key-phasemap [data-testid="stElementContainer"]{ height:auto !important; }
h1,h2,h3,h4{ font-family:'Outfit',sans-serif; font-weight:600; color:var(--fg); }
header[data-testid="stHeader"]{ background:rgba(9,11,15,.85); backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }

.ph{ margin:8px 0 22px; display:flex; gap:16px; align-items:center; }
.ph .logo{ flex:none; width:46px; height:46px; border:1px solid #1d4a47; background:#0f2523; border-radius:12px; display:grid; place-items:center; color:var(--acc); font-size:20px; }
.ph .eyebrow{ font-size:.7rem; font-weight:600; letter-spacing:.16em; text-transform:uppercase; color:var(--acc); }
.ph h1{ font-size:1.7rem; font-weight:600; margin:0; padding:0; color:var(--fg); line-height:1.15; }
.ph p{ margin:.3rem 0 0; color:var(--mut); max-width:780px; font-size:.95rem; line-height:1.5; }

.stat-grid{ display:flex; flex-wrap:wrap; gap:12px; margin:18px 0 8px; }
.stat{ flex:1 1 150px; padding:14px 18px; background:var(--panel); border:1px solid var(--line); border-radius:14px; }
.stat .val{ font-size:2rem; font-weight:600; color:var(--acc); line-height:1; }
.stat .lab{ font-size:.72rem; color:var(--mut); text-transform:uppercase; letter-spacing:.14em; margin-top:8px; }

.pipe{ display:none; }
.ph .logo{ font-weight:700; font-size:1.2rem; box-shadow:0 8px 24px -8px rgba(0,0,0,.7); }
.ph .phtxt{ flex:1; min-width:0; }
.stepper{ flex:none; display:flex; align-items:center; padding:8px 12px; background:rgba(20,23,27,.85); border:1px solid var(--line); border-radius:18px; }
.sd{ width:26px; height:26px; border-radius:50%; display:grid; place-items:center; font:600 .72rem Outfit,sans-serif; color:#fff; background:var(--c); opacity:.55; flex:none; }
.sd.ok{ opacity:.95; } .sd.bad{ background:#b91c1c; opacity:1; }
.sd.on{ opacity:1; width:32px; height:32px; box-shadow:0 0 0 2px #090b0f, 0 0 0 4px var(--pc), 0 0 16px var(--pc); }
.sl{ width:8px; height:2px; background:#3a424d; flex:none; }
@media(max-width:900px){ .ph{ flex-wrap:wrap; } .stepper{ order:3; } }

div[data-testid="stMetric"]{ background:var(--panel); border:1px solid var(--line); padding:12px 16px; border-radius:12px; }
.stButton>button, .stDownloadButton>button{ border-radius:10px; font-weight:500; border:1px solid var(--line); background:#181d24; color:var(--fg); }
.stButton>button:hover, .stDownloadButton>button:hover{ border-color:var(--acc); color:var(--acc); background:#10201f; }
.stButton>button[kind="primary"]{ background:#0f2f2c; color:#5eead4; border-color:#1d6b64; }
.stButton>button[kind="primary"]:hover{ background:#14403c; color:#99f6e4; }
div[data-baseweb="tab-highlight"]{ background:var(--acc); height:2px; }
textarea, input{ font-family:'JetBrains Mono',monospace !important; }
div[data-baseweb="textarea"], div[data-baseweb="input"], div[data-baseweb="select"]>div{ border-radius:10px !important; }
div[data-testid="stDataFrame"], div[data-testid="stCodeBlock"], div[data-testid="stExpander"]{ border:1px solid var(--line); border-radius:12px; background:var(--panel); overflow:hidden; }
div[data-testid="stAlert"]{ border-radius:12px; }
iframe{ border:1px solid var(--line); border-radius:16px; }

.tt{ width:100%; border-collapse:separate; border-spacing:6px; }
.tt th{ padding:10px; font-size:.74rem; letter-spacing:.14em; text-transform:uppercase; color:#5eead4; background:#0f2523; border:1px solid #1d4a47; border-radius:10px; }
.tt td.t{ font-weight:500; color:var(--mut); width:60px; font-size:.78rem; text-align:center; }
.tt td.c{ vertical-align:top; min-width:125px; height:56px; padding:5px; background:var(--panel); border:1px solid var(--line); border-radius:10px; }
.slot{ padding:6px 9px; margin-bottom:4px; font-size:.75rem; line-height:1.3; color:#fff; border-radius:8px; background:var(--a); }
.slot b{ font-size:.82rem; } .slot span{ display:block; font-size:.7rem; opacity:.85; }
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


_PIPE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#090b0f;--panel:#14171b;--line:#252a31;--fg:#e9ecf0;--mut:#8b929c;--acc:#2dd4bf;--ph:#2dd4bf}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font-family:Outfit,system-ui,sans-serif;overflow:hidden}
#app{position:relative;height:100%;overflow:hidden}
#app:before{content:"";position:absolute;inset:0;pointer-events:none;transition:background .8s;
 background:radial-gradient(ellipse at 45% 45%,color-mix(in srgb,var(--ph) 22%,transparent),transparent 60%),radial-gradient(ellipse at 8% 100%,color-mix(in srgb,var(--ph) 14%,transparent),transparent 50%)}
canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab;touch-action:none}
.brand{position:absolute;top:18px;left:18px;display:flex;gap:12px;align-items:center;pointer-events:none}
.logo{width:42px;height:42px;border:1px solid #1d4a47;background:#0f2523;border-radius:11px;display:grid;place-items:center;color:var(--ph)}
.brand h1{margin:0;font-size:20px;font-weight:600}.brand span{font-size:13px;color:var(--mut)}
.hint{position:absolute;top:18px;right:18px;display:flex;gap:10px;align-items:center;font-size:14px;color:var(--mut)}
.hint b{color:var(--ph);font-weight:500}
.pill{height:38px;padding:0 14px;border-radius:10px;border:1px solid var(--line);background:#14171b;color:var(--fg);font:500 13px Outfit;display:flex;align-items:center;gap:8px}
.panel{position:absolute;right:18px;top:70px;bottom:78px;width:min(370px,calc(100% - 30px));background:rgba(16,19,24,.88);backdrop-filter:blur(14px);
 border:1px solid var(--line);border-top:3px solid var(--ph);border-radius:16px;padding:16px 20px;overflow:auto;box-shadow:0 20px 60px #0008;transition:transform .35s,opacity .35s}
.panel.off{transform:translateX(30px);opacity:0;pointer-events:none}
.x{position:absolute;top:14px;right:14px;width:30px;height:30px;border-radius:50%;border:0;background:#20252c;color:var(--mut);font-size:16px;cursor:pointer}
.lab{font:600 11px Outfit;letter-spacing:.16em;text-transform:uppercase;color:var(--ph)}
.panel h2{margin:8px 0 2px;font-size:21px;font-weight:600}
.sub{font:13px "JetBrains Mono",monospace;color:var(--mut)}
.badge{display:inline-block;margin-top:12px;padding:3px 10px;border-radius:99px;font:600 11px Outfit;letter-spacing:.1em;text-transform:uppercase}
.b-ok{background:#0f2f22;color:#34d399;border:1px solid #1d6b46}.b-bad{background:#34171a;color:#f87171;border:1px solid #6b2a30}.b-idle{background:#1b2027;color:#8b929c;border:1px solid #2a313a}
.panel p{color:#d3d7dd;line-height:1.55;margin:14px 0;font-size:14.5px}
h4{margin:18px 0 8px;font-size:12px;font-weight:500;letter-spacing:.14em;color:var(--mut);text-transform:uppercase;display:flex;gap:10px;align-items:center}
h4:after{content:"";flex:1;height:1px;background:var(--line)}
ul{margin:0;padding-left:18px;color:#c3c8cf;font-size:14px;line-height:1.6}
.steps{position:absolute;left:50%;bottom:16px;transform:translateX(-50%);display:flex;align-items:center;padding:9px 13px;background:rgba(16,19,24,.85);backdrop-filter:blur(12px);border:1px solid var(--line);border-radius:20px;max-width:calc(100% - 20px)}
.steps button{width:32px;height:32px;border-radius:50%;border:0;color:#fff;font:600 13px Outfit;cursor:pointer;flex:none;opacity:.8;transition:all .2s}
.steps button.on{width:38px;height:38px;opacity:1;box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--ph),0 0 18px var(--ph)}
.steps u{display:block;width:12px;height:2px;background:#3a424d;flex:none}
.ctl{position:absolute;left:18px;bottom:16px;padding:10px 14px;border:1px solid var(--line);background:rgba(16,19,24,.85);border-radius:11px;font-size:13px;color:var(--mut)}
.ctl b{color:var(--fg);font-weight:600}
.nm{position:absolute;left:50%;bottom:62px;transform:translateX(-50%);font:600 11px Outfit;letter-spacing:.16em;text-transform:uppercase;color:var(--ph);pointer-events:none;white-space:nowrap}
@media(max-width:760px){.ctl,.hint .pill{display:none}.panel{top:auto;left:12px;right:12px;width:auto;bottom:74px;max-height:52%}}
</style></head><body><div id="app">
<canvas id="c"></canvas>
<div class="brand"><div class="logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 18 6-6-6-6M8 6l-6 6 6 6M14 4l-4 16"/></svg></div><div><h1>Timetable Compiler</h1><span>Interactive 3D phase map</span></div></div>
<div class="hint"><span><b>Click a phase</b> to explore</span><div class="pill" id="sum"></div></div>
<aside class="panel off" id="panel"></aside>
<div class="nm" id="nm"></div>
<nav class="steps" id="steps"></nav>
<div class="ctl"><b>Controls:</b> Drag to rotate • Scroll to zoom</div>
</div>
<script src="__THREE__"></script><script>
const PH=__DATA__;const N=PH.length;
const cv=document.getElementById('c'),app=document.getElementById('app');
const R=new THREE.WebGLRenderer({canvas:cv,antialias:true,alpha:true});R.setPixelRatio(Math.min(devicePixelRatio,2));
const S=new THREE.Scene(),C=new THREE.PerspectiveCamera(50,1,.1,200);
const G=new THREE.Group();S.add(G);
// layout: two rows, snake
const GX=4.7,GY=2.15;
PH.forEach((p,i)=>{const row=i<4?0:1,col=row?7-i:i;p.x=(col-1.5)*GX;p.y=row?-GY:GY;p.z=0});
function shade(h,f){const n=parseInt(h.slice(1),16);return '#'+[16,8,0].map(s=>Math.round(((n>>s)&255)*f).toString(16).padStart(2,'0')).join('')}
function lite(h,f){const n=parseInt(h.slice(1),16);return '#'+[16,8,0].map(s=>Math.round(((n>>s)&255)*(1-f)+255*f).toString(16).padStart(2,'0')).join('')}
function rr(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath()}
function draw(i,sel){const p=PH[i],c=p.cv.getContext('2d'),W=p.cv.width,H=p.cv.height;c.clearRect(0,0,W,H);
 const g=c.createLinearGradient(0,0,W*.5,H);g.addColorStop(0,lite(p.c,.2));g.addColorStop(1,shade(p.c,.62));
 c.fillStyle=g;rr(c,6,6,W-12,H-12,34);c.fill();c.lineWidth=sel?7:3;c.strokeStyle=sel?'#fff':'rgba(255,255,255,.25)';c.stroke();
 c.fillStyle='rgba(0,0,0,.28)';c.beginPath();c.arc(54,56,26,0,7);c.fill();c.fillStyle='#fff';c.font='600 28px Outfit,sans-serif';c.textAlign='center';c.fillText(i+1,54,66);
 c.font='600 42px Outfit,sans-serif';c.fillText(p.n,W/2,H/2+14);c.fillStyle='rgba(255,255,255,.72)';c.font='400 26px Outfit,sans-serif';c.fillText(p.s,W/2,H/2+58);
 if(p.st!=='idle'){c.fillStyle=p.st==='ok'?'#bbf7d0':'#fecaca';c.font='700 38px Outfit,sans-serif';c.textAlign='right';c.fillText(p.st==='ok'?'\u2713':'\u2715',W-34,66)}
 p.tex.needsUpdate=true}
// radial glow texture
const gc=document.createElement('canvas');gc.width=gc.height=128;const gg=gc.getContext('2d'),gr=gg.createRadialGradient(64,64,0,64,64,64);gr.addColorStop(0,'rgba(255,255,255,.9)');gr.addColorStop(1,'rgba(255,255,255,0)');gg.fillStyle=gr;gg.fillRect(0,0,128,128);const GT=new THREE.CanvasTexture(gc);
const NW=3.7,NH=2.1;
PH.forEach((p,i)=>{p.cv=document.createElement('canvas');p.cv.width=592;p.cv.height=336;p.tex=new THREE.CanvasTexture(p.cv);p.tex.anisotropy=4;
 p.mesh=new THREE.Mesh(new THREE.PlaneGeometry(NW,NH),new THREE.MeshBasicMaterial({map:p.tex,transparent:true}));p.mesh.position.set(p.x,p.y,0);p.mesh.userData.i=i;G.add(p.mesh);
 p.glow=new THREE.Mesh(new THREE.PlaneGeometry(NW*1.9,NH*2),new THREE.MeshBasicMaterial({map:GT,color:p.pc,transparent:true,opacity:.22,blending:THREE.AdditiveBlending,depthWrite:false}));p.glow.position.set(p.x,p.y,-.3);G.add(p.glow);
 p.ts=1;p.sc=1;draw(i,false)});
// connectors
const curves=[],tubes=[];
for(let i=0;i<N-1;i++){const a=PH[i],b=PH[i+1];let A,B,pts;
 if(i===3){A=new THREE.Vector3(a.x+NW/2,a.y,-.1);B=new THREE.Vector3(b.x+NW/2,b.y,-.1);pts=[A,new THREE.Vector3(A.x+1.3,a.y-.2,-.1),new THREE.Vector3(A.x+1.3,b.y+.2,-.1),B]}
 else{const d=a.x<b.x?1:-1;A=new THREE.Vector3(a.x+d*NW/2,a.y,-.1);B=new THREE.Vector3(b.x-d*NW/2,b.y,-.1);pts=[A,A.clone().lerp(B,.35).add(new THREE.Vector3(0,.35,0)),A.clone().lerp(B,.65).add(new THREE.Vector3(0,-.35,0)),B]}
 const cu=new THREE.CatmullRomCurve3(pts);curves.push(cu);
 const m=new THREE.MeshBasicMaterial({color:0x35424f});const tb=new THREE.Mesh(new THREE.TubeGeometry(cu,40,.06,8,false),m);G.add(tb);tubes.push(m);
 [.3,.7].forEach(t=>{const s=new THREE.Mesh(new THREE.SphereGeometry(.12,12,12),m);s.position.copy(cu.getPoint(t));G.add(s)})}
function paintTubes(){tubes.forEach((m,i)=>m.color.set(PH[i].st==='ok'?PH[i].pc:'#35424f'))}paintTubes();
// data packet flowing along the whole path
const pk=new THREE.Mesh(new THREE.SphereGeometry(.17,16,16),new THREE.MeshBasicMaterial({color:0xbaf7ef}));G.add(pk);
const pkg=new THREE.Mesh(new THREE.PlaneGeometry(1.2,1.2),new THREE.MeshBasicMaterial({map:GT,color:0x67e8f9,transparent:true,opacity:.7,blending:THREE.AdditiveBlending,depthWrite:false}));G.add(pkg);
// starfield
const sp=[];for(let i=0;i<650;i++)sp.push((Math.random()-.5)*90,(Math.random()-.5)*60,-8-Math.random()*28);
const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.Float32BufferAttribute(sp,3));
const stars=new THREE.Points(sg,new THREE.PointsMaterial({color:0x9aa4b2,size:.1,transparent:true,opacity:.7}));S.add(stars);
// UI
const panel=document.getElementById('panel'),steps=document.getElementById('steps'),nm=document.getElementById('nm'),sum=document.getElementById('sum');
const done=PH.filter(p=>p.st==='ok').length,bad=PH.filter(p=>p.st==='bad').length;
sum.textContent=bad?bad+' failed':done+' / '+N+' phases passed';
PH.forEach((p,i)=>{const b=document.createElement('button');b.textContent=i+1;b.style.background=p.c;b.title=p.n;b.onclick=()=>pick(i);p.btn=b;steps.appendChild(b);if(i<N-1){const u=document.createElement('u');steps.appendChild(u)}});
let sel=-1,tx=0,ty=0,tz=17.5,base=17.5,cx=0,cy=0,cz=17.5,rx=.12,ry=-.08,trx=.12,tryy=-.08,drag=false,moved=0,lx=0,ly=0,mx=0,my=0;
function pick(i){const old=sel;sel=i;if(old>=0){PH[old].ts=1;draw(old,false)}
 if(i<0){panel.classList.add('off');tx=ty=0;tz=base;nm.textContent='';steps.querySelectorAll('button').forEach(b=>b.classList.remove('on'));app.style.setProperty('--ph','#2dd4bf');return}
 const p=PH[i];p.ts=1.08;draw(i,true);app.style.setProperty('--ph',p.pc);tx=p.x*.55;ty=p.y*.5;tz=base*.84;nm.textContent=p.n;
 steps.querySelectorAll('button').forEach((b,k)=>b.classList.toggle('on',k===i));
 const lab={ok:'Passed',bad:'Failed',idle:'Not run'}[p.st];
 panel.innerHTML='<button class="x" id="cl">\u2715</button><div class="lab">Phase '+(i+1)+' of '+N+'</div><h2>'+p.n+'</h2><div class="sub">'+p.s+'</div><span class="badge b-'+p.st+'">'+lab+'</span><p>'+p.d+'</p><h4>Key points</h4><ul>'+p.k.map(k=>'<li>'+k+'</li>').join('')+'</ul>';
 panel.classList.remove('off');document.getElementById('cl').onclick=()=>pick(-1)}
// interaction
const ray=new THREE.Raycaster(),v=new THREE.Vector2();
cv.addEventListener('pointerdown',e=>{drag=true;moved=0;lx=e.clientX;ly=e.clientY;cv.style.cursor='grabbing'});
addEventListener('pointerup',e=>{if(drag&&moved<5){const r=cv.getBoundingClientRect();v.set(((e.clientX-r.left)/r.width)*2-1,-((e.clientY-r.top)/r.height)*2+1);ray.setFromCamera(v,C);const h=ray.intersectObjects(PH.map(p=>p.mesh))[0];if(h)pick(h.object.userData.i);else if(sel>=0)pick(-1)}drag=false;cv.style.cursor='grab'});
addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect();mx=e.clientX;my=e.clientY;
 if(drag){moved+=Math.abs(e.clientX-lx)+Math.abs(e.clientY-ly);tryy=Math.max(-.5,Math.min(.5,tryy+(e.clientX-lx)*.004));trx=Math.max(-.35,Math.min(.45,trx+(e.clientY-ly)*.003));lx=e.clientX;ly=e.clientY}
 else{v.set(((mx-r.left)/r.width)*2-1,-((my-r.top)/r.height)*2+1);ray.setFromCamera(v,C);const h=ray.intersectObjects(PH.map(p=>p.mesh))[0];cv.style.cursor=h?'pointer':'grab';PH.forEach((p,i)=>{p.hv=h&&h.object.userData.i===i})}});
cv.addEventListener('wheel',e=>{e.preventDefault();tz=Math.max(9,Math.min(45,tz+e.deltaY*.02))},{passive:false});
function fit(){const w=app.clientWidth,h=app.clientHeight;R.setSize(w,h,false);C.aspect=w/h;C.updateProjectionMatrix();base=Math.max(13.5,22/(.933*C.aspect));if(sel<0)tz=base}addEventListener('resize',fit);fit();cz=tz;
// path length for packet
const lens=curves.map(c=>c.getLength()),tot=lens.reduce((a,b)=>a+b,0);
function at(u){let d=u*tot;for(let i=0;i<curves.length;i++){if(d<=lens[i])return curves[i].getPoint(d/lens[i]);d-=lens[i]}return curves[curves.length-1].getPoint(1)}
(function loop(t){requestAnimationFrame(loop);t*=.001;
 cx+=(tx-cx)*.07;cy+=(ty-cy)*.07;cz+=(tz-cz)*.07;rx+=(trx-rx)*.08;ry+=(tryy-ry)*.08;
 if(!drag&&sel<0){tryy=Math.sin(t*.25)*.12}
 G.rotation.set(rx,ry,0);C.position.set(cx,cy,cz);C.lookAt(cx,cy,0);
 PH.forEach((p,i)=>{p.sc+=(((p.hv?1.05:1)*p.ts)-p.sc)*.12;p.mesh.scale.set(p.sc,p.sc,1);p.mesh.position.y=p.y+Math.sin(t*.9+i)*.06;p.glow.position.y=p.mesh.position.y;p.glow.material.opacity=i===sel?.5:(p.hv?.34:.2)});
 const u=(t*.07)%1,q=at(u);pk.position.copy(q);pkg.position.set(q.x,q.y,q.z);pkg.material.opacity=.5+Math.sin(t*6)*.2;
 stars.rotation.z=t*.004;R.render(S,C)})(0);
</script></body></html>"""

_TT3D_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#0e1115;overflow:hidden;font-family:sans-serif}
#c{width:100%;height:100%;display:block;cursor:grab}
#tip{position:absolute;pointer-events:none;padding:8px 12px;border-radius:4px;background:#fbfbfa;color:#1b2430;font-size:13px;border:1px solid #b9c0c7;box-shadow:0 6px 14px rgba(0,0,0,.25);display:none}
.cap{position:absolute;left:14px;bottom:10px;color:#8b929c;font-size:12px}
</style></head><body><canvas id="c"></canvas><div id="tip"></div>
<div class="cap">Drag to rotate · scroll to zoom · hover a block for details</div>
<script src="__THREE__"></script><script>
const D=__DATA__, DAYS=__DAYS__, TIMES=__TIMES__, COL=__COLS__;
const cv=document.getElementById('c'),tip=document.getElementById('tip');
const R=new THREE.WebGLRenderer({canvas:cv,antialias:true});R.setPixelRatio(Math.min(devicePixelRatio,2));
R.shadowMap.enabled=true;R.shadowMap.type=THREE.PCFSoftShadowMap;R.setClearColor(0x0e1115);
const S=new THREE.Scene();S.fog=new THREE.Fog(0x0e1115,26,60);
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


# phase key -> (index, name, dark colour, light colour); mirrors the dashboard map
_PHASE_META = [
    ("rule", "TCS Rules", "#0aa346", "#22c55e"),
    ("lexical", "Lexical Analysis", "#0d4fc4", "#3b82f6"),
    ("syntax", "Syntax Analysis", "#a0125f", "#ec4899"),
    ("semantic", "Semantic Analysis", "#b34510", "#f97316"),
    ("intermediate", "Intermediate Code", "#7a3ad4", "#a78bfa"),
    ("constraint", "Constraint Generation", "#0e7490", "#22d3ee"),
    ("solver", "CP-SAT Solver", "#b0132a", "#ef4444"),
    ("timetable", "Timetable", "#15803d", "#34d399"),
]


def _phase_of(title: str) -> int | None:
    low = title.lower()
    for i, (key, *_rest) in enumerate(_PHASE_META):
        if key in low:
            return i
    return None


def _phase_states() -> list[str]:
    s = st.session_state
    sem, sol = s.get("semantic_result"), s.get("solver_result")

    def f(done, failed=False):
        return "bad" if failed else ("ok" if done else "idle")

    return [
        f(bool(s.get("source_code"))), f(bool(s.get("tokens"))), f(bool(s.get("parse_tree"))),
        f(bool(sem and sem.valid), bool(sem and not sem.valid)), f(bool(s.get("ir_instructions"))),
        f(bool(s.get("constraint_set"))), f(bool(sol and sol.success), bool(sol and not sol.success)),
        f(bool(sol and sol.success and sol.timetable)),
    ]


_PAGE_CSS = """
<style>
:root{--ph:%(pc)s;}
.stApp{ background:
  radial-gradient(ellipse at 50%% 0%%, color-mix(in srgb,%(pc)s 20%%,transparent), transparent 55%%),
  radial-gradient(ellipse at 0%% 100%%, color-mix(in srgb,%(pc)s 12%%,transparent), transparent 50%%), #090b0f; }
div[data-testid="stExpander"], div[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"]{ border-top:3px solid %(pc)s !important; }
div[data-baseweb="tab-highlight"]{ background:%(pc)s !important; }
.stButton>button:hover, .stDownloadButton>button:hover{ border-color:%(pc)s; color:%(pc)s; }
.stButton>button[kind="primary"]{ background:color-mix(in srgb,%(pc)s 22%%,#0e1115); border-color:color-mix(in srgb,%(pc)s 60%%,#252a31); color:#fff; }
.stButton>button[kind="primary"]:hover{ background:color-mix(in srgb,%(pc)s 38%%,#0e1115); color:#fff; }
.tt th{ color:%(pc)s; }
</style>
"""


def page_header(title: str, subtitle: str = "", tag: str = "") -> None:
    """Phase-coloured heading with a logo tile and a mini phase stepper."""
    import re as _re
    title = _EMOJI.sub("", title)
    title = _re.sub(r"^Phase\s*\d+(\s*&\s*\w+)?:\s*", "", title)
    idx = _phase_of(title)
    if idx is None:
        dark, light, label = "#14b8a6", "#2dd4bf", tag or "Workspace"
        tile = "&lt;/&gt;"
        if "error" in title.lower():
            dark, light, label, tile = "#b0132a", "#ef4444", "Diagnostics", "!"
    else:
        _k, _n, dark, light = _PHASE_META[idx]
        label, tile = f"Phase {idx + 1} of {len(_PHASE_META)}", str(idx + 1)
    st.html(_PAGE_CSS % {"pc": light})

    stepper = ""
    if idx is not None:
        states = _phase_states()
        dots = ""
        for i, (_key, name, c, pc) in enumerate(_PHASE_META):
            cls = ("on " if i == idx else "") + states[i]
            dots += f'<span class="sd {cls}" style="--c:{c};--pc:{pc}" title="{html.escape(name)}">{i + 1}</span>'
            if i < len(_PHASE_META) - 1:
                dots += '<span class="sl"></span>'
        stepper = f'<div class="stepper">{dots}</div>'
    st.html(
        f'<div class="ph"><div class="logo" style="background:linear-gradient(135deg,{light},{dark});'
        f'border-color:{light}66;color:#fff">{tile}</div><div class="phtxt">'
        f'<div class="eyebrow" style="color:{light}">{html.escape(label)}</div>'
        f'<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>{stepper}</div>'
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


def pipeline_scene(phases: list[dict], height: int = 760) -> None:
    """Full-width interactive 3D map of the compiler phases.

    phases: dicts with n (name), s (subtitle), c/pc (dark/light colour), d (summary),
    k (key points) and st ('ok' | 'bad' | 'idle').
    """
    import json
    page = (_PIPE_HTML.replace("__THREE__", _THREE)
            .replace("__DATA__", json.dumps(phases).replace("</", "<\\/")))
    with st.container(key="phasemap"):
        st.iframe(page, height=height, alt="Interactive 3D map of the compiler phases")


def hero_3d(height: int = 470) -> None:
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
