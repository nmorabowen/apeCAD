// The main three.js viewport: renderer, scene, both cameras, orbit controls, lights, and the
// draft / ghost / preselect groups the rest of the client draws into. Objects only; camera
// behaviour lives in camera.js.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { disposeObject3D, wrapAutoDispose as _wrapAutoDispose } from "./geom.js";
import { requestRender } from "./store.js";

export { disposeObject3D };

export const canvas = document.getElementById("view");

export const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
export const scene = new THREE.Scene();
scene.background = new THREE.Color(); // set from the canvas role by applyViz()

export const WORLD_UP = new THREE.Vector3(0, 0, 1);
export const ISO_DIR = new THREE.Vector3(1, -1, 1);
export const viewUp = new THREE.Vector3(0, 0, 1);
export const VIEW_PRESETS = {
  top: { dir: new THREE.Vector3(0, 0, 1), up: new THREE.Vector3(0, 1, 0), label: "Top" },
  bottom: { dir: new THREE.Vector3(0, 0, -1), up: new THREE.Vector3(0, 1, 0), label: "Bottom" },
  front: { dir: new THREE.Vector3(0, -1, 0), up: WORLD_UP, label: "Front" },
  back: { dir: new THREE.Vector3(0, 1, 0), up: WORLD_UP, label: "Back" },
  right: { dir: new THREE.Vector3(1, 0, 0), up: WORLD_UP, label: "Right" },
  left: { dir: new THREE.Vector3(-1, 0, 0), up: WORLD_UP, label: "Left" },
};

export const persp = new THREE.PerspectiveCamera(50, 1, 10, 2_000_000);
persp.up.copy(WORLD_UP);
persp.position.copy(ISO_DIR.clone().normalize().multiplyScalar(10000));
export const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 10, 2_000_000);
orthoCam.up.copy(WORLD_UP);
orthoCam.position.copy(persp.position);

export const controls = new OrbitControls(orthoCam, canvas);
controls.target.set(0, 0, 0);
controls.mouseButtons.LEFT = -1;
controls.mouseButtons.MIDDLE = THREE.MOUSE.ROTATE;
controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
// Keep orbit off the Z pole so lookAt(up=+Z) stays well-defined after Top/Bottom.
controls.minPolarAngle = 0.04;
controls.maxPolarAngle = Math.PI - 0.04;
controls.minDistance = 10;
controls.maxDistance = 2_000_000;
controls.update();

// Light intensities in the legacy scale the clay was tuned in. three r155+ lights are
// physical: a Lambert surface returns intensity / π, so applyViz() multiplies by
// LIGHT_SCALE. Without it a solid renders at about a third of its clay grey (near black).
export const LIGHT_SCALE = Math.PI;
export const LIGHTS = { hemi: 0.58, hemiFlat: 0.42, key: 0.45 };
// Colours: applyViz().
export const hemi = new THREE.HemisphereLight(undefined, undefined, LIGHTS.hemi * LIGHT_SCALE);
scene.add(hemi);
export const keyLight = new THREE.DirectionalLight(0xffffff, LIGHTS.key * LIGHT_SCALE);
// Over the viewer's left shoulder in the ISO view (camera at +x -y +z), so the three faces
// it shows read as three greys: top lightest, front, then right. It used to sit behind the
// camera (-x +y), which left both visible side faces unlit.
keyLight.position.set(0.35, -0.8, 1.0);
scene.add(keyLight);

export const contact = new THREE.Mesh(
  new THREE.PlaneGeometry(40000, 40000),
  new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.06,
    depthWrite: false,
  }),
);
contact.position.z = -2;
contact.renderOrder = -2;
scene.add(contact);
scene.add(new THREE.AxesHelper(3000));
export const draft = new THREE.Group();
export const ghosts = new THREE.Group();
export const preselects = new THREE.Group();
export const selectionHalos = new THREE.Group();
scene.add(draft);
scene.add(ghosts);
scene.add(preselects);
scene.add(selectionHalos);
draft.renderOrder = 1;
ghosts.renderOrder = 2;
preselects.renderOrder = 3;
selectionHalos.renderOrder = 4;

export function wrapAutoDispose(group) {
  return _wrapAutoDispose(group, requestRender);
}

wrapAutoDispose(draft);
wrapAutoDispose(ghosts);
wrapAutoDispose(preselects);
wrapAutoDispose(selectionHalos);

export function currentLineResolution() {
  const w = (canvas && canvas.clientWidth) || window.innerWidth || 1;
  const h = (canvas && canvas.clientHeight) || window.innerHeight || 1;
  return new THREE.Vector2(w, h);
}

export function syncAllLineResolutions(
  w = (canvas && canvas.clientWidth) || 1,
  h = (canvas && canvas.clientHeight) || 1,
) {
  scene.traverse((obj) => {
    const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : [];
    for (const mat of mats) {
      if (mat && mat.resolution && typeof mat.resolution.set === "function") {
        mat.resolution.set(w, h);
      }
    }
  });
}

// Render one frame synchronously and capture a PNG data URL (ADR 0038) so visual checks
// do not need permanent preserveDrawingBuffer overhead.
export function exportViewportPng(activeCam = orthoCam) {
  renderer.render(scene, activeCam);
  return canvas.toDataURL("image/png");
}

