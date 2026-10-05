// Shapewright 3D viewer (three.js): used by the workbench and by the docs gallery.
// For people only: the CPU renderer stays the reference for agents, tests and goldens.
// The page provides an import map for "three" and "three/addons/" (vendored in the workbench, a CDN on the site).
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

export const MODES = ["textured", "clay", "material", "parts", "normals", "uv_checker", "texel"];

const PALETTE = [0xe65c4d, 0x408cd9, 0x59b861, 0xf2b333, 0x9e6bcc, 0x33bfbf, 0xe680b3, 0x8c8c40, 0x6666bf, 0xd99973, 0x4d7359, 0xb34073];

function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function checkerTexture(cells = 16) {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const g = c.getContext("2d");
  const s = 512 / cells;
  for (let y = 0; y < cells; y++) for (let x = 0; x < cells; x++) {
    g.fillStyle = (x + y) % 2 ? "#2b3a55" : "#e8e4da";
    g.fillRect(x * s, y * s, s, s);
  }
  g.fillStyle = "#d9534f"; g.fillRect(0, 0, s, s);  // a red corner shows flipped or rotated charts
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(12, 12);  // 192 cells across the atlas: stretching shows as uneven squares
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// the part a mesh belongs to: glTF splits a multi-material node into child meshes "<node>_1", "<node>_2"...
function partName(obj) {
  const p = obj.parent;
  if (obj.isMesh && p && p.name && p.type !== "Scene" && (!obj.name || obj.name.startsWith(p.name + "_"))) return p.name;
  return obj.name || "";
}

export function createViewer(container, opts = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);
  renderer.domElement.style.display = "block";
  renderer.domElement.style.width = "100%";
  renderer.domElement.style.height = "100%";

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(opts.background || 0xecebe7);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  scene.add(sun, sun.target);
  scene.add(new THREE.HemisphereLight(0xdfe6f2, 0x5a5048, 0.35));
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.22 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  let grid = null, figure = null, marker = null, model = null, wires = [], box = null;
  let mixer = null, clips = [], action = null, skelHelper = null, weightBone = null;  // Phase 24: rigged characters
  const clock = new THREE.Clock();
  const originals = new Map();
  const state = { mode: "textured", wire: false, grid: true, figure: false };
  const checker = checkerTexture();

  function resize() {
    const w = container.clientWidth || 600, h = container.clientHeight || 400;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  function frame() {
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
    const r = Math.max(size.length() / 2, 0.05);
    const dist = r / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.1;
    const dir = new THREE.Vector3(Math.sin(0.61) * Math.cos(0.38), Math.sin(0.38), Math.cos(0.61) * Math.cos(0.38));
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.near = dist / 100; camera.far = dist * 20; camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
    const span = Math.max(size.x, size.z, 1) * 4;
    ground.scale.set(span, span, 1);
    ground.position.set(center.x, box.min.y, center.z);
    sun.position.copy(center).add(new THREE.Vector3(-0.6, 1.0, 0.45).multiplyScalar(r * 4));
    sun.target.position.copy(center);
    const s = sun.shadow.camera;
    s.left = s.bottom = -r * 1.6; s.right = s.top = r * 1.6; s.near = 0.01; s.far = r * 10; s.updateProjectionMatrix();
    if (grid) scene.remove(grid);
    const cells = Math.max(2, Math.ceil(Math.max(size.x, size.z) + 2));
    grid = new THREE.GridHelper(cells, cells, 0x9a968c, 0xc9c5bb);  // 1 m cells
    grid.position.set(Math.round(center.x), box.min.y + 0.001, Math.round(center.z));
    grid.visible = state.grid;
    scene.add(grid);
    placeFigure();
  }

  function placeFigure() {
    if (figure) scene.remove(figure);
    // a 1.75 m person beside the model: capsule body (radius 0.2) + head
    figure = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: 0x8a8a8a, roughness: 0.9 });
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 1.02, 6, 16), mat);
    body.position.y = 0.19 + 0.51 + 0.0;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 14), mat);
    head.position.y = 1.75 - 0.11;
    figure.add(body, head);
    figure.traverse(o => { o.castShadow = true; });
    figure.position.set(box.max.x + 0.6, box.min.y, (box.min.z + box.max.z) / 2);
    figure.visible = state.figure;
    scene.add(figure);
  }

  function materialFor(mesh, mode) {
    const orig = originals.get(mesh);
    const name = partName(mesh);
    switch (mode) {
      case "clay": return new THREE.MeshStandardMaterial({ color: 0xa8a097, roughness: 0.9 });
      case "material": return (Array.isArray(orig) ? orig : [orig]).map(m => new THREE.MeshStandardMaterial({ color: m.color ? m.color.clone() : 0xcccccc, roughness: 0.8 }));
      case "parts": return new THREE.MeshStandardMaterial({ color: PALETTE[hash(name) % PALETTE.length], roughness: 0.75 });
      case "normals": return new THREE.MeshNormalMaterial();
      case "uv_checker": return new THREE.MeshBasicMaterial({ map: checker });
      case "texel": return new THREE.MeshBasicMaterial({ vertexColors: true });
      case "weights": return new THREE.MeshLambertMaterial({ vertexColors: true });
      default: return orig;
    }
  }

  function texelColors(mesh) {
    // texels per metre per triangle (atlas resolution x UV area vs world area), coloured relative to the median
    if (mesh.userData.texelGeom) return mesh.userData.texelGeom;
    const g = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
    const pos = g.getAttribute("position"), uv = g.getAttribute("uv");
    const orig = originals.get(mesh);
    const map = (Array.isArray(orig) ? orig[0] : orig).map;
    const res = (map && map.image && map.image.width) || 1024;
    const n = pos.count / 3, dens = new Float32Array(n);
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    mesh.updateWorldMatrix(true, false);
    for (let i = 0; i < n; i++) {
      a.fromBufferAttribute(pos, 3 * i).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(pos, 3 * i + 1).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(pos, 3 * i + 2).applyMatrix4(mesh.matrixWorld);
      const area = b.clone().sub(a).cross(c.clone().sub(a)).length() / 2;
      let uvA = 0;
      if (uv) {
        const [u0, v0, u1, v1, u2, v2] = [uv.getX(3 * i), uv.getY(3 * i), uv.getX(3 * i + 1), uv.getY(3 * i + 1), uv.getX(3 * i + 2), uv.getY(3 * i + 2)];
        uvA = Math.abs((u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0)) / 2;
      }
      dens[i] = area > 1e-9 ? Math.sqrt(uvA * res * res / area) : 0;
    }
    g.userData.density = dens;
    mesh.userData.texelGeom = g;
    return g;
  }

  function applyTexelColors() {
    const all = [];
    model.traverse(o => { if (o.isMesh) all.push(...texelColors(o).userData.density); });
    const sorted = all.filter(x => x > 0).sort((p, q) => p - q);
    const med = sorted[Math.floor(sorted.length / 2)] || 1;
    model.traverse(o => {
      if (!o.isMesh) return;
      const g = texelColors(o), d = g.userData.density, col = new Float32Array(d.length * 9);
      const tmp = new THREE.Color();
      for (let i = 0; i < d.length; i++) {
        const t = d[i] ? Math.max(-1, Math.min(1, Math.log2(d[i] / med))) : -1;  // half the median: blue, double: red
        tmp.setHSL((1 - (t + 1) / 2) * 0.66, 0.75, d[i] ? 0.5 : 0.15);
        for (let k = 0; k < 3; k++) col.set([tmp.r, tmp.g, tmp.b], 9 * i + 3 * k);
      }
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    });
    return med;
  }

  function setMode(mode) {
    state.mode = mode;
    if (!model) return;
    let info = "";
    if (mode === "texel") info = `median ${applyTexelColors().toFixed(0)} px/m: blue = half, red = double`;
    if (mode === "weights") info = applyWeightColors();
    model.traverse(o => {
      if (!o.isMesh) return;
      if (mode === "texel") { o.userData.geom0 ??= o.geometry; o.geometry = texelColors(o); }
      else if (o.userData.geom0) o.geometry = o.userData.geom0;
      o.material = materialFor(o, mode);
    });
    return info;
  }

  function boneNames() {
    const names = [];
    model && model.traverse(o => { if (o.isSkinnedMesh) o.skeleton.bones.forEach(b => names.includes(b.name) || names.push(b.name)); });
    return names;
  }

  function applyWeightColors() {
    // skinning weight of one joint per vertex (skinIndex / skinWeight), blue 0 -> red 1; unskinned meshes grey
    const bone = weightBone || boneNames()[0];
    if (!bone) return "no skeleton in this file";
    const tmp = new THREE.Color();
    model.traverse(o => {
      if (!o.isMesh) return;
      const g = o.geometry, n = g.getAttribute("position").count, col = new Float32Array(n * 3);
      const si = g.getAttribute("skinIndex"), sw = g.getAttribute("skinWeight");
      const j = o.isSkinnedMesh ? o.skeleton.bones.findIndex(b => b.name === bone) : -1;
      for (let i = 0; i < n; i++) {
        let w = -1;
        if (si && sw && j >= 0) { w = 0; for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === j) w += sw.getComponent(i, k); }
        if (w < 0) tmp.setRGB(0.66, 0.63, 0.59); else tmp.setHSL((1 - w) * 0.66, 0.8, 0.5);
        col.set([tmp.r, tmp.g, tmp.b], 3 * i);
      }
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    });
    return `weights of ${bone}: blue 0, red 1`;
  }

  function setSkeleton(on) {
    if (skelHelper) { scene.remove(skelHelper); skelHelper = null; }
    if (!on || !model || !boneNames().length) return;
    skelHelper = new THREE.SkeletonHelper(model);
    skelHelper.material.depthTest = false;  // drawn over the body
    skelHelper.material.linewidth = 2;
    scene.add(skelHelper);
  }

  function play(name) {
    if (action) { action.stop(); action = null; }
    if (!mixer || !name) return;
    const clip = clips.find(c => c.name === name);
    if (!clip) return;
    action = mixer.clipAction(clip);
    action.play();
  }

  function scrub(fraction) {  // pause on one moment of the playing clip (a pose slider)
    if (!action) return;
    action.paused = true;
    action.time = fraction * action.getClip().duration;
    mixer.update(0);
  }

  function setWire(on) {
    state.wire = on;
    wires.forEach(w => w.parent && w.parent.remove(w));
    wires = [];
    if (!on || !model) return;
    model.traverse(o => {
      if (!o.isMesh) return;
      const w = new THREE.LineSegments(new THREE.WireframeGeometry(o.userData.geom0 || o.geometry),
        new THREE.LineBasicMaterial({ color: 0x1d2a44, transparent: true, opacity: 0.45 }));
      o.add(w); wires.push(w);
    });
  }

  function load(url) {
    return new Promise((resolve, reject) => {
      new GLTFLoader().load(url, gltf => {
        if (model) scene.remove(model);
        originals.clear();
        model = gltf.scene;
        model.traverse(o => { if (o.isMesh) { originals.set(o, o.material); o.castShadow = o.receiveShadow = true; } });
        clips = gltf.animations || [];
        mixer = clips.length ? new THREE.AnimationMixer(model) : null;
        action = null;
        if (skelHelper) setSkeleton(true);
        scene.add(model);
        const first = !box;
        box = new THREE.Box3().setFromObject(model);
        if (first || opts.reframe) frame(); else { placeFigure(); }
        setMode(state.mode);
        setWire(state.wire);
        resolve(model);
      }, undefined, reject);
    });
  }

  // picking: a click (not a drag) on the model reports the part, the point and the surface normal
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || !model || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObject(model, true).find(h => h.object.isMesh);
    if (!hit) return;
    const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
    if (marker) scene.remove(marker);
    const rad = Math.max(box.getSize(new THREE.Vector3()).length() * 0.008, 0.005);
    marker = new THREE.Mesh(new THREE.SphereGeometry(rad, 16, 12), new THREE.MeshBasicMaterial({ color: 0xff3b30, depthTest: false }));
    marker.renderOrder = 10;
    marker.position.copy(hit.point);
    scene.add(marker);
    opts.onPick && opts.onPick({ part: partName(hit.object), point: hit.point.toArray(), normal: n.toArray(), uv: hit.uv ? hit.uv.toArray() : null });
  });

  function uvLayout(canvas, part) {
    // UV triangles of one part (zoomed to its charts, with the atlas outline) or of every part
    const g = canvas.getContext("2d"), S = canvas.width;
    g.fillStyle = "#f6f5f2"; g.fillRect(0, 0, S, S);
    if (!model) return 0;
    const tris = [];
    model.traverse(o => {
      if (!o.isMesh) return;
      const name = partName(o);
      if (part && name !== part) return;
      const geom = o.userData.geom0 || o.geometry, uv = geom.getAttribute("uv");
      if (!uv) return;
      const idx = geom.index ? geom.index.array : null, count = idx ? idx.length : uv.count;
      for (let i = 0; i < count; i += 3) {
        const t = [];
        for (let k = 0; k < 3; k++) { const j = idx ? idx[i + k] : i + k; t.push(uv.getX(j), uv.getY(j)); }  // glTF UV origin: top-left
        tris.push(t);
      }
    });
    let x0 = 0, y0 = 0, span = 1;
    if (part && tris.length) {
      const xs = tris.flatMap(t => [t[0], t[2], t[4]]), ys = tris.flatMap(t => [t[1], t[3], t[5]]);
      x0 = Math.min(...xs); y0 = Math.min(...ys);
      span = Math.max(Math.max(...xs) - x0, Math.max(...ys) - y0, 1e-4) * 1.15;
      x0 -= span * 0.065; y0 -= span * 0.065;
    }
    const X = u => (u - x0) / span * S, Y = v => (v - y0) / span * S;
    g.strokeStyle = "#999"; g.strokeRect(X(0) + 0.5, Y(0) + 0.5, (X(1) - X(0)) - 1, (Y(1) - Y(0)) - 1);
    g.fillStyle = part ? "rgba(64,140,217,0.35)" : "rgba(64,140,217,0.18)";
    g.strokeStyle = "rgba(29,42,68,0.6)";
    g.lineWidth = 0.7;
    for (const t of tris) {
      g.beginPath(); g.moveTo(X(t[0]), Y(t[1])); g.lineTo(X(t[2]), Y(t[3])); g.lineTo(X(t[4]), Y(t[5])); g.closePath(); g.fill(); g.stroke();
    }
    return tris.length;
  }

  function screenshot() {
    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  }

  function loop() {
    controls.update();
    if (mixer) mixer.update(clock.getDelta()); else clock.getDelta();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }
  loop();

  return {
    load, setMode, setWire, uvLayout, screenshot, play, scrub, setSkeleton,
    clips() { return clips.map(c => c.name); },
    bones: boneNames,
    setWeightBone(name) { weightBone = name; return state.mode === "weights" ? applyWeightColors() : ""; },
    setGrid(on) { state.grid = on; if (grid) grid.visible = on; },
    setFigure(on) { state.figure = on; if (figure) figure.visible = on; },
    reframe() { if (box) frame(); },
    clearMarker() { if (marker) scene.remove(marker); marker = null; },
    get state() { return { ...state }; },
  };
}
