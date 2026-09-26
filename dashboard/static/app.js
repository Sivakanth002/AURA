// ─── AURA Dashboard Frontend Application ───

let ws = null;
let mapData = null;
let worldState = null;
let activePromptId = null;

// Map render configuration
const mapScale = 24; // pixels per meter
const mapOffsetX = 100;
const mapOffsetY = 200;

document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  fetchInitialState();
  setInterval(fetchInitialState, 1500); // Polling backup
});

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById('ws-status').textContent = 'LIVE';
    document.getElementById('ws-status').style.color = 'var(--accent-green)';
  };

  ws.onclose = () => {
    document.getElementById('ws-status').textContent = 'DISCONNECTED';
    document.getElementById('ws-status').style.color = 'var(--accent-red)';
    setTimeout(initWebSocket, 2000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleLiveEvent(msg);
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  };
}

async function fetchInitialState() {
  try {
    const [stateRes, mapRes] = await Promise.all([
      fetch('/api/state').then(r => r.json()),
      fetch('/api/map').then(r => r.json())
    ]);

    worldState = stateRes.world_state;
    mapData = mapRes;

    updateUI(stateRes);
    renderMap();
  } catch (err) {
    console.error('Failed to fetch state:', err);
  }
}

function handleLiveEvent(msg) {
  addDecisionLog(msg);
  
  if (msg.event_type === 'USER_INTERACTION_REQUEST') {
    showHitlModal(msg.data);
  } else if (msg.event_type === 'TELEMETRY' || msg.event_type === 'OBSTACLE_DETECTED' || msg.event_type === 'TASK_STATUS_CHANGED') {
    fetchInitialState();
  }
}

function updateUI(stateRes) {
  const ws = stateRes.world_state;
  document.getElementById('agent-state').textContent = stateRes.agent_state;
  document.getElementById('robot-battery').textContent = `${ws.robot.battery.toFixed(0)}%`;

  // HUD
  document.getElementById('hud-pos').textContent = `[${ws.robot.location[0].toFixed(2)}, ${ws.robot.location[1].toFixed(2)}]`;
  document.getElementById('hud-vel').textContent = `${ws.robot.linear_velocity.toFixed(2)} m/s`;
  document.getElementById('hud-carrying').textContent = ws.robot.carrying_object || 'None';
  document.getElementById('hud-waypoint').textContent = ws.robot.nearest_waypoint || 'reception';

  // Mission Tasks
  if (ws.mission && ws.mission.tasks) {
    document.getElementById('plan-revision').textContent = ws.mission.revision || 1;
    renderTasksList(ws.mission.tasks);
  }
}

function renderTasksList(tasks) {
  const container = document.getElementById('tasks-list');
  container.innerHTML = '';

  tasks.forEach(task => {
    const card = document.createElement('div');
    card.className = `task-card ${task.status}`;
    card.innerHTML = `
      <div>
        <span class="task-id">${task.task_id}</span>
        <span class="task-desc">${task.description}</span>
      </div>
      <span class="task-status-badge">${task.status}</span>
    `;
    container.appendChild(card);
  });
}

function showHitlModal(data) {
  activePromptId = data.prompt_id;
  const modal = document.getElementById('hitl-modal');
  document.getElementById('hitl-question').textContent = data.question;

  const optContainer = document.getElementById('hitl-options-container');
  optContainer.innerHTML = '';

  data.options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'btn btn-warning';
    btn.textContent = opt;
    btn.onclick = () => submitDisambiguation(activePromptId, opt);
    optContainer.appendChild(btn);
  });

  modal.classList.remove('hidden');
}

async function submitDisambiguation(promptId, option) {
  await fetch('/api/disambiguate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId, selected_option: option })
  });
  document.getElementById('hitl-modal').classList.add('hidden');
}

