// Dead Mall Arena LAN — boot loader.
// Picks a graphics preset, builds a THREE shim (modern three.js with the old game's
// expectations), wires up the post-processing pipeline, then starts game.js.
import * as T from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { SMAAPass } from 'three/addons/postprocessing/SMAAPass.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

/* ------------------------------------------------------------------
   QUALITY PRESETS
   ultra  — AMD Ryzen AI Max+ 395 (Radeon 8060S) and other strong GPUs
   high   — good gaming laptops / desktops
   medium — older or integrated GPUs
   pi     — Raspberry Pi 5 / 500 (VideoCore VII)
------------------------------------------------------------------ */
const PRESETS = {
  ultra:  { label:'Ultra (AMD 395)',  scale:1.0,  maxDpr:1.5, msaa:4, smaa:false, post:true, ao:true,  aoHalf:false, bloom:true, shadows:true, shadowSize:4096, pointShadows:6, env:true,  lambert:false, shafts:true, dust:900, lightCull:46, maxLights:22, aniso:8, grain:true,  floorDetail:2048, exposure:1.05 },
  high:   { label:'High',             scale:1.0,  maxDpr:1.25,msaa:4, smaa:false, post:true, ao:true,  aoHalf:true,  bloom:true, shadows:true, shadowSize:2048, pointShadows:3, env:true,  lambert:false, shafts:true, dust:500, lightCull:34, maxLights:16, aniso:4, grain:true,  floorDetail:1024, exposure:1.05 },
  medium: { label:'Medium',           scale:1.0,  maxDpr:1.0, msaa:0, smaa:true,  post:true, ao:false, aoHalf:true,  bloom:true, shadows:true, shadowSize:1024, pointShadows:0, env:true,  lambert:false, shafts:true, dust:250, lightCull:26, maxLights:10, aniso:2, grain:false, floorDetail:1024, exposure:1.05 },
  pi:     { label:'Pi 500',           scale:0.8,  maxDpr:1.0, msaa:0, smaa:false, post:false,ao:false, aoHalf:true,  bloom:false,shadows:false,shadowSize:512,  pointShadows:0, env:false, lambert:true,  shafts:true, dust:0,   lightCull:16, maxLights:6,  aniso:1, grain:false, floorDetail:512,  exposure:1.1  }
};

function detectGPU(){
  try{
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if(!gl) return '';
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    const r = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    const lose = gl.getExtension('WEBGL_lose_context'); if(lose) lose.loseContext();
    return String(r||'');
  }catch(e){ return ''; }
}
function autoPreset(gpu){
  const g = gpu.toLowerCase();
  if(/v3d|videocore|broadcom|mali|adreno|powervr|llvmpipe|swiftshader/.test(g)) return 'pi';
  if(/radeon|amd|rtx|geforce gtx 1[0-9]|rx \d|arc/.test(g)) return 'ultra';
  if(/geforce|apple m\d|iris xe/.test(g)) return 'high';
  if(/intel/.test(g)) return 'medium';
  return (window.DMA_DEFAULT_QUALITY || 'high');
}
const params = new URLSearchParams(location.search);
const gpuName = detectGPU();
let stored = null; try{ stored = localStorage.getItem('dma_quality'); }catch(e){}
let choice = params.get('q') || stored || 'auto';
if(params.has('lowpower')) choice = 'pi';
const resolved = (choice === 'auto' || !PRESETS[choice]) ? autoPreset(gpuName) : choice;
const Q = Object.assign({ name: resolved }, PRESETS[resolved]);

/* ------------------------------------------------------------------
   THREE SHIM — the game was written against r128; this keeps its code
   working on r160 while upgrading materials, textures and lights.
------------------------------------------------------------------ */
const NOT_LAMBERT = ['roughness','metalness','roughnessMap','metalnessMap','envMapIntensity','clearcoat','sheen','transmission','ior','thickness'];
const allMaterials = [];
class GameStandardMaterial extends (Q.lambert ? T.MeshLambertMaterial : T.MeshStandardMaterial) {
  constructor(p){
    p = Object.assign({}, p || {});
    if(Q.lambert){ NOT_LAMBERT.forEach(k => delete p[k]); }
    super(p);
    allMaterials.push(this);
  }
}
class GameCanvasTexture extends T.CanvasTexture {
  constructor(...a){ super(...a); this.colorSpace = T.SRGBColorSpace; this.anisotropy = Q.aniso; }
}
const allPointLights = [];
class GamePointLight extends T.PointLight {
  // r128 used decay=1 by default; keep that look (we run with legacy light units)
  constructor(color, intensity = 1, distance = 0, decay = 1){
    super(color, intensity, distance, decay);
    allPointLights.push(this);
  }
}
const THREE = Object.assign({}, T, {
  MeshStandardMaterial: GameStandardMaterial,
  MeshPhongMaterial: GameStandardMaterial,
  MeshLambertMaterial: GameStandardMaterial,
  CanvasTexture: GameCanvasTexture,
  PointLight: GamePointLight
});
window.THREE = THREE;

