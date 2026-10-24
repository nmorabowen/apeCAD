// Native cursor-pivot Z-up CAD turntable Navigator and pointer-capture cleanup (ADR 0037).
// Pure math helpers live in nav-math.js and are re-exported here for callers and unit tests.

import {
  DEFAULT_WORLD_UP,
  createVec3,
  headingBasis,
  orbitAroundCursor,
  panKeepPoint,
  toVec3,
  vAdd,
  vLen,
  vScale,
  vSub,
  writeVec3,
  zoomAtCursor,
} from "./nav-math.js";
import { S } from "./state.js";
import { requestRender } from "./store.js";

export * from "./nav-math.js";

// Native cursor-pivot Z-up CAD turntable Navigator (ADR 0037).
export class Navigator {
  constructor(object = null, domElement = null, options = {}) {
    this.object = object;
    this.domElement = domElement;
    this.enabled = options.enabled ?? true;
    this.target =
      options.target ||
      (object?.position && typeof object.position.clone === "function"
        ? object.position.clone().set(0, 0, 0)
        : createVec3(0, 0, 0));
    this.minDistance = options.minDistance ?? 10;
    this.maxDistance = options.maxDistance ?? 2_000_000;
    this.minPolarAngle = options.minPolarAngle ?? 0.04;
    this.maxPolarAngle = options.maxPolarAngle ?? Math.PI - 0.04;
    this.rotateSpeed = options.rotateSpeed ?? 0.0075;
    this.mouseButtons = { LEFT: -1, MIDDLE: 0, RIGHT: 2, ...(options.mouseButtons || {}) };
    this.getPivot = typeof options.getPivot === "function" ? options.getPivot : null;

    this._listeners = new Map();
    this._state = "none";
    this._pointerId = null;
    this._lastX = 0;
    this._lastY = 0;
    this._pivot = null;

    this._onPointerDown = (ev) => this._handlePointerDown(ev);
    this._onPointerMove = (ev) => this._handlePointerMove(ev);
    this._onPointerUp = (ev) => this._endGesture(ev);
    this._onPointerCancel = (ev) => this._endGesture(ev);
    this._onWheel = (ev) => this._handleWheel(ev);
    this._onContextMenu = (ev) => {
      if (typeof ev?.preventDefault === "function") ev.preventDefault();
    };

    if (this.domElement && typeof this.domElement.addEventListener === "function") {
      this.domElement.addEventListener("pointerdown", this._onPointerDown, false);
      this.domElement.addEventListener("pointermove", this._onPointerMove, false);
      this.domElement.addEventListener("pointerup", this._onPointerUp, false);
      this.domElement.addEventListener("pointercancel", this._onPointerCancel, false);
      this.domElement.addEventListener("lostpointercapture", this._onPointerCancel, false);
      this.domElement.addEventListener("wheel", this._onWheel, { passive: false });
      this.domElement.addEventListener("contextmenu", this._onContextMenu, false);
    }
  }

  _actionForButton(button) {
    let code = -1;
    if (button === 0) code = this.mouseButtons.LEFT ?? -1;
    else if (button === 1) code = this.mouseButtons.MIDDLE ?? 0;
    else if (button === 2) code = this.mouseButtons.RIGHT ?? 2;
    if (code === 0 || code === "orbit" || code === "rotate") return "orbit";
    if (code === 2 || code === "pan") return "pan";
    return "none";
  }

  _resolvePivot(event) {
    const tgt = toVec3(this.target, { x: 0, y: 0, z: 0 });
    const eye = toVec3(this.object?.position, { x: 0, y: -1000, z: 0 });
    if (typeof this.getPivot === "function") {
      const hit = this.getPivot(event);
      if (hit) {
        const p = toVec3(hit, tgt);
        const camDist = Math.max(vLen(vSub(eye, tgt)), 1);
        if (vLen(vSub(p, tgt)) <= camDist * 6) return p;
      }
    }
    const rect =
      this.domElement && typeof this.domElement.getBoundingClientRect === "function"
        ? this.domElement.getBoundingClientRect()
        : null;
    if (rect && rect.width > 0 && rect.height > 0 && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
      const basis = headingBasis(vSub(tgt, eye), toVec3(this.object?.up, DEFAULT_WORLD_UP));
      const { worldPerPixelX, worldPerPixelY } = this._worldPerPixel(eye, tgt);
      const dxPx = event.clientX - (rect.left + rect.width * 0.5);
      const dyPx = event.clientY - (rect.top + rect.height * 0.5);
      return vAdd(tgt, vAdd(vScale(basis.right, dxPx * worldPerPixelX), vScale(basis.up, -dyPx * worldPerPixelY)));
    }
    return tgt;
  }

