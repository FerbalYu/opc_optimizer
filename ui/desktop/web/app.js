import * as THREE from "three";

const $ = (id) => document.getElementById(id);

const state = {
  bridge: null,
  round: "-",
  activeAgent: "-",
  health: "-",
  changedFiles: 0,
  toolCalls: [],
  history: [],
};

const NODE_ORDER = ["plan", "execute", "test", "archive", "report", "interact"];
const NODE_COLORS = {
  plan: 0x58a6ff,
  execute: 0x3fb950,
  test: 0xf0883e,
  archive: 0xbc8cff,
  report: 0x39d2c0,
  interact: 0xf78166,
};
const NODE_LABELS = {
  plan: "Plan",
  execute: "Execute",
  test: "Test",
  archive: "Archive",
  report: "Report",
  interact: "Interact",
};
const STATIONS = {
  plan: { x: -5.2, z: -2.7, facing: Math.PI },
  execute: { x: 0, z: -2.7, facing: Math.PI },
  test: { x: 5.2, z: -2.7, facing: Math.PI },
  archive: { x: -5.2, z: 2.7, facing: 0 },
  report: { x: 0, z: 2.7, facing: 0 },
  interact: { x: 5.2, z: 2.7, facing: 0 },
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function log(message, detail = "") {
  const row = document.createElement("div");
  row.className = "row";
  row.innerHTML = `<strong>${escapeHtml(message)}</strong><small>${escapeHtml(detail)}</small>`;
  $("logList").prepend(row);
}

function setConnection(text) {
  $("connectionState").textContent = text;
}

function setAgentStep(step) {
  document.querySelectorAll("#agentLoop [data-step]").forEach((node) => {
    node.classList.toggle("active", node.dataset.step === step);
  });
}

function renderToolCalls() {
  const target = $("toolCalls");
  if (!state.toolCalls.length) {
    target.className = "list empty";
    target.textContent = "No tool calls";
    return;
  }
  target.className = "list";
  target.innerHTML = state.toolCalls.slice(0, 8).map((call) => {
    const status = call.ok === false ? "failed" : call.ok === null ? "running" : "done";
    return `<div class="row"><strong>${escapeHtml(call.tool_name || call.name || "tool")}</strong><small>${status} / round ${escapeHtml(call.round || "-")}</small></div>`;
  }).join("");
}

function renderHistory() {
  const target = $("roundHistory");
  if (!state.history.length) {
    target.className = "timeline empty";
    target.textContent = "No round history";
    return;
  }
  target.className = "timeline";
  target.innerHTML = state.history.slice(0, 10).map((item) => {
    const round = item.round || "-";
    const files = (item.modified_files || []).length;
    return `<div class="row"><strong>Round ${escapeHtml(round)}</strong><small>${files} files / ${escapeHtml(item.active_agent || "-")}</small></div>`;
  }).join("");
}

function updateSummary() {
  $("roundValue").textContent = state.round;
  $("agentValue").textContent = state.activeAgent;
  $("healthValue").textContent = state.health;
  $("fileCount").textContent = String(state.changedFiles);
}

function normalizeNode(name) {
  const value = String(name || "").toLowerCase();
  if (value === "task_router" || value === "task") return "plan";
  return NODE_ORDER.includes(value) ? value : "execute";
}

function handleBridgeEvent(raw) {
  const event = typeof raw === "string" ? JSON.parse(raw) : raw;
  const data = event.data || {};
  switch (event.type) {
    case "node_start": {
      const node = normalizeNode(data.node);
      state.round = data.round || state.round;
      state.activeAgent = data.node || state.activeAgent;
      setAgentStep("act");
      moveToStation(node);
      log(`Node started: ${data.node || "-"}`, `round ${data.round || "-"}`);
      break;
    }
    case "node_complete": {
      const node = normalizeNode(data.node);
      state.activeAgent = data.node || state.activeAgent;
      setAgentStep("observe");
      celebrateAt(node);
      log(`Node complete: ${data.node || "-"}`, `${Math.round((data.elapsed || 0) * 100) / 100}s`);
      break;
    }
    case "node_error": {
      const node = normalizeNode(data.node);
      errorAt(node);
      log(`Node error: ${data.node || "-"}`, data.error || "");
      break;
    }
    case "diff_update":
      state.changedFiles += (data.files || []).length;
      buildFileBricks(data.files || []);
      log("File changes", (data.files || []).join(", "));
      break;
    case "skill_chain_update":
      $("skillChain").textContent = `Skill chain: ${(data.skill_chain || []).join(" -> ") || "-"}`;
      setAgentStep("think");
      break;
    case "tool_call_start":
      state.toolCalls.unshift({ tool_name: data.tool_name, round: data.round, ok: null });
      renderToolCalls();
      break;
    case "tool_call_complete":
      state.toolCalls.unshift(data);
      renderToolCalls();
      break;
    case "round_history_update":
      state.history.unshift(data);
      renderHistory();
      break;
    case "round_insight":
      state.health = data.health_score ?? state.health;
      $("valueLabel").textContent = data.value_label || "-";
      $("nextAction").textContent = (data.next_actions || [])[0] || "-";
      updateInsightObjects(data);
      break;
    case "metrics_update":
      if (data.health_score !== undefined) state.health = data.health_score;
      break;
    case "awaiting_input":
      setAgentStep("reflect");
      moveToStation("interact");
      log("Awaiting user input", `round ${data.round || "-"}`);
      break;
    case "optimization_complete":
      setAgentStep("reflect");
      moveToStation("report");
      log("Optimization complete", "Report is ready");
      break;
    case "desktop_error":
      log("Desktop error", data.error || "");
      break;
    default:
      log(event.type || "event", JSON.stringify(data));
      break;
  }
  updateSummary();
}

function initBridge() {
  if (!window.qt) {
    setConnection("Browser preview");
    log("QWebChannel disconnected", "Open in OPC Desktop to enable run controls");
    return;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    state.bridge = channel.objects.desktopBridge;
    state.bridge.eventReceived.connect(handleBridgeEvent);
    state.bridge.runStateChanged.connect((raw) => log("Run state", raw));
    setConnection("Bridge connected");
    state.bridge.initialConfig((raw) => {
      const response = JSON.parse(raw);
      if (!response.ok) return;
      $("projectPath").value = response.project_path || "";
      $("goalInput").value = response.goal || $("goalInput").value;
      $("maxRounds").value = response.max_rounds || 5;
      $("autoMode").checked = Boolean(response.auto);
      $("dryRun").checked = Boolean(response.dry_run);
    });
  });
}

