import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const canvas = document.querySelector("#scene");
const statusEl = document.querySelector("#status");
const nameEl = document.querySelector("#part-name");
const metaEl = document.querySelector("#part-meta");
const fileInput = document.querySelector("#file-input");

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
renderer.setClearColor(0x101512, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
controls.screenSpacePanning = true;

const root = new THREE.Group();
scene.add(root);

scene.add(new THREE.HemisphereLight(0xe6fff0, 0x27352d, 1.05));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.8);
keyLight.position.set(80, -120, 140);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(1024, 1024);
scene.add(keyLight);
const fillLight = new THREE.DirectionalLight(0xb8d7ff, 0.75);
fillLight.position.set(-140, 120, 90);
scene.add(fillLight);
const rimLight = new THREE.DirectionalLight(0x9dffbd, 0.85);
rimLight.position.set(-100, -80, 180);
scene.add(rimLight);

const grid = new THREE.GridHelper(160, 16, 0x587064, 0x2c3a33);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
scene.add(new THREE.AxesHelper(42));

const shadowPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(1000, 1000),
  new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.2 }),
);
shadowPlane.receiveShadow = true;
scene.add(shadowPlane);

let renderQueued = false;

function requestRender() {
  if (renderQueued || document.hidden) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    renderer.render(scene, camera);
  });
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  requestRender();
}

window.addEventListener("resize", resize);
controls.addEventListener("change", requestRender);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) requestRender();
});
resize();

function makeMaterial(object) {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(object.color || "#67b7dc"),
    roughness: 0.48,
    metalness: 0.08,
    transparent: (object.opacity ?? 1) < 1,
    opacity: object.opacity ?? 1,
    side: THREE.DoubleSide,
  });
}

function addEdges(mesh) {
  if (mesh.geometry.attributes.position?.count > 120000) return;
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: 0x162018, transparent: true, opacity: 0.42 }),
  );
  mesh.add(edges);
}

function prepMesh(mesh) {
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function objectPosition(object) {
  const p = object.position || { x: 0, y: 0, z: 0 };
  return [p.x || 0, p.y || 0, p.z || 0];
}

function buildBox(object) {
  const size = object.size || { x: 10, y: 10, z: 10 };
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size.x, size.y, size.z),
    makeMaterial(object),
  );
  mesh.position.set(...objectPosition(object));
  addEdges(mesh);
  return prepMesh(mesh);
}

function buildCylinder(object) {
  const depth = object.depth || 10;
  const radius = object.radius || 5;
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, depth, 64),
    makeMaterial(object),
  );
  if (object.axis === "z") {
    mesh.rotation.x = Math.PI / 2;
  } else if (object.axis === "x") {
    mesh.rotation.z = Math.PI / 2;
  }
  mesh.position.set(...objectPosition(object));
  addEdges(mesh);
  return prepMesh(mesh);
}

function buildPlateWithHoles(object) {
  const size = object.size || { x: 100, y: 50, z: 6 };
  const halfX = size.x / 2;
  const halfY = size.y / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-halfX, -halfY);
  shape.lineTo(halfX, -halfY);
  shape.lineTo(halfX, halfY);
  shape.lineTo(-halfX, halfY);
  shape.lineTo(-halfX, -halfY);
  for (const hole of object.holes || []) {
    const path = new THREE.Path();
    path.absellipse(hole.x, hole.y, hole.radius, hole.radius, 0, Math.PI * 2, true);
    shape.holes.push(path);
  }
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: size.z,
    bevelEnabled: false,
    curveSegments: 48,
  });
  geometry.translate(0, 0, -size.z / 2);
  const mesh = new THREE.Mesh(geometry, makeMaterial(object));
  mesh.position.set(...objectPosition(object));
  addEdges(mesh);
  return prepMesh(mesh);
}

function buildObject(object) {
  if (object.kind === "box") return buildBox(object);
  if (object.kind === "cylinder") return buildCylinder(object);
  if (object.kind === "plate_with_holes") return buildPlateWithHoles(object);
  throw new Error(`Unsupported object kind: ${object.kind}`);
}

function clearRoot() {
  while (root.children.length) {
    const child = root.children.pop();
    child.traverse((node) => {
      if (node.geometry) node.geometry.dispose();
      if (node.material) node.material.dispose();
    });
  }
}

function fitCamera() {
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 1);
  const distance = maxDim / (2 * Math.tan((camera.fov * Math.PI) / 360));
  camera.position.set(center.x + distance * 0.8, center.y - distance * 1.25, center.z + distance * 0.9);
  camera.near = Math.max(distance / 100, 0.1);
  camera.far = distance * 20;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
  grid.position.set(center.x, center.y, box.min.z - 0.6);
  shadowPlane.position.set(center.x, center.y, box.min.z - 0.7);
  requestRender();
}

function renderSceneArtifact(artifact, sourceLabel) {
  clearRoot();
  for (const object of artifact.objects || []) {
    root.add(buildObject(object));
  }
  nameEl.textContent = artifact.name || artifact.id || "Untitled part";
  metaEl.textContent = `${artifact.objects?.length || 0} objects · ${artifact.units || "units"} · ${sourceLabel}`;
  statusEl.textContent = "Drag to orbit. Scroll to zoom. Right-drag to pan.";
  fitCamera();
}

function renderStlGeometry(geometry, sourceLabel) {
  clearRoot();
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: 0x78c894,
      roughness: 0.44,
      metalness: 0.06,
      envMapIntensity: 0.6,
    }),
  );
  addEdges(mesh);
  root.add(prepMesh(mesh));
  nameEl.textContent = sourceLabel.split("/").pop() || "Generated CAD model";
  metaEl.textContent = `STL mesh · ${sourceLabel}`;
  statusEl.textContent = "Drag to orbit. Scroll to zoom. Right-drag to pan.";
  fitCamera();
}

async function loadArtifactFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const stlUrl = params.get("stl");
  if (stlUrl) {
    const geometry = await new STLLoader().loadAsync(stlUrl);
    renderStlGeometry(geometry, stlUrl);
    return;
  }
  const artifactUrl = params.get("artifact") || "/workspace/sample_part.json";
  const response = await fetch(artifactUrl);
  if (!response.ok) {
    throw new Error(`Could not load ${artifactUrl}: ${response.status}`);
  }
  renderSceneArtifact(await response.json(), artifactUrl);
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  try {
    renderSceneArtifact(JSON.parse(await file.text()), file.name);
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

loadArtifactFromUrl().catch((error) => {
  statusEl.textContent = error.message;
  nameEl.textContent = "No artifact loaded";
  metaEl.textContent = "";
  requestRender();
});