  _worldPerPixel(eye, target) {
    const rect =
      this.domElement && typeof this.domElement.getBoundingClientRect === "function"
        ? this.domElement.getBoundingClientRect()
        : null;
    const clientW = Math.max(1, Number(rect?.width) || Number(this.domElement?.clientWidth) || 800);
    const clientH = Math.max(1, Number(rect?.height) || Number(this.domElement?.clientHeight) || 600);
    const cam = this.object || {};
    const zoom = Math.max(Number(cam.zoom) || 1, 1e-6);
    if (
      !cam.isPerspectiveCamera &&
      typeof cam.right === "number" &&
      typeof cam.left === "number" &&
      typeof cam.top === "number" &&
      typeof cam.bottom === "number" &&
      cam.right - cam.left > 2.01
    ) {
      return {
        worldPerPixelX: (cam.right - cam.left) / (zoom * clientW),
        worldPerPixelY: (cam.top - cam.bottom) / (zoom * clientH),
      };
    }
    const dist = Math.max(vLen(vSub(eye, target)), 1);
    const fovRad = ((Number(cam.fov) || 50) * Math.PI) / 180;
    const wpp = (2 * dist * Math.tan(fovRad * 0.5)) / (zoom * clientH);
    return { worldPerPixelX: wpp, worldPerPixelY: wpp };
  }

  _handlePointerDown(event) {
    if (!this.enabled || !this.object || this._state !== "none") return;
    const action = this._actionForButton(event.button);
    if (action === "none") return;
    if (typeof event.preventDefault === "function") event.preventDefault();
    this._state = action;
    this._pointerId = event.pointerId ?? null;
    this._lastX = Number(event.clientX) || 0;
    this._lastY = Number(event.clientY) || 0;
    this._pivot =
      action === "orbit" ? this._resolvePivot(event) : toVec3(this.target, { x: 0, y: 0, z: 0 });
    if (this._pointerId !== null && typeof this.domElement?.setPointerCapture === "function") {
      try {
        this.domElement.setPointerCapture(this._pointerId);
      } catch (_e) {
        // Synthetic pointer events in unit tests may not have an active hardware pointer.
      }
    }
    this.dispatchEvent({ type: "start" });
  }

  _handlePointerMove(event) {
    if (!this.enabled || !this.object || this._state === "none") return;
    if (this._pointerId !== null && event.pointerId != null && event.pointerId !== this._pointerId) {
      return;
    }
    const clientX = Number(event.clientX) || 0;
    const clientY = Number(event.clientY) || 0;
    const dx = clientX - this._lastX;
    const dy = clientY - this._lastY;
    this._lastX = clientX;
    this._lastY = clientY;
    if (dx === 0 && dy === 0) return;

    if (this._state === "orbit") {
      const poleMarginRad = Math.max(
        1e-4,
        Math.min(this.minPolarAngle ?? 0.04, Math.PI - (this.maxPolarAngle ?? Math.PI - 0.04)),
      );
      const res = orbitAroundCursor({
        eye: this.object.position,
        target: this.target,
        up: DEFAULT_WORLD_UP,
        pivot: this._pivot || this.target,
        yawDeltaRad: -dx * this.rotateSpeed,
        pitchDeltaRad: -dy * this.rotateSpeed,
        poleMarginRad,
      });
      writeVec3(this.object.position, res.eye);
      if (this.object.up) writeVec3(this.object.up, res.up);
      writeVec3(this.target, res.target);
      if (typeof this.object.lookAt === "function") this.object.lookAt(this.target);
      this.dispatchEvent({ type: "change" });
      return;
    }

    if (this._state === "pan") {
      const eye = toVec3(this.object.position, { x: 0, y: -1000, z: 0 });
      const target = toVec3(this.target, { x: 0, y: 0, z: 0 });
      const camUp = toVec3(this.object.up, DEFAULT_WORLD_UP);
      const basis = headingBasis(vSub(target, eye), camUp);
      const { worldPerPixelX, worldPerPixelY } = this._worldPerPixel(eye, target);
      const res = panKeepPoint({
        eye,
        target,
        right: basis.right,
        up: basis.up,
        worldPerPixelX,
        worldPerPixelY,
        dxPx: dx,
        dyPx: dy,
      });
      writeVec3(this.object.position, res.eye);
      writeVec3(this.target, res.target);
      if (typeof this.object.lookAt === "function") this.object.lookAt(this.target);
      this.dispatchEvent({ type: "change" });
    }
  }