function loadBridgeScript() {
  if (!window.qt) {
    initBridge();
    return;
  }
  const script = document.createElement("script");
  script.src = "qrc:///qtwebchannel/qwebchannel.js";
  script.onload = initBridge;
  script.onerror = () => {
    setConnection("QWebChannel load failed");
    log("QWebChannel script failed", "qrc:///qtwebchannel/qwebchannel.js");
  };
  document.head.appendChild(script);
}

function collectRunConfig() {
  return {
    project_path: $("projectPath").value.trim(),
    goal: $("goalInput").value.trim(),
    max_rounds: Number($("maxRounds").value || 5),
    auto: $("autoMode").checked,
    dry_run: $("dryRun").checked,
  };
}

function wireControls() {
  $("browseBtn").addEventListener("click", () => {
    if (!state.bridge) return;
    state.bridge.chooseProject((raw) => {
      const response = JSON.parse(raw);
      if (response.ok) $("projectPath").value = response.project_path;
    });
  });
  $("startBtn").addEventListener("click", () => {
    if (!state.bridge) return;
    state.changedFiles = 0;
    state.toolCalls = [];
    state.history = [];
    renderToolCalls();
    renderHistory();
    updateSummary();
    state.bridge.startRun(JSON.stringify(collectRunConfig()), (raw) => {
      const response = JSON.parse(raw);
      log(response.ok ? "Run submitted" : "Run failed", response.error || response.state || "");
    });
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!state.bridge) return;
      const action = button.dataset.action;
      state.bridge.sendCommand(JSON.stringify({ action }), (raw) => log(`Command: ${action}`, raw));
    });
  });
}

const canvas = $("sceneCanvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87ceeb);
scene.fog = new THREE.Fog(0x87ceeb, 28, 58);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camera.position.set(14, 12, 14);
camera.lookAt(0, 1, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.52));
const sunLight = new THREE.DirectionalLight(0xfff4e6, 1.2);
sunLight.position.set(10, 20, 10);
sunLight.castShadow = true;
sunLight.shadow.mapSize.set(1024, 1024);
scene.add(sunLight);
const fillLight = new THREE.DirectionalLight(0x8ec8f8, 0.35);
fillLight.position.set(-10, 8, -10);
scene.add(fillLight);

