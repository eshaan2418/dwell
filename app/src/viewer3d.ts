/**
 * three.js view of a unit. All report geometry is built in ENU coordinates inside `world`, whose
 * matrix converts ENU (x east, y north, z up) → three.js (y up); see geo.ts.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import { roomName, type Report, type XY } from './data/schema';
import { ENU_TO_THREE_MATRIX, enuToThree, sunDirectionThree } from './geo';

const ROOM_COLORS: Record<string, number> = {
  bedroom: 0x8fb3d9, living: 0xc9b58f, kitchen: 0xa8c98f, bathroom: 0xb7a3d1, office: 0xd1a3a3,
};

function shapeFrom(poly: XY[]): THREE.Shape {
  return new THREE.Shape(poly.map(([x, y]) => new THREE.Vector2(x, y)));
}

function disposeTree(obj: THREE.Object3D): void {
  obj.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose?.();
    const mat = m.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
    else mat?.dispose?.();
    if (o instanceof CSS2DObject) o.element.remove();
  });
}

export class Viewer3D {
  private renderer: THREE.WebGLRenderer;
  private labels: CSS2DRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(45, 1, 0.5, 5000);
  private controls: OrbitControls;
  private world = new THREE.Group();
  private patches = new THREE.Group();
  private sunLight = new THREE.DirectionalLight(0xfff2d0, 1.6);
  private sunMarker = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffc400 }));
  private hemi = new THREE.HemisphereLight(0xdfe9ff, 0x404040, 0.9);
  private report: Report | null = null;
  private center = new THREE.Vector3();
  private radius = 20;
  private resizeObs: ResizeObserver;
  private raf = 0;
  private patchMat = new THREE.MeshBasicMaterial({
    color: 0xffd400, transparent: true, opacity: 0.75, side: THREE.DoubleSide, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2,
  });

  constructor(private container: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0xe8eef4);
    container.append(this.renderer.domElement);
    this.renderer.domElement.setAttribute('aria-label', '3D view of the unit and its surroundings. Drag to orbit, scroll or pinch to zoom.');
    this.renderer.domElement.setAttribute('role', 'img');
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'labels';
    container.append(this.labels.domElement);

    this.world.matrixAutoUpdate = false;
    this.world.matrix.fromArray(ENU_TO_THREE_MATRIX);
    this.world.add(this.patches);
    this.scene.add(this.world, this.hemi, this.sunLight, this.sunLight.target, this.sunMarker);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.495;

    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(container);
    this.resize();
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this.labels.render(this.scene, this.camera);
    };
    loop();
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.resizeObs.disconnect();
    this.controls.dispose();
    disposeTree(this.scene);
    this.renderer.dispose();
    this.container.replaceChildren();
  }

  private resize(): void {
    const w = this.container.clientWidth || 300;
    const hgt = this.container.clientHeight || 300;
    this.renderer.setSize(w, hgt);
    this.labels.setSize(w, hgt);
    this.camera.aspect = w / hgt;
    this.camera.updateProjectionMatrix();
  }

  setReport(r: Report): void {
    this.report = r;
    for (const child of [...this.world.children]) {
      if (child === this.patches) continue;
      this.world.remove(child);
      disposeTree(child);
    }
    const g = r.geometry;

    // ground
    const ground = new THREE.Mesh(new THREE.CircleGeometry(220, 48), new THREE.MeshLambertMaterial({ color: 0xd7dccf }));
    ground.position.z = -0.02;
    this.world.add(ground);

    // context buildings (own building as a faint ghost so the unit stays visible)
    const ctxMat = new THREE.MeshLambertMaterial({ color: 0x9aa0a6 });
    const ownMat = new THREE.MeshLambertMaterial({ color: 0xb0b6bc, transparent: true, opacity: 0.18, depthWrite: false });
    for (const b of g.context_buildings ?? []) {
      if (b.height <= 0) continue;
      const geo = new THREE.ExtrudeGeometry(shapeFrom(b.footprint), { depth: b.height, bevelEnabled: false });
      const mesh = new THREE.Mesh(geo, b.own ? ownMat : ctxMat);
      this.world.add(mesh);
      if (b.own) this.world.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x6b7178 })));
    }

    // roads
    for (const rd of g.roads ?? []) {
      const pts = rd.coords.map(([x, y]) => new THREE.Vector3(x, y, 0.05));
      const color = rd.road_class === 'primary' || rd.road_class === 'trunk' ? 0x404040 : 0x707070;
      this.world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color })));
    }

    // trees: cone + sphere crown; ConeGeometry axis is +Y in object space → rotate onto ENU +z
    const trunkMat = new THREE.MeshLambertMaterial({ color: 0x7a5a3a });
    const crownMat = new THREE.MeshLambertMaterial({ color: 0x4f8a4a });
    for (const t of g.trees ?? []) {
      const tree = new THREE.Group();
      const trunkH = t.height * 0.35;
      const trunk = new THREE.Mesh(new THREE.ConeGeometry(Math.max(0.15, t.radius * 0.08), trunkH, 6), trunkMat);
      trunk.position.y = trunkH / 2;
      const crown = new THREE.Mesh(new THREE.SphereGeometry(t.radius, 10, 8), crownMat);
      crown.position.y = Math.max(trunkH, t.height - t.radius);
      tree.add(trunk, crown);
      tree.rotation.x = Math.PI / 2;
      tree.position.set(t.x, t.y, 0);
      this.world.add(tree);
    }

    // rooms: floor slab + wireframe volume + label
    const box = new THREE.Box3();
    for (const room of g.rooms) {
      const shape = shapeFrom(room.polygon);
      const slab = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.08, bevelEnabled: false }),
        new THREE.MeshLambertMaterial({ color: ROOM_COLORS[room.kind] ?? 0xcfcfcf }));
      slab.position.z = room.floor_z - 0.08;
      const vol = new THREE.ExtrudeGeometry(shape, { depth: room.ceiling_height, bevelEnabled: false });
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(vol), new THREE.LineBasicMaterial({ color: 0x2b3a4a }));
      vol.dispose();
      edges.position.z = room.floor_z;
      this.world.add(slab, edges);

      const cx = room.polygon.reduce((s, p) => s + p[0], 0) / room.polygon.length;
      const cy = room.polygon.reduce((s, p) => s + p[1], 0) / room.polygon.length;
      const el = document.createElement('div');
      el.className = 'room-label';
      el.textContent = roomName(room);
      const label = new CSS2DObject(el);
      label.position.set(cx, cy, room.floor_z + room.ceiling_height + 0.4);
      this.world.add(label);
      for (const [x, y] of room.polygon) {
        box.expandByPoint(new THREE.Vector3(...enuToThree(x, y, room.floor_z)));
        box.expandByPoint(new THREE.Vector3(...enuToThree(x, y, room.floor_z + room.ceiling_height)));
      }
    }

    // windows as translucent quads
    const winMat = new THREE.MeshBasicMaterial({ color: 0x3aa0ff, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthWrite: false });
    for (const w of g.windows) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(w.corners.flat(), 3));
      geo.setIndex([0, 1, 2, 0, 2, 3]);
      this.world.add(new THREE.Mesh(geo, winMat));
      const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(w.corners.map((c) => new THREE.Vector3(...c))),
        new THREE.LineBasicMaterial({ color: 0x0a4f9a }));
      this.world.add(outline);
    }

    // camera framing: look at the unit from the south-east, above
    box.getCenter(this.center);
    this.radius = Math.max(8, box.getSize(new THREE.Vector3()).length());
    const d = this.radius * 3.2;
    const [ex, ey, ez] = enuToThree(0.6, -0.8, 0.7);
    this.camera.position.set(this.center.x + ex * d, this.center.y + ey * d, this.center.z + ez * d);
    this.controls.target.copy(this.center);
    this.controls.maxDistance = 600;
    this.controls.update();
    this.sunMarker.scale.setScalar(Math.max(0.6, this.radius * 0.06));
  }

  /** Show sun direction + floor sun patches for (dateIdx, hourIdx). Returns the sun's [az, el]. */
  setSun(dateIdx: number, hourIdx: number): [number, number] | null {
    const r = this.report;
    for (const c of [...this.patches.children]) {
      this.patches.remove(c);
      (c as THREE.Mesh).geometry.dispose();
    }
    if (!r) return null;
    const pos = r.sun.sun_position[dateIdx]?.[hourIdx];
    if (!pos) return null;
    const [az, el] = pos;
    const up = el > 0;
    const dir = new THREE.Vector3(...sunDirectionThree(az, el));
    const dist = this.radius * 3;
    this.sunMarker.visible = up;
    this.sunMarker.position.copy(this.center).addScaledVector(dir, dist);
    this.sunLight.position.copy(this.center).addScaledVector(dir, dist);
    this.sunLight.target.position.copy(this.center);
    this.sunLight.intensity = up ? 0.4 + 1.4 * Math.sin((Math.min(el, 60) * Math.PI) / 180) : 0;
    this.hemi.intensity = up ? 0.9 : 0.45;

    const rooms = new Map(r.geometry.rooms.map((rm) => [rm.id, rm]));
    for (const [roomId, perDate] of Object.entries(r.sun.patches)) {
      const poly = perDate[dateIdx]?.[hourIdx];
      const room = rooms.get(roomId);
      if (!poly || !room) continue;
      const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shapeFrom(poly)), this.patchMat);
      mesh.position.z = room.floor_z + 0.03;
      mesh.renderOrder = 2;
      this.patches.add(mesh);
    }
    return [az, el];
  }
}