  _endGesture(event) {
    if (this._state === "none") {
      if (this.mouseButtons) this.mouseButtons.LEFT = -1;
      return;
    }
    if (event && this._pointerId !== null && event.pointerId != null && event.pointerId !== this._pointerId) {
      return;
    }
    const pid = this._pointerId;
    this._state = "none";
    this._pointerId = null;
    this._pivot = null;
    if (this.mouseButtons) this.mouseButtons.LEFT = -1;
    if (pid !== null && typeof this.domElement?.releasePointerCapture === "function") {
      try {
        this.domElement.releasePointerCapture(pid);
      } catch (_e) {
        // Ignore if already released.
      }
    }
    this.dispatchEvent({ type: "end" });
  }

  _handleWheel(event) {
    if (!this.enabled || !this.object || event.ctrlKey) return;
    const deltaY = Number(event.deltaY) || 0;
    if (deltaY === 0) return;
    if (typeof event.preventDefault === "function") event.preventDefault();
    const zoomFactor = deltaY < 0 ? 0.9 : 1 / 0.9;
    const pivot = this._resolvePivot(event);
    const res = zoomAtCursor({
      eye: this.object.position,
      target: this.target,
      pivot,
      zoomFactor,
      minDistance: this.minDistance,
      maxDistance: this.maxDistance,
    });
    writeVec3(this.object.position, res.eye);
    writeVec3(this.target, res.target);
    if (typeof this.object.lookAt === "function") this.object.lookAt(this.target);
    this.dispatchEvent({ type: "change" });
  }

  update() {
    if (this.object && typeof this.object.lookAt === "function") {
      this.object.lookAt(this.target);
    }
    return false;
  }

  addEventListener(type, listener) {
    if (!type || typeof listener !== "function") return;
    let set = this._listeners.get(type);
    if (!set) {
      set = new Set();
      this._listeners.set(type, set);
    }
    set.add(listener);
  }

  removeEventListener(type, listener) {
    const set = this._listeners.get(type);
    if (set) set.delete(listener);
  }

  dispatchEvent(event) {
    const type = typeof event === "string" ? event : event?.type;
    if (!type) return;
    const payload = typeof event === "string" ? { type, target: this } : { target: this, ...event };
    const set = this._listeners.get(type);
    if (!set) return;
    for (const fn of [...set]) fn.call(this, payload);
  }

  dispose() {
    this._endGesture();
    if (this.domElement && typeof this.domElement.removeEventListener === "function") {
      this.domElement.removeEventListener("pointerdown", this._onPointerDown, false);
      this.domElement.removeEventListener("pointermove", this._onPointerMove, false);
      this.domElement.removeEventListener("pointerup", this._onPointerUp, false);
      this.domElement.removeEventListener("pointercancel", this._onPointerCancel, false);
      this.domElement.removeEventListener("lostpointercapture", this._onPointerCancel, false);
      this.domElement.removeEventListener("wheel", this._onWheel);
      this.domElement.removeEventListener("contextmenu", this._onContextMenu, false);
    }
    this._listeners.clear();
  }
}

// Attach cursor-pivot lookup and pointercancel / lostpointercapture / blur cleanup to the viewport.
export function bindCadNavigation({ canvas, controls, hitWorkplane, hideMarquee, win }) {
  if (!canvas) return;
  if (controls && typeof hitWorkplane === "function") {
    controls.getPivot = hitWorkplane;
  }

  const cancelActiveGesture = (event) => {
    const isForeignPointer =
      event &&
      event.type !== "blur" &&
      controls &&
      controls._state !== "none" &&
      controls._pointerId !== null &&
      event.pointerId != null &&
      event.pointerId !== controls._pointerId;
    if (isForeignPointer) return;
    if (S.marqueeOrigin && typeof hideMarquee === "function") hideMarquee();
    if (controls) {
      if (controls.mouseButtons) controls.mouseButtons.LEFT = -1;
      if (typeof controls._endGesture === "function") {
        controls._endGesture(event?.type === "blur" ? undefined : event);
      }
    }
    requestRender();
  };
  canvas.addEventListener("pointercancel", cancelActiveGesture);
  canvas.addEventListener("lostpointercapture", cancelActiveGesture);
  const winTarget = win ?? (typeof window !== "undefined" ? window : null);
  if (winTarget && typeof winTarget.addEventListener === "function") {
    winTarget.addEventListener("blur", cancelActiveGesture);
  }
}