function voxelMat(color, options = {}) {
  return new THREE.MeshLambertMaterial({
    color,
    transparent: options.opacity !== undefined,
    opacity: options.opacity ?? 1,
  });
}

function box(w, h, d, color, x, y, z, options = {}) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), voxelMat(color, options));
  mesh.position.set(x, y, z);
  mesh.castShadow = options.castShadow !== false;
  mesh.receiveShadow = options.receiveShadow !== false;
  return mesh;
}

function buildRoom() {
  const room = new THREE.Group();
  room.add(box(20, 0.5, 14, 0x5b8c5a, 0, -0.25, 0));
  for (let x = -9; x <= 9; x += 2) {
    for (let z = -6; z <= 6; z += 2) {
      room.add(box(1.9, 0.1, 1.9, (x + z) % 4 === 0 ? 0x6b9c6a : 0x4b7c4a, x, 0.01, z));
    }
  }
  room.add(box(20, 5, 0.5, 0x8b7355, 0, 2.5, -7));
  room.add(box(0.5, 5, 14, 0x7a6548, -10, 2.5, 0));
  room.add(box(0.5, 5, 14, 0x7a6548, 10, 2.5, 0));
  for (let wx = -6; wx <= 6; wx += 4) {
    room.add(box(2, 2, 0.58, 0xadd8e6, wx, 3, -6.75, { castShadow: false }));
  }
  room.add(box(2.8, 2.1, 0.35, 0x6f7f91, -8.4, 1.05, 4.8));
  for (let y = 0.5; y < 1.8; y += 0.45) {
    room.add(box(2.4, 0.08, 0.42, 0xa7b0ba, -8.4, y, 5.05));
  }
  scene.add(room);
}

function buildDesk(x, z) {
  const group = new THREE.Group();
  group.add(box(2.5, 0.3, 1.5, 0x8b6914, 0, 1.2, 0));
  for (const lx of [-1, 1]) {
    for (const lz of [-0.5, 0.5]) {
      group.add(box(0.2, 1.2, 0.2, 0x6b4f1d, lx, 0.6, lz));
    }
  }
  group.position.set(x, 0, z);
  return group;
}

function buildChair(x, z, facingBack = true) {
  const group = new THREE.Group();
  group.add(box(0.8, 0.2, 0.8, 0xc0392b, 0, 0.8, 0));
  group.add(box(0.8, 1, 0.2, 0xc0392b, 0, 1.4, facingBack ? 0.35 : -0.35));
  group.position.set(x, 0, facingBack ? z + 2.2 : z - 2.2);
  return group;
}

const stationIndicators = {};

