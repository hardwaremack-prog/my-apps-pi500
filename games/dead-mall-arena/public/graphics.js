// Dead Mall Arena LAN — graphics upgrade layer.
// Runs after the mall is built: procedural PBR surfaces, shadows, reflections,
// god rays through the skylight, drifting dust, pooled muzzle/explosion lights
// and a light manager that never changes the active light count (no shader hitches).
(function(){
  'use strict';
  const Q = DMA.Q;
  const T = DMA.THREE_NS;

  /* ---------------- small procedural texture toolkit ---------------- */
  function rng(seed){ let a = seed>>>0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function valueNoise(size, cells, seed){
    // tileable value noise grid -> Float32Array size*size in 0..1
    const r = rng(seed), g = new Float32Array(cells*cells);
    for(let i=0;i<g.length;i++) g[i] = r();
    const out = new Float32Array(size*size);
    for(let y=0;y<size;y++){
      const fy = y/size*cells, y0 = Math.floor(fy), ty = fy-y0, sy = ty*ty*(3-2*ty);
      for(let x=0;x<size;x++){
        const fx = x/size*cells, x0 = Math.floor(fx), tx = fx-x0, sx = tx*tx*(3-2*tx);
        const x1 = (x0+1)%cells, y1 = (y0+1)%cells;
        const a = g[y0*cells+x0], b = g[y0*cells+x1], c = g[y1*cells+x0], d = g[y1*cells+x1];
        out[y*size+x] = (a+(b-a)*sx) + ((c+(d-c)*sx) - (a+(b-a)*sx))*sy;
      }
    }
    return out;
  }
  function fbm(size, baseCells, octaves, seed){
    const out = new Float32Array(size*size);
    let amp = 0.5, total = 0;
    for(let o=0;o<octaves;o++){
      const n = valueNoise(size, baseCells<<o, seed+o*101);
      for(let i=0;i<out.length;i++) out[i] += n[i]*amp;
      total += amp; amp *= 0.5;
    }
    for(let i=0;i<out.length;i++) out[i] /= total;
    return out;
  }
  function canvasOf(size){ const c = document.createElement('canvas'); c.width = c.height = size; return c; }
  function texFrom(canvas, srgb, repeat){
    const t = new T.CanvasTexture(canvas);
    t.colorSpace = srgb ? T.SRGBColorSpace : T.NoColorSpace;
    t.wrapS = t.wrapT = T.RepeatWrapping;
    t.anisotropy = Q.aniso;
    if(repeat) t.repeat.set(repeat, repeat);
    return t;
  }
  function normalFromHeight(height, size, strength){
    const c = canvasOf(size), ctx = c.getContext('2d'), img = ctx.createImageData(size, size), d = img.data;
    for(let y=0;y<size;y++) for(let x=0;x<size;x++){
      const l = height[y*size+((x-1+size)%size)], r = height[y*size+((x+1)%size)];
      const u = height[((y-1+size)%size)*size+x], b = height[((y+1)%size)*size+x];
      let nx = (l-r)*strength, ny = (u-b)*strength, nz = 1;
      const inv = 1/Math.hypot(nx,ny,nz);
      const i = (y*size+x)*4;
      d[i] = (nx*inv*0.5+0.5)*255; d[i+1] = (ny*inv*0.5+0.5)*255; d[i+2] = (nz*inv*0.5+0.5)*255; d[i+3] = 255;
    }
    ctx.putImageData(img,0,0);
    return c;
  }

  /* ---------------- ground floor: worn 80s mall tile ---------------- */
  function makeGroundFloor(){
    const S = Q.floorDetail, tiles = 8, tp = S/tiles, grout = Math.max(2, Math.round(S/340));
    const r = rng(1987);
    const grime = fbm(S, 4, 5, 11), fine = fbm(S, 32, 3, 77), puddle = fbm(S, 3, 3, 404);
    const col = canvasOf(S), cx = col.getContext('2d');
    const h = new Float32Array(S*S), rough = new Float32Array(S*S);
    // per-tile base colors (two-tone checker with variation)
    const tileTone = [];
    for(let ty=0;ty<tiles;ty++) for(let tx=0;tx<tiles;tx++){
      const alt = (tx+ty)%2 === 0, v = (r()-0.5)*0.06;
      tileTone.push(alt ? [0.80+v, 0.74+v, 0.62+v] : [0.66+v, 0.58+v, 0.46+v]);
    }
    const img = cx.createImageData(S,S), d = img.data;
    for(let y=0;y<S;y++){
      const ty = Math.floor(y/tp), iy = y - ty*tp;
      for(let x=0;x<S;x++){
        const tx = Math.floor(x/tp), ix = x - tx*tp, i = y*S+x;
        const isGrout = ix < grout || iy < grout;
        const g = grime[i], f = fine[i], p = puddle[i];
        let cr, cg, cb, hh, rr;
        if(isGrout){ cr = 0.30; cg = 0.27; cb = 0.23; hh = 0.0; rr = 0.9; }
        else {
          const t = tileTone[ty*tiles+tx];
          const speck = f > 0.72 ? 0.85 : (f < 0.28 ? 1.12 : 1.0); // terrazzo chips
          cr = t[0]*speck; cg = t[1]*speck; cb = t[2]*speck; hh = 1.0 - (f>0.72?0.08:0); rr = 0.16 + f*0.1;
        }
        const dirt = Math.max(0, g-0.45)*1.6;            // big grime blotches
        cr *= 1-dirt*0.55; cg *= 1-dirt*0.58; cb *= 1-dirt*0.62;
        rr = Math.min(1, rr + dirt*0.5);
        if(p > 0.66){ const w = Math.min(1,(p-0.66)*9); rr = rr*(1-w) + 0.04*w; cr*=1-w*0.18; cg*=1-w*0.18; cb*=1-w*0.15; } // standing water from the leaking roof
        h[i] = hh; rough[i] = rr;
        d[i*4] = Math.min(255,cr*255); d[i*4+1] = Math.min(255,cg*255); d[i*4+2] = Math.min(255,cb*255); d[i*4+3] = 255;
      }
    }
    cx.putImageData(img,0,0);
    // scuffs and cracks
    cx.lineCap = 'round';
    for(let k=0;k<40;k++){
      cx.strokeStyle = `rgba(30,24,18,${0.08+r()*0.12})`; cx.lineWidth = S/600 + r()*S/500;
      const x = r()*S, y = r()*S, rad = S/40 + r()*S/14, a0 = r()*6.28;
      cx.beginPath(); cx.arc(x,y,rad,a0,a0+0.6+r()*1.4); cx.stroke();
    }
    for(let k=0;k<9;k++){
      cx.strokeStyle = 'rgba(25,20,15,0.65)'; cx.lineWidth = Math.max(1, S/900);
      let x = r()*S, y = r()*S; cx.beginPath(); cx.moveTo(x,y);
      for(let s=0;s<7;s++){ x += (r()-0.5)*S/18; y += (r()-0.5)*S/18; cx.lineTo(x,y); }
      cx.stroke();
    }
    const rCan = canvasOf(S), rctx = rCan.getContext('2d'), rimg = rctx.createImageData(S,S);
    for(let i=0;i<S*S;i++){ const v = rough[i]*255; rimg.data[i*4] = 0; rimg.data[i*4+1] = v; rimg.data[i*4+2] = 0; rimg.data[i*4+3] = 255; }
    rctx.putImageData(rimg,0,0);
    return { map: texFrom(col, true), rough: texFrom(rCan, false), normal: Q.lambert ? null : texFrom(normalFromHeight(h, S, 3.0), false) };
  }

  /* ---------------- ground-floor ceiling: water-stained drop tiles ---------------- */
  function makeDropCeiling(){
    const S = Math.min(1024, Q.floorDetail), n = 8, tp = S/n, bar = Math.max(2, Math.round(S/170));
    const r = rng(311), c = canvasOf(S), x = c.getContext('2d');
    const noise = fbm(S, 8, 3, 5);
    const img = x.createImageData(S,S), d = img.data;
    for(let i=0;i<S*S;i++){ const v = 0.70 + noise[i]*0.12; d[i*4] = v*235; d[i*4+1] = v*230; d[i*4+2] = v*212; d[i*4+3] = 255; }
    x.putImageData(img,0,0);
    for(let ty=0;ty<n;ty++) for(let tx=0;tx<n;tx++){
      const px = tx*tp, py = ty*tp, roll = r();
      if(roll < 0.06){ x.fillStyle = '#0b0a08'; x.fillRect(px,py,tp,tp); continue; } // missing tile: the dark void above
      if(roll < 0.22){ // water stain rings
        const cxp = px+tp*(0.3+r()*0.4), cyp = py+tp*(0.3+r()*0.4), rad = tp*(0.2+r()*0.35);
        const g = x.createRadialGradient(cxp,cyp,rad*0.2,cxp,cyp,rad);
        g.addColorStop(0,'rgba(140,110,60,0.18)'); g.addColorStop(0.8,'rgba(120,90,45,0.32)'); g.addColorStop(1,'rgba(120,90,45,0)');
        x.fillStyle = g; x.beginPath(); x.arc(cxp,cyp,rad,0,6.3); x.fill();
      }
      if(roll > 0.92){ x.save(); x.translate(px+tp/2,py+tp/2); x.rotate((r()-0.5)*0.12); x.fillStyle='rgba(0,0,0,0.35)'; x.fillRect(-tp/2,-tp/2,tp,tp*0.12); x.restore(); } // sagging tile
      x.fillStyle = 'rgba(0,0,0,0.12)';
      for(let k=0;k<60;k++) x.fillRect(px+r()*tp, py+r()*tp, 1.5, 1.5); // pinholes
    }
    x.fillStyle = '#6c6a62';
    for(let i=0;i<=n;i++){ x.fillRect(i*tp-bar/2,0,bar,S); x.fillRect(0,i*tp-bar/2,S,bar); }
    return texFrom(c, true);
  }

  /* ---------------- upstairs: speckled terrazzo with brass divider strips ---------------- */
  function makeTerrazzo(){
    const S = Q.floorDetail, r = rng(9001);
    const c = canvasOf(S), x = c.getContext('2d');
    const base = fbm(S, 6, 4, 42);
    const img = x.createImageData(S,S), d = img.data;
    const rmCan = canvasOf(S), rm = rmCan.getContext('2d'), rimg = rm.createImageData(S,S);
    for(let i=0;i<S*S;i++){
      const v = 0.42 + base[i]*0.14;
      d[i*4] = v*255*1.04; d[i*4+1] = v*255; d[i*4+2] = v*255*0.93; d[i*4+3] = 255;
      rimg.data[i*4+1] = (0.3 + base[i]*0.25)*255; rimg.data[i*4+3] = 255;
    }
    x.putImageData(img,0,0);
    const chips = ['#d9cdb4','#6b5a48','#a39282','#2c2a28','#b8794e','#e8e2d4'];
    const count = S*S/180;
    for(let k=0;k<count;k++){
      x.fillStyle = chips[Math.floor(r()*chips.length)];
      const s = 1 + r()*S/400;
      x.beginPath(); x.ellipse(r()*S, r()*S, s, s*(0.5+r()*0.6), r()*3, 0, 6.3); x.fill();
    }
    // brass strips every half texture (texture spans 6 m -> strips every 3 m)
    const strip = Math.max(2, Math.round(S/300));
    x.fillStyle = '#9a7a3a';
    for(const p of [0, S/2]){ x.fillRect(p,0,strip,S); x.fillRect(0,p,S,strip); }
    rm.putImageData(rimg,0,0);
    rm.fillStyle = 'rgb(0,90,255)'; // brass: lower roughness, metallic (B = metalness)
    for(const p of [0, S/2]){ rm.fillRect(p,0,strip,S); rm.fillRect(0,p,S,strip); }
    return { map: texFrom(c, true), rm: texFrom(rmCan, false) };
  }

  /* ---------------- walls: painted concrete block ---------------- */
  function makeBlockWall(){
    const S = Math.min(1024, Q.floorDetail), r = rng(55);
    const c = canvasOf(S), x = c.getContext('2d');
    const n = fbm(S, 8, 4, 9), streak = fbm(S, 16, 2, 13);
    const h = new Float32Array(S*S);
    const img = x.createImageData(S,S), d = img.data;
    const bw = S/4, bh = S/8, mortar = Math.max(2, Math.round(S/220)); // texture = 1.6 m: blocks 0.4 x 0.2 m
    for(let y=0;y<S;y++){
      const row = Math.floor(y/bh), iy = y - row*bh, off = (row%2)*bw/2;
      for(let xx=0;xx<S;xx++){
        const ix = ((xx+off)%bw), i = y*S+xx;
        const m = ix < mortar || iy < mortar;
        let v = m ? 0.62 : 0.88 + (n[i]-0.5)*0.18;
        // grime creeping up from the floor and rust streaks running down
        const fromBottom = y/S;
        v *= 1 - Math.max(0, fromBottom-0.72)*0.9*(0.6+n[i]*0.8);
        v *= 1 - Math.max(0, streak[i]-0.62)*1.2*(1-fromBottom*0.5);
        h[i] = m ? 0 : 1 - (n[i]-0.5)*0.2;
        d[i*4] = v*255; d[i*4+1] = v*250; d[i*4+2] = v*246; d[i*4+3] = 255;
      }
    }
    x.putImageData(img,0,0);
    // a little graffiti tagging and scrapes
    for(let k=0;k<6;k++){
      x.strokeStyle = `rgba(${40+r()*60},${20+r()*40},${30+r()*60},0.25)`; x.lineWidth = S/250;
      let px = r()*S, py = S*0.35 + r()*S*0.5; x.beginPath(); x.moveTo(px,py);
      for(let s=0;s<6;s++){ px += (r()-0.3)*S/14; py += (r()-0.5)*S/18; x.lineTo(px,py); }
      x.stroke();
    }
    return { map: texFrom(c, true), normal: Q.lambert ? null : texFrom(normalFromHeight(h, S, 2.0), false), meters: 1.6 };
  }

  /* ---------------- generic painted plaster detail for every other big surface ---------------- */
  function makePlaster(){
    const S = 512, c = canvasOf(S), x = c.getContext('2d');
    const n = fbm(S, 6, 5, 321), s = fbm(S, 24, 2, 99);
    const img = x.createImageData(S,S), d = img.data;
    for(let i=0;i<S*S;i++){
      const y = Math.floor(i/S)/S;
      let v = 0.9 + (n[i]-0.5)*0.16 - Math.max(0,s[i]-0.7)*0.25;
      v *= 1 - Math.max(0, y-0.8)*0.5;
      d[i*4] = v*255; d[i*4+1] = v*253; d[i*4+2] = v*249; d[i*4+3] = 255;
    }
    x.putImageData(img,0,0);
    return { map: texFrom(c, true), meters: 2.5 };
  }

  /* ---------------- box UVs scaled to real-world size ---------------- */
  function worldScaleBoxUVs(mesh, meters){
    const g = mesh.geometry;
    if(!g || !g.parameters || g.userData._uvScaled) return;
    const s = mesh.scale, p = g.parameters, uv = g.attributes.uv;
    if(g.type === 'BoxGeometry'){
      const W = p.width*s.x, H = p.height*s.y, D = p.depth*s.z;
      const faces = [[D,H],[D,H],[W,D],[W,D],[W,H],[W,H]];
      for(let f=0; f<6; f++){
        for(let v=0; v<4; v++){
          const i = f*4+v; if(i >= uv.count) break;
          uv.setXY(i, uv.getX(i)*faces[f][0]/meters, uv.getY(i)*faces[f][1]/meters);
        }
      }
    } else if(g.type === 'PlaneGeometry'){
      const W = p.width*s.x, H = p.height*s.y;
      for(let i=0;i<uv.count;i++) uv.setXY(i, uv.getX(i)*W/meters, uv.getY(i)*H/meters);
    } else return;
    uv.needsUpdate = true;
    g.userData._uvScaled = true;
  }

  /* ---------------- god rays + dust ---------------- */
  function makeShafts(scene, sunDir, floorY, roofY){
    // soft sunbeams through the skylight: each is a ribbon that always turns its face to the camera
    // around the beam's own axis (a cylindrical billboard), so it reads as a volume from any angle
    const r = rng(77);
    const beams = [];
    const len = (roofY - floorY) / Math.max(0.3, sunDir.y);
    // only keep beams with a clear path to the skylight (not through a store's roof)
    const blockers = [], bb = new T.Box3();
    scene.traverse(o => {
      if(!o.isMesh || !o.visible || !o.material || o.material.transparent || o.material.isShaderMaterial) return;
      bb.setFromObject(o);
      if(bb.max.y > floorY + 1 && bb.min.y < roofY - 1.2) blockers.push(o);
    });
    const ray = new T.Raycaster();
    const axis = sunDir.clone().normalize();
    for(let tries=0; tries<220 && beams.length < 22; tries++){
      const fx = (r()-0.5)*96, fz = (r()-0.5)*96;
      ray.set(new T.Vector3(fx, floorY + 0.3, fz), axis);
      ray.far = (roofY - 1.2 - floorY) / Math.max(0.3, axis.y);
      if(ray.intersectObjects(blockers, false).length) continue;
      beams.push({ x:fx, z:fz, w: 0.9 + r()*2.2, a: 0.5 + r()*0.5, ph: r()*6.28 });
    }
    const n = beams.length;
    const pos = new Float32Array(n*4*3), quad = new Float32Array(n*4*2), info = new Float32Array(n*4*4);
    const idx = [];
    beams.forEach((bm, i) => {
      const corners = [[0,-1],[0,1],[1,-1],[1,1]];
      corners.forEach((c, k) => {
        const v = i*4+k;
        pos[v*3] = bm.x; pos[v*3+1] = floorY; pos[v*3+2] = bm.z;
        quad[v*2] = c[0]; quad[v*2+1] = c[1];
        info[v*4] = bm.w; info[v*4+1] = bm.a; info[v*4+2] = bm.ph; info[v*4+3] = len;
      });
      idx.push(i*4, i*4+1, i*4+2, i*4+2, i*4+1, i*4+3);
    });
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.BufferAttribute(pos,3));
    g.setAttribute('quad', new T.BufferAttribute(quad,2));
    g.setAttribute('info', new T.BufferAttribute(info,4));
    g.setIndex(idx);
    const mat = new T.ShaderMaterial({
      transparent:true, depthWrite:false, blending:T.AdditiveBlending, side:T.DoubleSide, fog:false,
      uniforms:{ time:{value:0}, axis:{value:sunDir.clone().normalize()}, strength:{value: Q.lambert ? 0.07 : 0.085}, color:{value:new T.Color(0xffe9c8)} },
      vertexShader:`attribute vec2 quad; attribute vec4 info; uniform vec3 axis; varying vec2 vQ; varying float vA; varying float vPh; varying float vNear;
        void main(){
          vec3 base = position;                      // where the beam lands on the upstairs floor
          vec3 p = base + axis * quad.x * info.w;    // up the beam toward the skylight
          vec3 toCam = normalize(cameraPosition - p);
          vec3 side = normalize(cross(axis, toCam));
          p += side * quad.y * info.x;
          vQ = quad; vA = info.y; vPh = info.z;
          // fade a beam out as you walk into it, so it never smears across the whole screen
          vec3 c = cameraPosition - base; float along = clamp(dot(c, axis), 0.0, info.w);
          vNear = smoothstep(1.5, 6.0, length(c - axis*along));
          gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
        }`,
      fragmentShader:`uniform float time; uniform float strength; uniform vec3 color; varying vec2 vQ; varying float vA; varying float vPh; varying float vNear;
        void main(){
          float across = exp(-vQ.y*vQ.y*3.2);                         // soft gaussian edges
          float along = smoothstep(0.0,0.18,vQ.x) * smoothstep(1.0,0.7,vQ.x);
          float shimmer = 0.8 + 0.2*sin(time*0.6 + vPh + vQ.x*7.0);
          gl_FragColor = vec4(color * across * along * shimmer * strength * vA * vNear, 1.0);
        }`
    });
    const mesh = new T.Mesh(g, mat);
    mesh.frustumCulled = false;
    mesh.renderOrder = 5;
    mesh.userData.noShadow = true;
    scene.add(mesh);
    return mat;
  }
  function makeDust(scene, count, floorY, roofY){
    if(!count) return null;
    const pos = new Float32Array(count*3), seed = new Float32Array(count);
    const r = rng(5);
    for(let i=0;i<count;i++){
      pos[i*3] = (r()-0.5)*100; pos[i*3+1] = floorY + r()*(roofY-floorY); pos[i*3+2] = (r()-0.5)*100; seed[i] = r()*100;
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.BufferAttribute(pos,3));
    g.setAttribute('seed', new T.BufferAttribute(seed,1));
    const mat = new T.ShaderMaterial({
      transparent:true, depthWrite:false, blending:T.AdditiveBlending, fog:false,
      uniforms:{ time:{value:0}, px:{value: Math.min(window.devicePixelRatio||1, Q.maxDpr)} },
      vertexShader:`attribute float seed; uniform float time; uniform float px; varying float vA;
        void main(){ vec3 p = position; p.x += sin(time*0.11+seed)*1.6; p.y += sin(time*0.07+seed*1.7)*0.9; p.z += cos(time*0.09+seed*0.6)*1.6;
          vec4 mv = modelViewMatrix*vec4(p,1.0); gl_Position = projectionMatrix*mv;
          float d = -mv.z; vA = smoothstep(26.0, 3.0, d) * (0.4 + 0.6*fract(seed*7.31));
          gl_PointSize = px * 28.0 / max(d, 0.5); }`,
      fragmentShader:`varying float vA; void main(){ vec2 c = gl_PointCoord-0.5; float a = smoothstep(0.5,0.0,length(c)); gl_FragColor = vec4(vec3(1.0,0.95,0.85)*a*vA*0.45, 1.0); }`
    });
    const pts = new T.Points(g, mat);
    pts.frustumCulled = false;
    pts.userData.noShadow = true;
    scene.add(pts);
    return mat;
  }

  /* ---------------- pooled flash lights + constant-count light manager ---------------- */
  const pool = [];
  let staticLights = [], shadowLights = [];
  function initLightPool(scene){
    const n = Q.lambert ? 2 : 4;
    for(let i=0;i<n;i++){
      const l = new T.PointLight(0xffaa55, 0, 8, 1.5);
      l.userData.pooled = true;
      scene.add(l);
      pool.push({light:l, until:0, peak:0, start:0});
    }
  }
  function flash(position, color, intensity, distance, ms){
    let best = pool[0];
    for(const p of pool){ if(p.until < best.until) best = p; }
    if(!best) return;
    best.light.position.copy(position);
    best.light.color.set(color || 0xffaa55);
    best.light.distance = distance || 8;
    best.peak = (intensity || 3) * (Q.lambert ? 0.8 : 1.15);
    best.start = performance.now(); best.until = best.start + (ms || 70);
    best.light.intensity = best.peak;
  }
  function updatePool(now){
    for(const p of pool){
      if(now >= p.until){ p.light.intensity = 0; continue; }
      const f = (now - p.start) / (p.until - p.start);
      p.light.intensity = p.peak * (1 - f*f);
    }
  }
  let lastCull = 0;
  function updateLights(cam){
    const now = performance.now();
    updatePool(now);
    if(now - lastCull < 200) return;
    lastCull = now;
    const cx = cam.position.x, cy = cam.position.y, cz = cam.position.z;
    const scored = staticLights.map(l => {
      const wp = l.userData._wp;
      const dx = wp.x-cx, dy = (wp.y-cy)*1.6, dz = wp.z-cz;
      return { l, d: Math.sqrt(dx*dx+dy*dy+dz*dz) - (l.distance||10)*0.35 };
    }).sort((a,b) => a.d - b.d);
    const K = Math.min(Q.maxLights, scored.length);
    scored.forEach((s,i) => { s.l.visible = i < K; });
  }

  /* ---------------- the main pass, run once the mall exists ---------------- */
  function enhance(ctx){
    const { scene, camera, pipeline, ground, ceiling, groundMat, ceilingMat, wallMat, coverMat, railingMat, sun, rim, FLOOR2_Y, ARENA_HALF } = ctx;
    FLOOR2 = FLOOR2_Y; sceneRef = scene;
    const renderer = pipeline.renderer;
    const t0 = performance.now();

    // --- atmosphere
    scene.background = new T.Color(0x0d0c08);
    scene.fog = new T.Fog(0x2a271d, Q.lambert ? 6 : 12, Q.lambert ? 46 : 78);
    camera.far = Q.lambert ? 60 : 220; camera.updateProjectionMatrix();

    // --- ground floor tile
    const gf = makeGroundFloor();
    const rep = ARENA_HALF*2/6;
    [gf.map, gf.rough, gf.normal].forEach(t => { if(t) t.repeat.set(rep, rep); });
    groundMat.map = gf.map;
    if(!Q.lambert){
      groundMat.roughnessMap = gf.rough; groundMat.roughness = 1.0; groundMat.metalness = 0.0;
      if(gf.normal){ groundMat.normalMap = gf.normal; groundMat.normalScale = new T.Vector2(0.6, 0.6); }
      groundMat.envMapIntensity = 0.9;
    }
    groundMat.color.setHex(0xffffff);
    groundMat.needsUpdate = true;
    ground.receiveShadow = true;

    // --- ground floor ceiling (underside) + new upstairs floor surface
    const dc = makeDropCeiling();
    dc.repeat.set(ARENA_HALF*2/4.8, ARENA_HALF*2/4.8);
    ceilingMat.map = dc; ceilingMat.color.setHex(0xb8b4a8); ceilingMat.side = T.FrontSide;
    if(!Q.lambert){ ceilingMat.roughness = 0.95; }
    ceilingMat.needsUpdate = true;
    ceiling.receiveShadow = true; ceiling.castShadow = true;

    const tz = makeTerrazzo();
    const trep = ARENA_HALF*2/6;
    tz.map.repeat.set(trep, trep); tz.rm.repeat.set(trep, trep);
    const upMat = new THREE.MeshStandardMaterial({ map: tz.map, roughness: 1.0, metalness: 1.0, polygonOffset:true, polygonOffsetFactor:1, polygonOffsetUnits:1 });
    if(!Q.lambert){ upMat.roughnessMap = tz.rm; upMat.metalnessMap = tz.rm; upMat.envMapIntensity = 0.8; }
    const up = new T.Mesh(new T.PlaneGeometry(ARENA_HALF*2, ARENA_HALF*2), upMat);
    up.rotation.x = -Math.PI/2; up.position.y = FLOOR2_Y + 0.004;
    up.receiveShadow = true; up.userData.noCast = true;
    scene.add(up);

    // --- upper perimeter walls around the mezzanine (the original left the sides open to black)
    const block = makeBlockWall();
    {
      const roofTop = FLOOR2_Y + 9, hgt = roofTop - (FLOOR2_Y + 1.1), span = ARENA_HALF*2 + 1.2;
      const upperMat = new THREE.MeshStandardMaterial({ color:0x8a8478, roughness:0.9, map:block.map });
      if(block.normal && !Q.lambert){ upperMat.normalMap = block.normal; }
      const mk = (w, d, x, z) => {
        const m = new T.Mesh(new T.BoxGeometry(w, hgt, d), upperMat);
        m.position.set(x, FLOOR2_Y + 1.1 + hgt/2, z);
        worldScaleBoxUVs(m, block.meters);
        scene.add(m);
      };
      mk(span, 0.6, 0, -ARENA_HALF-0.6); mk(span, 0.6, 0, ARENA_HALF+0.6);
      mk(0.6, span, -ARENA_HALF-0.6, 0); mk(0.6, span, ARENA_HALF+0.6, 0);
      // a band of clerestory-style windows: dim blue panels near the top of each wall
      const winMat = new T.MeshBasicMaterial({ color: Q.bloom ? 0x23303c : 0x1c2630 });
      const winY = FLOOR2_Y + 6.6;
      for(let i=-4;i<=4;i++){
        const off = i*11.5;
        [[off, -ARENA_HALF-0.28, 0],[off, ARENA_HALF+0.28, Math.PI],[-ARENA_HALF-0.28, off, Math.PI/2],[ARENA_HALF+0.28, off, -Math.PI/2]].forEach(([x,z,ry]) => {
          const w = new T.Mesh(new T.PlaneGeometry(7, 2.2), winMat);
          w.position.set(x, winY, z); w.rotation.y = ry; w.userData.noShadow = true;
          scene.add(w);
        });
      }
    }

    // --- walls & big untextured surfaces get real-world-scaled detail
    const plaster = makePlaster();
    const blockMats = new Set([wallMat, coverMat, railingMat].filter(Boolean));
    blockMats.forEach(m => {
      m.map = block.map; if(block.normal && !Q.lambert){ m.normalMap = block.normal; m.normalScale = new T.Vector2(0.7,0.7); }
      m.needsUpdate = true;
    });
    // collect users of each material
    const users = new Map();
    scene.traverse(o => {
      if(!o.isMesh || Array.isArray(o.material)) return;
      if(!users.has(o.material)) users.set(o.material, []);
      users.get(o.material).push(o);
    });
    const geoOwners = new Map();
    scene.traverse(o => { if(o.isMesh && o.geometry){ geoOwners.set(o.geometry, (geoOwners.get(o.geometry)||0)+1); } });
    users.forEach((meshes, mat) => {
      const isBlock = blockMats.has(mat);
      const candidate = isBlock || (!mat.map && (mat.isMeshStandardMaterial || mat.isMeshLambertMaterial) && !mat.transparent &&
        meshes.every(m => m.geometry && (m.geometry.type === 'BoxGeometry' || m.geometry.type === 'PlaneGeometry')) &&
        meshes.some(m => { const p = m.geometry.parameters; return Math.max(p.width||0, p.height||0, p.depth||0) > 1.6; }) &&
        (mat.emissive ? mat.emissive.getHex() === 0 : true));
      if(!candidate) return;
      const meters = isBlock ? block.meters : plaster.meters;
      meshes.forEach(m => {
        if(geoOwners.get(m.geometry) > 1){ m.geometry = m.geometry.clone(); }
        worldScaleBoxUVs(m, meters);
      });
      if(!isBlock){ mat.map = plaster.map; mat.needsUpdate = true; }
    });

    // --- emissives a bit hotter so bloom picks up neon, screens and fixtures
    if(Q.bloom){
      users.forEach((meshes, mat) => {
        if(mat.emissive && mat.emissive.getHex() !== 0 && mat.emissiveIntensity >= 0.3) mat.emissiveIntensity *= 1.9;
        if(mat.isMeshBasicMaterial && mat.map && mat.map.userData && mat.map.userData.glow) mat.color.multiplyScalar(mat.map.userData.glow);
      });
    }

    // --- lights
    sun.color.setHex(0xffe7c2); sun.intensity = Q.lambert ? 0.45 : 0.85;
    sun.position.set(26, 38, 12);
    sun.target.position.set(0,0,0); scene.add(sun.target);
    const sunDir = sun.position.clone().normalize();
    if(Q.shadows){
      renderer.shadowMap.enabled = true;
      sun.castShadow = true;
      sun.shadow.mapSize.set(Q.shadowSize, Q.shadowSize);
      const sc = sun.shadow.camera; sc.left = -64; sc.right = 64; sc.top = 64; sc.bottom = -64; sc.near = 1; sc.far = 140;
      sun.position.copy(sunDir.clone().multiplyScalar(70));
      sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.04;
      sc.updateProjectionMatrix();
      sun.shadow.autoUpdate = false; sun.shadow.needsUpdate = true; sunRef = sun; // refreshed every other frame
    }
    rim.intensity = 0.12;
    scene.traverse(o => {
      if(o.isAmbientLight) o.intensity *= Q.lambert ? 1.05 : (Q.env ? 0.7 : 0.95);
      if(o.isHemisphereLight){ o.intensity *= Q.env ? 0.75 : 1.0; }
    });

    // static point lights (everything currently in the scene)
    scene.updateMatrixWorld(true);
    staticLights = []; shadowLights = [];
    scene.traverse(o => { if(o.isPointLight && !o.userData.pooled){ o.userData._wp = o.getWorldPosition(new T.Vector3()); staticLights.push(o); } });
    if(Q.shadows && Q.pointShadows > 0){
      // the main fluorescent banks over the ground-floor corridors cast soft, static shadows
      const fixtures = staticLights.filter(l => Math.abs(l.userData._wp.y - (FLOOR2_Y-0.3)) < 0.05 && (l.distance||0) >= 15)
        .sort((a,b) => (Math.hypot(a.userData._wp.x,a.userData._wp.z)) - (Math.hypot(b.userData._wp.x,b.userData._wp.z)))
        .slice(0, Q.pointShadows);
      fixtures.forEach(l => {
        l.castShadow = true; l.shadow.mapSize.set(512,512); l.shadow.bias = -0.002; l.shadow.radius = 3;
        l.shadow.camera.near = 0.2; l.shadow.camera.far = 18; l.shadow.autoUpdate = false; l.shadow.needsUpdate = true;
        shadowLights.push(l);
      });
      staticLights = staticLights.filter(l => !shadowLights.includes(l));
    }
    initLightPool(scene);

    // --- shadows on meshes
    markShadows(scene);

    // --- light shafts & dust (upstairs, under the skylight)
    const roofY = FLOOR2_Y + 9;
    shaftMat = Q.shafts ? makeShafts(scene, sunDir, FLOOR2_Y, roofY - 0.6) : null;
    dustMat = makeDust(scene, Q.dust, FLOOR2_Y + 0.2, roofY - 1);
    // the ground floor gets a lower, dimmer layer of floating dust too
    dustMat2 = Q.dust ? makeDust(scene, Math.floor(Q.dust*0.5), 0.2, FLOOR2_Y - 0.4) : null;

    // --- reflections: capture the mall itself into an environment map
    if(Q.env){
      setTimeout(() => captureEnvironment(scene, renderer), 600);
    }

    // skylight casts patterned mullion shadows
    scene.traverse(o => {
      if(o.isMesh && o.material && o.material.map && o.position && Math.abs(o.position.y - roofY) < 0.01 && o.geometry.type === 'PlaneGeometry'){
        // the glass itself shouldn't block the sun — only the metal mullions. three.js copies the
        // visible material's alphaTest onto the shadow material, so cast from an invisible twin instead
        o.castShadow = false; o.receiveShadow = false;
        if(Q.shadows){
          const twin = new T.Mesh(o.geometry, new T.MeshBasicMaterial({ map:o.material.map, alphaTest:0.5, colorWrite:false, depthWrite:false, side:T.DoubleSide }));
          twin.position.copy(o.position); twin.rotation.copy(o.rotation); twin.scale.copy(o.scale);
          twin.castShadow = true; twin.userData._sh = true; twin.renderOrder = -1;
          o.parent.add(twin);
        }
        skylightMesh = o;
      }
    });

    console.log('[DMA] graphics enhanced in', Math.round(performance.now()-t0), 'ms — preset', Q.name, '— lights', staticLights.length, '+', shadowLights.length, 'shadowed');
  }
  let shaftMat = null, dustMat = null, dustMat2 = null, skylightMesh = null, sceneRef = null, sunRef = null, frameNo = 0;

  const _box = new T.Box3();
  let FLOOR2 = 5.5;
  function markShadows(root, dynamic){
    if(!Q.shadows) return;
    root.updateMatrixWorld(true);
    root.traverse(o => {
      if(!o.isMesh || o.userData._sh) return;
      o.userData._sh = true;
      if(o.userData.noShadow) return;
      const m = o.material;
      if(!m || Array.isArray(m)) return;
      const lit = m.isMeshStandardMaterial || m.isMeshLambertMaterial;
      o.receiveShadow = lit;
      o.castShadow = lit && !o.userData.noCast && !(m.transparent && m.opacity < 0.6);
      if(o.castShadow){
        // layer 1 = "can be hit by sunlight": anything reaching above the ground-floor ceiling, plus anything that moves
        let dyn = dynamic;
        for(let p = o.parent; p && !dyn; p = p.parent){ if(p.userData && (p.userData.isRemote || p.userData.isBot)) dyn = true; }
        if(dyn) o.layers.enable(1);
        else { _box.setFromObject(o); if(_box.max.y > FLOOR2 - 0.05) o.layers.enable(1); }
      }
    });
  }

  function captureEnvironment(scene, renderer){
    try{
      const cubeRT = new T.WebGLCubeRenderTarget(256, { type:T.HalfFloatType });
      const cc = new T.CubeCamera(0.1, 120, cubeRT);
      cc.position.set(0, 2.4, -3);
      const hidden = [];
      scene.traverse(o => { if((o.isSprite || o.isPoints) && o.visible){ o.visible = false; hidden.push(o); } });
      const fog = scene.fog; scene.fog = null;
      cc.update(renderer, scene);
      scene.fog = fog;
      hidden.forEach(o => o.visible = true);
      const pm = new T.PMREMGenerator(renderer);
      const env = pm.fromCubemap(cubeRT.texture).texture;
      scene.environment = env;
      DMA.allMaterials.forEach(m => { if(m.envMapIntensity !== undefined && !m.userData._envSet){ m.envMapIntensity = m.envMapIntensity === 1 ? 0.55 : m.envMapIntensity; m.userData._envSet = true; } });
      cubeRT.dispose(); pm.dispose();
    }catch(e){ console.warn('env capture failed', e); }
  }

  let shadowRound = 0, lastShadowRefresh = 0, lastMark = 0;
  function frame(camera, now){
    const t = now/1000;
    if(shaftMat) shaftMat.uniforms.time.value = t;
    if(dustMat) dustMat.uniforms.time.value = t;
    if(dustMat2) dustMat2.uniforms.time.value = t;
    updateLights(camera);
    if(sunRef && (++frameNo % 2 === 0)) sunRef.shadow.needsUpdate = true;
    // refresh one static point shadow at a time, slowly — characters walking under a fixture still show up
    if(shadowLights.length && now - lastShadowRefresh > 400){
      lastShadowRefresh = now;
      shadowLights[shadowRound++ % shadowLights.length].shadow.needsUpdate = true;
    }
    if(now - lastMark > 1500){ lastMark = now; if(sceneRef) markShadows(sceneRef, true); }
  }

  /* ---------------- static batching ----------------
     The mall is ~1,800 separate meshes. Everything that never moves gets merged into a few
     big meshes per area and look, cutting draw calls from ~500 to well under 100 — the
     single biggest win on the Raspberry Pi. The originals stay in the scene (hidden) so
     bullets, line of sight and collisions work exactly as before. */
  function shownChain(o){ for(let p=o; p; p=p.parent){ if(!p.visible) return false; } return true; }
  function snapshotStatic(scene){
    scene.updateMatrixWorld(true);
    const m = new Map();
    scene.traverse(o => { if(o.isMesh) m.set(o, { e: o.matrixWorld.elements.slice(), v: shownChain(o), mv: o.material && o.material.version }); });
    return m;
  }
  function matSignature(mat){
    // materials that look identical can share one draw call; glowing/animated ones keep their own
    if(mat.emissive && mat.emissive.getHex() !== 0) return 'u:' + mat.uuid;
    const c = mat.color ? mat.color.getHexString() : '';
    return [mat.type, c, mat.map ? mat.map.uuid : '', mat.normalMap ? mat.normalMap.uuid : '', mat.roughnessMap ? mat.roughnessMap.uuid : '',
      (mat.roughness||0).toFixed(2), (mat.metalness||0).toFixed(2), mat.side, mat.envMapIntensity !== undefined ? mat.envMapIntensity.toFixed(2) : '',
      mat.polygonOffset ? 1 : 0, mat.vertexColors ? 1 : 0, mat.flatShading ? 1 : 0].join('|');
  }
  function mergeStatic(scene, first, excludeRoots){
    const merge = DMA.mergeGeometries;
    if(!merge) return 0;
    const second = snapshotStatic(scene);
    const excluded = new Set();
    excludeRoots.forEach(r => { if(r) (r.isObject3D ? r : null) && r.traverse(o => excluded.add(o)); });
    const CELL = Q.lambert ? 56 : 28, groups = new Map(), wp = new T.Vector3();
    let before = 0;
    second.forEach((s, o) => {
      const f = first.get(o);
      if(!f || !s.v || !f.v || excluded.has(o) || o.isInstancedMesh || o.isSkinnedMesh) return;
      for(let i=0;i<16;i++){ if(Math.abs(f.e[i]-s.e[i]) > 1e-6) return; }
      const mat = o.material, g = o.geometry;
      if(!mat || Array.isArray(mat) || mat.isShaderMaterial || mat.transparent || mat.alphaTest > 0 || f.mv !== s.mv) return;
      if(!g || !g.index || !g.attributes.position || !g.attributes.normal || !g.attributes.uv || g.morphAttributes.position) return;
      if(o.customDepthMaterial || o.renderOrder !== 0 || o.userData.noMerge) return;
      for(let p=o.parent; p; p=p.parent){ if(p.userData && (p.userData.isRemote || p.userData.isBot)) return; }
      o.getWorldPosition(wp);
      const key = matSignature(mat) + '#' + o.castShadow + o.receiveShadow + o.layers.mask + '#' + Math.floor(wp.x/CELL) + ',' + Math.floor(wp.z/CELL) + ',' + (wp.y > 5.4 ? 1 : 0);
      if(!groups.has(key)) groups.set(key, { mat, list: [] });
      groups.get(key).list.push(o);
      before++;
    });
    let made = 0, merged = 0;
    groups.forEach(({mat, list}) => {
      if(list.length < 2) return;
      const geos = list.map(o => {
        const g = o.geometry.clone();
        Object.keys(g.attributes).forEach(n => { if(n !== 'position' && n !== 'normal' && n !== 'uv') g.deleteAttribute(n); });
        g.morphAttributes = {};
        g.applyMatrix4(o.matrixWorld);
        return g;
      });
      let mg = null;
      try{ mg = merge(geos, false); }catch(e){ mg = null; }
      geos.forEach(g => g.dispose());
      if(!mg) return;
      mg.computeBoundingSphere(); mg.computeBoundingBox();
      const m = new T.Mesh(mg, mat);
      m.castShadow = list[0].castShadow; m.receiveShadow = list[0].receiveShadow;
      m.layers.mask = list[0].layers.mask;
      m.matrixAutoUpdate = false; m.updateMatrix();
      m.userData._sh = true; m.userData.merged = true;
      scene.add(m);
      list.forEach(o => { o.visible = false; o.userData.mergedAway = true; });
      made++; merged += list.length;
    });
    console.log('[DMA] batched', merged, 'static meshes into', made);
    return merged;
  }

  window.DMAGfx = { enhance, frame, flash, markShadows, Q, snapshotStatic, mergeStatic };
})();
