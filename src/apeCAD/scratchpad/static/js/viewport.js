// The main three.js viewport: renderer, scene, both cameras, orbit controls, lights, and the
// draft / ghost / preselect groups the rest of the client draws into. Objects only; camera
// behaviour lives in camera.js.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

export const canvas = document.getElementById("view");

export const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
export const scene = new THREE.Scene();
scene.background = new THREE.Color(0xe4e9ee);

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

export const hemi = new THREE.HemisphereLight(0xf4f7fb, 0x6e757c, 0.55);
scene.add(hemi);
export const keyLight = new THREE.DirectionalLight(0xffffff, 0.45);
keyLight.position.set(-1.1, 0.85, 1.35);
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
scene.add(draft);
scene.add(ghosts);
scene.add(preselects);
draft.renderOrder = 1;
ghosts.renderOrder = 2;
preselects.renderOrder = 3;