function buildStation(name) {
  const { x, z } = STATIONS[name];
  const color = NODE_COLORS[name];
  const group = new THREE.Group();
  group.name = `${name}-station`;
  group.add(box(4, 0.15, 3.5, color, x, 0.08, z, { opacity: 0.25, castShadow: false }));

  // Keep the original office-worker idea: book, monitor, traffic lights,
  // file cabinet, whiteboard, sofa, and coffee table around the stations.
  if (name === "interact") {
    group.add(box(1.5, 0.2, 1, 0x8b6914, x, 0.5, z));
    group.add(box(0.3, 0.35, 0.3, 0xe74c3c, x + 0.35, 0.8, z));
    group.add(box(2.2, 0.7, 0.8, 0x8e44ad, x, 0.35, z - 1.2));
    group.add(box(2.2, 0.5, 0.25, 0x7d3c98, x, 0.75, z - 1.55));
    for (const side of [-1, 1]) {
      group.add(box(0.2, 0.4, 0.8, 0x7d3c98, x + side * 1.1, 0.55, z - 1.2));
    }
  } else {
    group.add(buildDesk(x, z));
    group.add(buildChair(x, z, z < 0));
    if (name === "plan") {
      group.add(box(0.6, 0.15, 0.8, 0x2980b9, x - 0.3, 1.5, z));
      group.add(box(0.6, 0.05, 0.8, 0xecf0f1, x - 0.28, 1.62, z + 0.05));
    } else if (name === "execute") {
      group.add(box(1.2, 0.9, 0.1, 0x2c3e50, x, 2.0, z - 0.4));
      group.add(box(1.0, 0.7, 0.05, 0x3498db, x, 2.0, z - 0.34, { castShadow: false }));
    } else if (name === "test") {
      [0xf85149, 0xf0883e, 0x3fb950].forEach((lamp, index) => {
        group.add(box(0.3, 0.3, 0.3, lamp, x + 1.5, 2.5 - index * 0.4, z));
      });
    } else if (name === "archive") {
      group.add(box(1, 2.5, 0.8, 0x7f8c8d, x + 1.5, 1.25, z));
      for (let dy = 0; dy < 3; dy++) {
        group.add(box(0.8, 0.05, 0.1, 0x95a5a6, x + 1.5, 0.6 + dy * 0.8, z + 0.45));
      }
    } else if (name === "report") {
      group.add(box(2, 1.5, 0.1, 0xecf0f1, x, 2.5, z + 0.6));
      [0x3498db, 0x2ecc71, 0xe74c3c, 0xf39c12].forEach((barColor, index) => {
        const height = 0.35 + index * 0.18;
        group.add(box(0.3, height, 0.05, barColor, x - 0.6 + index * 0.4, 1.8 + height / 2, z + 0.55));
      });
    }
  }

  const indicator = box(0.5, 0.5, 0.5, color, x, 4.8, z, { opacity: 0, castShadow: false });
  stationIndicators[name] = indicator;
  group.add(indicator);
  group.add(box(1.35, 0.18, 0.12, color, x, 4.15, z, { castShadow: false }));

  scene.add(group);
}

buildRoom();
NODE_ORDER.forEach(buildStation);

const steve = new THREE.Group();
const head = box(0.6, 0.6, 0.6, 0xf5cba7, 0, 2.3, 0);
const eyeL = box(0.12, 0.12, 0.05, 0x1a1a2e, -0.14, 2.35, 0.32, { castShadow: false });
const eyeR = box(0.12, 0.12, 0.05, 0x1a1a2e, 0.14, 2.35, 0.32, { castShadow: false });
const body = box(0.6, 0.8, 0.35, 0x2980b9, 0, 1.6, 0);
const armL = box(0.25, 0.75, 0.25, 0x58a6ff, -0.42, 1.62, 0);
const armR = box(0.25, 0.75, 0.25, 0x58a6ff, 0.42, 1.62, 0);
const legL = box(0.28, 0.8, 0.3, 0x5d6d7e, -0.16, 0.8, 0);
const legR = box(0.28, 0.8, 0.3, 0x5d6d7e, 0.16, 0.8, 0);
steve.add(head, eyeL, eyeR, body, armL, armR, legL, legR);
steve.position.set(STATIONS.execute.x, 0, STATIONS.execute.z + 1.5);
steve.rotation.y = Math.PI;
scene.add(steve);

const bubble = box(1.5, 0.42, 0.12, 0xffffff, 0, 3.25, 0.05, { opacity: 0, castShadow: false });
steve.add(bubble);

const fileGroup = new THREE.Group();
fileGroup.position.set(6.2, 0.2, 5.6);
scene.add(fileGroup);

const insightBar = box(1.1, 0.5, 1.1, 0x3fb950, -8.2, 0.25, 5.2, { opacity: 0.82 });
scene.add(insightBar);

let currentNode = "execute";
let targetPos = new THREE.Vector3(steve.position.x, 0, steve.position.z);
let isMoving = false;
let isWorking = true;
let walkTime = 0;
let workTime = 0;
const particles = [];

function stationStandPosition(nodeName) {
  const station = STATIONS[nodeName] || STATIONS.execute;
  return new THREE.Vector3(station.x, 0, station.z < 0 ? station.z + 1.5 : station.z - 1.5);
}

function moveToStation(nodeName) {
  currentNode = nodeName;
  targetPos = stationStandPosition(nodeName);
  isMoving = true;
  isWorking = false;
}

function startWorking() {
  isMoving = false;
  isWorking = true;
  workTime = 0;
  const station = STATIONS[currentNode];
  if (station) steve.rotation.y = station.facing;
}

