// The Z-up view cube: its own small renderer, face labels, and click-to-view picking.
import * as THREE from "three";
import { S } from "./state.js";
import {
  bindProjectionCamera,
  camera,
  fitView,
  goNamedView,
  goToView,
  lookAtScene,
  namedViewFromDir,
  syncViewMenu,
} from "./camera.js";
import { setHint } from "./cmdline.js";
import { t } from "./strings.js";
import { INK, chromeColors } from "./theme.js";
import { ISO_DIR, WORLD_UP, viewUp } from "./viewport.js";

const cubeCanvas = document.getElementById("viewcube");
const cubeRenderer = new THREE.WebGLRenderer({
  canvas: cubeCanvas,
  antialias: true,
  alpha: true,
});

cubeRenderer.setPixelRatio(window.devicePixelRatio);
cubeRenderer.setClearAlpha(0);
const cubeScene = new THREE.Scene();
const cubeCam = new THREE.OrthographicCamera(-1.35, 1.35, 1.35, -1.35, 0.1, 20);
cubeCam.up.copy(WORLD_UP);
const cubeGroup = new THREE.Group();
cubeScene.add(cubeGroup);

// Face colours and type follow the chrome tokens; restyleCube() repaints them.
function makeFaceTexture(label) {
  const colors = chromeColors();
  const canvasFace = document.createElement("canvas");
  canvasFace.width = 256;
  canvasFace.height = 256;
  const ctx = canvasFace.getContext("2d");
  ctx.fillStyle = colors.surface;
  ctx.fillRect(0, 0, 256, 256);
  ctx.strokeStyle = colors.line;
  ctx.lineWidth = 10;
  ctx.strokeRect(6, 6, 244, 244);
  ctx.fillStyle = colors.text;
  ctx.font = `600 56px ${colors.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, 128, 128);
  const texture = new THREE.CanvasTexture(canvasFace);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

const CUBE_FACE = 1.12;
const cubeFaces = [];

function addCubeFace(nx, ny, nz, ux, uy, uz, label) {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(CUBE_FACE, CUBE_FACE),
    new THREE.MeshBasicMaterial({ map: makeFaceTexture(label) }),
  );
  mesh.userData.label = label;
  cubeFaces.push(mesh);
  const normal = new THREE.Vector3(nx, ny, nz);
  mesh.position.copy(normal).multiplyScalar(CUBE_FACE / 2);
  mesh.up.set(ux, uy, uz);
  mesh.lookAt(mesh.position.clone().add(normal));
  cubeGroup.add(mesh);
}
addCubeFace(1, 0, 0, 0, 0, 1, "RIGHT");
addCubeFace(-1, 0, 0, 0, 0, 1, "LEFT");
addCubeFace(0, 1, 0, 0, 0, 1, "BACK");
addCubeFace(0, -1, 0, 0, 0, 1, "FRONT");
addCubeFace(0, 0, 1, 0, 1, 0, "TOP");
addCubeFace(0, 0, -1, 0, 1, 0, "BOTTOM");

const cubePick = new THREE.Mesh(
  new THREE.BoxGeometry(CUBE_FACE, CUBE_FACE, CUBE_FACE),
  new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
);
cubeGroup.add(cubePick);
const cubeEdges = new THREE.LineSegments(
  new THREE.EdgesGeometry(cubePick.geometry),
  new THREE.LineBasicMaterial(),
);
cubeGroup.add(cubeEdges);

// Repaint the faces and edges after a theme or canvas change, and once the UI font loads.
export function restyleCube() {
  for (const mesh of cubeFaces) {
    mesh.material.map.dispose();
    mesh.material.map = makeFaceTexture(mesh.userData.label);
    mesh.material.needsUpdate = true;
  }
  cubeEdges.material.color.setHex(INK.ghost);
}

export function syncCube() {
  const cam = camera();
  cubeCam.up.copy(cam.up);
  cubeCam.position.set(0, 0, 0);
  cubeCam.quaternion.copy(cam.quaternion);
  cubeCam.translateZ(3.2);
  cubeCam.updateMatrixWorld();
  const size = Math.max(cubeCanvas.clientWidth, 1);
  cubeRenderer.setSize(size, size, false);
  cubeRenderer.render(cubeScene, cubeCam);
}

function pickCube(event) {
  const rect = cubeCanvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return null;
  const ndc = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndc, cubeCam);
  const hits = raycaster.intersectObject(cubePick, true);
  return hits[0] || null;
}

function viewDirFromCubePoint(point) {
  const local = cubePick.worldToLocal(point.clone());
  const snap = (value) => (Math.abs(value) < 0.42 ? 0 : Math.sign(value));
  let x = snap(local.x);
  let y = snap(local.y);
  let z = snap(local.z);
  if (x === 0 && y === 0 && z === 0) {
    const ax = Math.abs(local.x);
    const ay = Math.abs(local.y);
    const az = Math.abs(local.z);
    if (ax >= ay && ax >= az) x = Math.sign(local.x) || 1;
    else if (ay >= az) y = Math.sign(local.y) || 1;
    else z = Math.sign(local.z) || 1;
  }
  return new THREE.Vector3(x, y, z).normalize();
}

let cubePointer = null;

export function bindViewCube() {
  if (document.fonts) document.fonts.ready.then(() => restyleCube());
  cubeCanvas.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    cubePointer = { x: event.clientX, y: event.clientY };
  });
  cubeCanvas.addEventListener("pointerup", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const origin = cubePointer;
    cubePointer = null;
    if (!origin) return;
    if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 6) return;
    const hit = pickCube(event);
    if (!hit) return;
    const dir = viewDirFromCubePoint(hit.point);
    const name = namedViewFromDir(dir);
    if (name) goNamedView(name);
    else {
      S.namedView = null;
      if (S.projection === "orthographic") {
        S.projection = "parallel";
        S.useOrtho = true;
        bindProjectionCamera();
      }
      viewUp.copy(WORLD_UP);
      goToView(dir, { up: WORLD_UP.clone() });
      syncViewMenu();
    }
  });
  cubeCanvas.addEventListener("pointermove", (event) => {
    cubeCanvas.style.cursor = pickCube(event) ? "pointer" : "default";
  });
  cubeCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
  document.getElementById("view-iso").addEventListener("click", () => {
    S.namedView = null;
    if (S.projection === "orthographic") {
      S.projection = "parallel";
      S.useOrtho = true;
    }
    viewUp.copy(WORLD_UP);
    bindProjectionCamera();
    lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
    setHint(t("view.iso"));
  });
  document.getElementById("view-fit").addEventListener("click", () => fitView());
}
