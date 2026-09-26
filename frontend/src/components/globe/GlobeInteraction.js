import * as THREE from 'three';
import { damp } from './lib/math.js';

// Pointer / touch tracking scoped to the globe's own canvas. Listeners are passive and never call
// preventDefault, so page scrolling, links and buttons elsewhere behave exactly as before.

export class GlobeInteraction {
    constructor(canvas, camera, radius) {
        this.canvas = canvas;
        this.camera = camera;
        this.sphere = new THREE.Sphere(new THREE.Vector3(), radius);
        this.raycaster = new THREE.Raycaster();
        this.ndc = new THREE.Vector2();
        this.hit = new THREE.Vector3();
        this.inverse = new THREE.Matrix4();
        this.local = new THREE.Vector3(0, 0, 10); // unit-sphere point under the pointer
        this.inside = false;   // pointer over the canvas
        this.onGlobe = false;  // pointer ray hits the sphere
        this.strength = 0;     // smoothed 0..1 glow strength
        this.influenceX = 0;   // smoothed pointer offset used for orientation
        this.influenceY = 0;

        this._move = (e) => {
            const rect = canvas.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            this.ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
            this.inside = true;
        };
        this._leave = () => {
            this.inside = false;
        };
        this._touchEnd = (e) => {
            if (e.pointerType !== 'mouse') this.inside = false;
        };
        const passive = { passive: true };
        canvas.addEventListener('pointermove', this._move, passive);
        canvas.addEventListener('pointerdown', this._move, passive);
        canvas.addEventListener('pointerleave', this._leave, passive);
        canvas.addEventListener('pointercancel', this._leave, passive);
        canvas.addEventListener('pointerup', this._touchEnd, passive);
    }

    /** Update smoothed state; `globe` is the rotating group. */
    update(globe, dt, damping) {
        this.onGlobe = false;
        if (this.inside) {
            this.raycaster.setFromCamera(this.ndc, this.camera);
            if (this.raycaster.ray.intersectSphere(this.sphere, this.hit)) {
                this.inverse.copy(globe.matrixWorld).invert();
                this.local.copy(this.hit).applyMatrix4(this.inverse).normalize();
                this.onGlobe = true;
            }
        }
        this.strength = damp(this.strength, this.onGlobe ? 1 : 0, this.onGlobe ? 6 : 2.5, dt);
        this.influenceX = damp(this.influenceX, this.inside ? this.ndc.x : 0, damping, dt);
        this.influenceY = damp(this.influenceY, this.inside ? this.ndc.y : 0, damping, dt);
    }

    dispose() {
        const c = this.canvas;
        c.removeEventListener('pointermove', this._move);
        c.removeEventListener('pointerdown', this._move);
        c.removeEventListener('pointerleave', this._leave);
        c.removeEventListener('pointercancel', this._leave);
        c.removeEventListener('pointerup', this._touchEnd);
    }
}