function spawnParticles(x, y, z, color, count = 18) {
  for (let i = 0; i < count; i++) {
    const size = 0.08 + Math.random() * 0.12;
    const particle = box(size, size, size, color, x, y, z, { castShadow: false });
    particle.material.transparent = true;
    particle.userData.vel = new THREE.Vector3(
      (Math.random() - 0.5) * 0.14,
      Math.random() * 0.12 + 0.04,
      (Math.random() - 0.5) * 0.14,
    );
    particle.userData.life = 1;
    particles.push(particle);
    scene.add(particle);
  }
}

function celebrateAt(nodeName) {
  const station = STATIONS[nodeName];
  if (station) spawnParticles(station.x, 3, station.z, NODE_COLORS[nodeName] || 0x3fb950, 16);
}

function errorAt(nodeName) {
  const station = STATIONS[nodeName];
  if (station) spawnParticles(station.x, 2, station.z, 0xf85149, 24);
}

function updateParticles(dt) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const particle = particles[i];
    particle.position.add(particle.userData.vel);
    particle.userData.vel.y -= 0.004;
    particle.userData.life -= dt * 0.8;
    particle.material.opacity = Math.max(0, particle.userData.life);
    if (particle.userData.life <= 0) {
      scene.remove(particle);
      particles.splice(i, 1);
    }
  }
}

function buildFileBricks(files) {
  fileGroup.clear();
  files.slice(0, 16).forEach((file, index) => {
    const color = String(file).endsWith(".py") ? 0x5eead4 : 0x8b5cf6;
    const brick = box(
      0.62,
      0.26 + (index % 4) * 0.08,
      0.62,
      color,
      (index % 4) * 0.78,
      0.2,
      Math.floor(index / 4) * -0.78,
    );
    fileGroup.add(brick);
  });
}

function updateInsightObjects(data) {
  const score = Math.max(0, Math.min(10, Number(data.health_score || 0)));
  insightBar.scale.y = Math.max(0.5, score / 2);
  insightBar.position.y = insightBar.scale.y / 2;
  insightBar.material.color.setHex(score >= 7 ? 0x3fb950 : score >= 4 ? 0xf0883e : 0xf85149);
}

function resizeScene() {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height));
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

let lastTime = performance.now();
function animate(now = performance.now()) {
  resizeScene();
  const dt = Math.min((now - lastTime) / 1000, 0.1);
  lastTime = now;

  if (isMoving) {
    walkTime += dt * 8;
    const dir = targetPos.clone().sub(steve.position);
    const dist = dir.length();
    if (dist > 0.12) {
      dir.normalize();
      const step = Math.min(3.5 * dt, dist);
      steve.position.add(dir.multiplyScalar(step));
      steve.rotation.y = Math.atan2(dir.x, dir.z);
      armL.rotation.x = Math.sin(walkTime) * 0.6;
      armR.rotation.x = -Math.sin(walkTime) * 0.6;
      legL.rotation.x = -Math.sin(walkTime) * 0.5;
      legR.rotation.x = Math.sin(walkTime) * 0.5;
      steve.position.y = Math.abs(Math.sin(walkTime * 2)) * 0.08;
    } else {
      steve.position.copy(targetPos);
      steve.position.y = 0;
      armL.rotation.x = 0;
      armR.rotation.x = 0;
      legL.rotation.x = 0;
      legR.rotation.x = 0;
      startWorking();
    }
  }

  if (isWorking) {
    workTime += dt * 5;
    armL.rotation.x = Math.sin(workTime * 3) * 0.2;
    armR.rotation.x = Math.sin(workTime * 3 + 1) * 0.2;
    head.rotation.x = Math.sin(workTime * 1.5) * 0.05;
    bubble.material.opacity = 0.12 + Math.abs(Math.sin(workTime * 0.7)) * 0.18;
  }

  for (const [name, indicator] of Object.entries(stationIndicators)) {
    if (name === currentNode && isWorking) {
      indicator.material.opacity = 0.45 + Math.sin(now * 0.005) * 0.35;
      indicator.rotation.y += dt * 2;
    } else {
      indicator.material.opacity = 0;
    }
  }

  updateParticles(dt);
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

window.__opcDesktopHandleEvent = handleBridgeEvent;
window.__opcDesktopSceneState = () => ({
  currentNode,
  isMoving,
  isWorking,
  steve: { x: steve.position.x, y: steve.position.y, z: steve.position.z },
});

setAgentStep("think");
wireControls();
loadBridgeScript();
startWorking();
animate();