function addDecisionLog(msg) {
  const stream = document.getElementById('decisions-stream');
  const entry = document.createElement('div');
  entry.className = `decision-entry ${msg.event_type || 'info'}`;
  
  const time = new Date(msg.timestamp * 1000).toLocaleTimeString();
  const summary = msg.data ? (msg.data.reason || msg.data.trigger || JSON.stringify(msg.data)) : JSON.stringify(msg);

  entry.innerHTML = `<span class="time">[${time}]</span> <strong>${msg.event_type || 'EVENT'}:</strong> ${summary}`;
  stream.appendChild(entry);
  stream.scrollTop = stream.scrollHeight;
}

// ─── 2D Canvas Map Visualizer ───
function renderMap() {
  if (!mapData || !worldState) return;

  const canvas = document.getElementById('campus-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Transform coordinates: x to right, y up
  function toScreen(x, y) {
    return {
      x: mapOffsetX + x * mapScale,
      y: canvas.height - (mapOffsetY + y * mapScale)
    };
  }

  // Draw Edges / Corridors
  mapData.edges.forEach(edge => {
    const uNode = mapData.nodes[edge.from];
    const vNode = mapData.nodes[edge.to];
    if (!uNode || !vNode) return;

    const p1 = toScreen(uNode.coordinates[0], uNode.coordinates[1]);
    const p2 = toScreen(vNode.coordinates[0], vNode.coordinates[1]);

    const isBlocked = mapData.corridor_status[edge.corridor_id] === 'BLOCKED';
    const isStairs = edge.has_stairs;

    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineWidth = isBlocked ? 6 : (isStairs ? 4 : 5);
    ctx.strokeStyle = isBlocked ? '#f85149' : (isStairs ? '#d29922' : '#30363d');
    ctx.stroke();
  });

  // Draw Nodes / Waypoints
  Object.keys(mapData.nodes).forEach(nodeId => {
    const node = mapData.nodes[nodeId];
    const pt = toScreen(node.coordinates[0], node.coordinates[1]);

    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 6, 0, 2 * Math.PI);
    ctx.fillStyle = '#8b949e';
    ctx.fill();

    ctx.font = '10px Inter';
    ctx.fillStyle = '#c9d1d9';
    ctx.fillText(nodeId, pt.x + 8, pt.y + 3);
  });

  // Draw Objects
  if (worldState.objects) {
    Object.values(worldState.objects).forEach(obj => {
      const pt = toScreen(obj.location[0], obj.location[1]);
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 8, 0, 2 * Math.PI);
      ctx.fillStyle = '#bc8cff';
      ctx.fill();
      ctx.fillText(`🎒 ${obj.id}`, pt.x + 10, pt.y + 3);
    });
  }

  // Draw Robot
  const rLoc = worldState.robot.location;
  const rPt = toScreen(rLoc[0], rLoc[1]);

  ctx.beginPath();
  ctx.arc(rPt.x, rPt.y, 10, 0, 2 * Math.PI);
  ctx.fillStyle = '#58a6ff';
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = '#58a6ff';
  ctx.font = 'bold 11px JetBrains Mono';
  ctx.fillText('🤖 AURA-BOT', rPt.x + 12, rPt.y + 4);
}

// ─── Actions ───
async function submitGoal() {
  const input = document.getElementById('goal-input');
  const goal = input.value.trim();
  if (!goal) return;

  await fetch('/api/goal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal: goal })
  });
  fetchInitialState();
}

async function injectObstacle(corridorId) {
  await fetch('/api/chaos/inject_obstacle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ corridor_id: corridorId, location: [5.0, 8.0] })
  });
  fetchInitialState();
}

async function restoreCorridor(corridorId) {
  await fetch(`/api/chaos/restore_corridor?corridor_id=${corridorId}`, { method: 'POST' });
  fetchInitialState();
}

async function injectLowBattery() {
  await fetch('/api/chaos/low_battery?battery_level=15.0', { method: 'POST' });
  fetchInitialState();
}

async function triggerEstop() {
  await fetch('/api/estop', { method: 'POST' });
  fetchInitialState();
}

async function resetWorld() {
  await fetch('/api/reset', { method: 'POST' });
  fetchInitialState();
}