/* ------------------------------------------------------------------
   DETERMINISTIC WORLD BUILD — every player must get the exact same mall
------------------------------------------------------------------ */
const realRandom = Math.random;
function mulberry32(a){ return function(){ a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

/* ------------------------------------------------------------------
   RENDER PIPELINE
------------------------------------------------------------------ */
const GradeShader = {
  uniforms: { tDiffuse:{value:null}, time:{value:0}, grain:{value:Q.grain?0.035:0.0}, aberr:{value:Q.grain?0.0012:0.0}, hurt:{value:0} },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float time; uniform float grain; uniform float aberr; uniform float hurt;
    varying vec2 vUv;
    float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + time*7.13) * 43758.5453); }
    void main(){
      vec2 d = vUv - 0.5;
      float r2 = dot(d,d);
      vec2 off = d * aberr * (1.0 + r2*6.0);
      vec4 c;
      c.r = texture2D(tDiffuse, vUv + off).r;
      c.g = texture2D(tDiffuse, vUv).g;
      c.b = texture2D(tDiffuse, vUv - off).b;
      c.a = 1.0;
      // gentle split-tone: cool shadows, warm sodium highlights — the dead-mall palette
      float l = dot(c.rgb, vec3(0.2126,0.7152,0.0722));
      c.rgb = mix(c.rgb, c.rgb*vec3(0.92,0.98,1.08), smoothstep(0.35,0.0,l)*0.6);
      c.rgb = mix(c.rgb, c.rgb*vec3(1.06,1.0,0.9), smoothstep(0.4,1.2,l)*0.5);
      c.rgb += (hash(vUv*vec2(1920.0,1080.0)) - 0.5) * grain * (0.6 + l);
      c.rgb = mix(c.rgb, c.rgb*vec3(1.4,0.55,0.5), hurt);
      gl_FragColor = c;
    }`
};

function createPipeline(scene, camera){
  const renderer = new T.WebGLRenderer({ antialias: !Q.post && Q.name !== 'pi', powerPreference:'high-performance', stencil:false });
  renderer.useLegacyLights = true;
  renderer.outputColorSpace = T.SRGBColorSpace;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = Q.exposure;
  renderer.shadowMap.enabled = !!Q.shadows;
  renderer.shadowMap.type = T.PCFSoftShadowMap;
  const dpr = Math.min(window.devicePixelRatio || 1, Q.maxDpr) * Q.scale;
  renderer.setPixelRatio(dpr);
  renderer.setSize(window.innerWidth, window.innerHeight);
  document.body.appendChild(renderer.domElement);

  let composer = null, gtao = null, bloom = null, grade = null, smaa = null;
  if(Q.post){
    const w = window.innerWidth, h = window.innerHeight;
    const rt = new T.WebGLRenderTarget(w*dpr, h*dpr, { type:T.HalfFloatType, samples:Q.msaa });
    composer = new EffectComposer(renderer, rt);
    composer.setPixelRatio(dpr);
    composer.setSize(w, h);
    composer.addPass(new RenderPass(scene, camera));
    if(Q.ao){
      gtao = new GTAOPass(scene, camera, w*dpr, h*dpr);
      gtao.output = GTAOPass.OUTPUT.Default;
      gtao.blendIntensity = 0.85;
      gtao.updateGtaoMaterial({ radius:0.9, distanceExponent:1.4, thickness:1.2, scale:1.0, samples: Q.aoHalf ? 8 : 16, distanceFallOff:1.0, screenSpaceRadius:false });
      gtao.updatePdMaterial({ lumaPhi:10, depthPhi:2, normalPhi:3, radius:5, radiusExponent:1, rings:2, samples: Q.aoHalf ? 8 : 16 });
      composer.addPass(gtao);
    }
    if(Q.bloom){
      bloom = new UnrealBloomPass(new T.Vector2(w, h), 0.55, 0.55, 0.9);
      composer.addPass(bloom);
    }
    grade = new ShaderPass(GradeShader);
    composer.addPass(grade);
    composer.addPass(new OutputPass());
    if(Q.smaa){ smaa = new SMAAPass(w*dpr, h*dpr); composer.addPass(smaa); }
  }
  function resize(){
    camera.aspect = window.innerWidth/window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    if(composer){ composer.setSize(window.innerWidth, window.innerHeight); }
  }
  window.addEventListener('resize', resize);
  // adaptive resolution: if this machine can't hold the target frame rate (say a 4K screen on Ultra,
  // or a busy Pi), quietly lower the render resolution a step at a time — and raise it back when there's headroom
  const baseDpr = dpr, minDpr = Math.max(0.5, dpr*0.6);
  const targetMs = Q.lambert ? 33.4 : 16.8;
  let curDpr = dpr, ema = targetMs, lastT = 0, lastAdapt = performance.now() + 4000, frames = 0, fpsShown = 0, fpsAcc = 0, fpsN = 0;
  const fpsEl = document.createElement('div');
  fpsEl.style.cssText = 'position:fixed;top:4px;right:6px;z-index:40;font:11px "JetBrains Mono",monospace;color:#7ee89f;background:rgba(0,0,0,.45);padding:2px 6px;display:none;pointer-events:none';
  document.body.appendChild(fpsEl);
  window.addEventListener('keydown', e => { if(e.code === 'KeyF' && !e.repeat && document.activeElement && document.activeElement.tagName !== 'INPUT') fpsEl.style.display = fpsEl.style.display === 'none' ? 'block' : 'none'; });
  function applyDpr(v){
    curDpr = v;
    renderer.setPixelRatio(v);
    if(composer) composer.setPixelRatio(v);
    resize();
  }
  function adapt(now){
    if(lastT){
      const dt = Math.min(250, now - lastT);
      ema += (dt - ema) * 0.05;
      fpsAcc += dt; fpsN++;
      if(now - fpsShown > 500 && fpsEl.style.display !== 'none'){
        fpsShown = now;
        fpsEl.textContent = Math.round(1000/(fpsAcc/fpsN)) + ' fps · ' + Q.name + ' · ' + Math.round(curDpr*100) + '% res';
        fpsAcc = 0; fpsN = 0;
      }
      if(now - lastAdapt > 2500 && !document.hidden){
        lastAdapt = now;
        if(ema > targetMs*1.22 && curDpr > minDpr + 0.01) applyDpr(Math.max(minDpr, curDpr*0.86));
        else if(ema < targetMs*1.04 && curDpr < baseDpr - 0.01) applyDpr(Math.min(baseDpr, curDpr*1.08));
      }
    }
    lastT = now;
  }
  document.addEventListener('visibilitychange', () => { lastT = 0; lastAdapt = performance.now() + 3000; });
  const t0 = performance.now();
  function render(){
    const now = performance.now();
    adapt(now);
    if(composer){
      grade.uniforms.time.value = (now-t0)/1000;
      composer.render();
    } else {
      renderer.render(scene, camera);
    }
  }
  function setHurt(v){ if(grade) grade.uniforms.hurt.value = v; }
  return { renderer, composer, render, resize, setHurt, gtao, bloom, get dpr(){ return curDpr; } };
}

window.DMA = {
  THREE_NS: T, Q, PRESETS, gpuName, choice, mergeGeometries,
  allMaterials, allPointLights,
  createPipeline,
  seedRandom(seed){ Math.random = mulberry32(seed); },
  unseedRandom(){ Math.random = realRandom; },
  setQuality(name){ try{ localStorage.setItem('dma_quality', name); }catch(e){} const u = new URL(location.href); u.searchParams.delete('q'); u.searchParams.delete('lowpower'); location.href = u.toString(); }
};

// make sure sign textures are drawn with the real fonts, then start the game
(async function start(){
  try{
    await Promise.race([
      Promise.all([
        document.fonts.load('700 40px Orbitron'), document.fonts.load('900 28px Orbitron'),
        document.fonts.load('500 20px Orbitron'), document.fonts.load('400 14px "JetBrains Mono"'),
        document.fonts.load('600 14px "JetBrains Mono"')
      ]),
      new Promise(r => setTimeout(r, 2500))
    ]);
  }catch(e){}
  for(const src of ['graphics.js', 'net.js', 'game.js']){
    await new Promise((res, rej) => { const s = document.createElement('script'); s.src = src + '?v=' + (window.DMA_BUILD||'1'); s.onload = res; s.onerror = () => rej(new Error('could not load ' + src)); document.body.appendChild(s); });
  }
})();
