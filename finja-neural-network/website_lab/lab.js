const style = document.createElement('style');
style.textContent = `
  body, html {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #050505;
    font-family: 'Courier New', Courier, monospace;
  }
  #ui-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 10;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 20px;
    box-sizing: border-box;
  }
  .hud-top {
    display: flex;
    justify-content: space-between;
    pointer-events: auto;
  }
  .hud-panel {
    background: rgba(0, 255, 255, 0.1);
    border: 2px solid #00ffff;
    padding: 10px 20px;
    color: #00ffff;
    text-transform: uppercase;
    letter-spacing: 2px;
    box-shadow: 0 0 15px rgba(0, 255, 255, 0.3);
    text-shadow: 0 0 5px #00ffff;
  }
  .bottom-controls {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 30px;
    pointer-events: auto;
    margin-bottom: 20px;
  }
  .powerup-btn {
    background: #4e342e;
    border: 3px solid #795548;
    border-radius: 50%;
    width: 70px;
    height: 70px;
    cursor: pointer;
    font-size: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
    box-shadow: 0 0 10px #000;
  }
  .powerup-btn:hover {
    transform: scale(1.1);
    box-shadow: 0 0 20px #ffeb3b;
  }
  .powerup-btn:active {
    transform: scale(0.9);
  }
  .meter-container {
    width: 200px;
    height: 20px;
    background: #222;
    border: 2px solid #fff;
    position: relative;
  }
  #cocoa-meter-fill {
    width: 0%;
    height: 100%;
    background: linear-gradient(90deg, #4e342e, #795548);
    transition: width 0.3s;
  }
  canvas {
    display: block;
  }
  /* Sidebar Styles */
  #chaos-sidebar {
    position: fixed;
    top: 0;
    right: -320px;
    width: 300px;
    height: 100%;
    background: linear-gradient(135deg, rgba(255, 0, 255, 0.2), rgba(0, 255, 255, 0.2), rgba(255, 255, 0, 0.2));
    backdrop-filter: blur(15px);
    border-left: 2px solid rgba(255, 255, 255, 0.5);
    z-index: 100;
    transition: right 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    padding: 20px;
    box-sizing: border-box;
    color: white;
    box-shadow: -5px 0 25px rgba(0,0,0,0.5);
    overflow-y: auto;
  }
  #chaos-sidebar.open {
    right: 0;
  }
  .sidebar-toggle {
    position: absolute;
    left: -50px;
    top: 20px;
    width: 50px;
    height: 50px;
    background: linear-gradient(45deg, #ff00ff, #00ffff);
    border: none;
    border-radius: 10px 0 0 10px;
    cursor: pointer;
    font-size: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: -2px 0 10px rgba(0,0,0,0.3);
  }
  .sidebar-header {
    font-size: 1.5rem;
    margin-bottom: 20px;
    text-align: center;
    text-shadow: 0 0 10px #fff;
  }
  .chaos-control {
    margin-bottom: 30px;
    text-align: center;
  }
  .toggle-switch {
    position: relative;
    display: inline-block;
    width: 60px;
    height: 34px;
  }
  .toggle-switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #333;
    transition: .4s;
    border-radius: 34px;
  }
  .slider:before {
    position: absolute;
    content: "";
    height: 26px; width: 26px;
    left: 4px; bottom: 4px;
    background-color: white;
    transition: .4s;
    border-radius: 50%;
  }
  input:checked + .slider { background: linear-gradient(45deg, #ff00ff, #00ffff); }
  input:checked + .slider:before { transform: translateX(26px); }
  .glitter-log {
    background: rgba(0,0,0,0.3);
    border-radius: 10px;
    padding: 10px;
    height: 200px;
    overflow-y: auto;
    font-size: 0.8rem;
    border: 1px solid rgba(255,255,255,0.2);
  }
  .log-entry {
    margin-bottom: 5px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 2px;
  }
  .fox-icon {
    display: inline-block;
    animation: float 3s ease-in-out infinite;
  }
  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }
`;
document.head.appendChild(style);

const canvas = document.createElement('canvas');
const ctx = canvas.getContext('2d');
document.body.appendChild(canvas);

const uiLayer = document.createElement('div');
uiLayer.id = 'ui-layer';

// Sidebar Elements
const sidebar = document.createElement('div');
sidebar.id = 'chaos-sidebar';

const sidebarToggle = document.createElement('button');
sidebarToggle.className = 'sidebar-toggle';
sidebarToggle.innerHTML = '🦊';
sidebar.appendChild(sidebarToggle);

const sidebarHeader = document.createElement('div');
sidebarHeader.className = 'sidebar-header';
sidebarHeader.innerHTML = 'YourAI’s Creative Chaos <span class="fox-icon">🦊</span>';
sidebar.appendChild(sidebarHeader);

const chaosControl = document.createElement('div');
chaosControl.className = 'chaos-control';
chaosControl.innerHTML = `
  <p>CHAOS MODE</p>
  <label class="toggle-switch">
    <input type="checkbox" id="chaos-toggle">
    <span class="slider"></span>
  </label>
`;
sidebar.appendChild(chaosControl);

const logHeader = document.createElement('div');
logHeader.innerHTML = '<strong>GLITTER LOG</strong>';
sidebar.appendChild(logHeader);

const glitterLog = document.createElement('div');
glitterLog.className = 'glitter-log';
sidebar.appendChild(glitterLog);

document.body.appendChild(sidebar);

// HUD Elements
const hudTop = document.createElement('div');
hudTop.className = 'hud-top';

const statusPanel = document.createElement('div');
statusPanel.className = 'hud-panel';
statusPanel.textContent = 'STATUS: SECURE';

const inventoryPanel = document.createElement('div');
inventoryPanel.className = 'hud-panel';
inventoryPanel.textContent = 'GLITTER-GLUE: 10';

hudTop.appendChild(statusPanel);
hudTop.appendChild(inventoryPanel);

const bottomControls = document.createElement('div');
bottomControls.className = 'bottom-controls';

const cocoaMeterContainer = document.createElement('div');
cocoaMeterContainer.className = 'meter-container';
const cocoaMeterFill = document.createElement('div');
cocoaMeterFill.id = 'cocoa-meter-fill';
cocoaMeterContainer.appendChild(cocoaMeterFill);

const cocoaBtn = document.createElement('button');
cocoaBtn.className = 'powerup-btn';
cocoaBtn.innerHTML = '☕';
cocoaBtn.title = 'Activate Cocoa Vortex';

bottomControls.appendChild(cocoaMeterContainer);
bottomControls.appendChild(cocoaBtn);

uiLayer.appendChild(hudTop);
uiLayer.appendChild(bottomControls);
document.body.appendChild(uiLayer);

let width, height;
let particles = [];
let raids = [];
let barriers = [];
let stars = [];
let foxSpirits = [];
let mouseX = 0;
let mouseY = 0;
let isMouseDown = false;

// Game State
let glueCount = 10;
let cocoaMeter = 0;
let isPowerUpActive = false;
let powerUpTimer = 0;
let denHealth = 100;
let lastSpawnTime = 0;
let isChaosMode = false;
let nebulaTime = 0;

const den = {
  x: 0,
  y: 0,
  radius: 50
};

function resize() {
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = width;
  canvas.height = height;
  den.x = width / 2;
  den.y = height / 2;
  initStars();
}

function initStars() {
  stars = [];
  for (let i = 0; i < 200; i++) {
    stars.push({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 2,
      opacity: Math.random(),
      speed: Math.random() * 0.5 + 0.1
    });
  }
}

window.addEventListener('resize', resize);
resize();

class Particle {
  constructor(x, y, color, size, vx, vy, life, isGlitter = false, isFox = false) {
    this.x = x;
    this.y = y;
    this.color = color;
    this.size = size;
    this.vx = vx;
    this.vy = vy;
    this.life = life;
    this.maxLife = life;
    this.isGlitter = isGlitter;
    this.isFox = isFox;
  }

  update() {
    this.x += this.vx;
    this.y += this.vy;
    
    if (isChaosMode && !this.isFox) {
        this.vy -= 0.1; // Inverted gravity for normal particles
    }

    this.life -= 0.02;
  }

  draw(ctx) {
    ctx.globalAlpha = this.life / this.maxLife;
    ctx.fillStyle = this.color;
    ctx.beginPath();
    if (this.isFox) {
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.shadowBlur = 15;
        ctx.shadowColor = this.color;
    } else if (this.isGlitter) {
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    } else {
      ctx.rect(this.x, this.y, this.size, this.size);
    }
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  }
}

class Raid {
  constructor() {
    const side = Math.floor(Math.random() * 4);
    if (side === 0) { this.x = Math.random() * width; this.y = -50; }
    else if (side === 1) { this.x = width + 50; this.y = Math.random() * height; }
    else if (side === 2) { this.x = Math.random() * width; this.y = height + 50; }
    else { this.x = -50; this.y = Math.random() * height; }

    const angle = Math.atan2(den.y - this.y, den.x - this.x);
    const speed = 2 + Math.random() * 3;
    this.vx = Math.cos(angle) * speed;
    this.vy = Math.sin(angle) * speed;
    this.size = 15 + Math.random() * 15;
    this.color = '#ff0033';
    this.glitchOffset = 0;
  }

  update() {
    this.x += this.vx;
    this.y += this.vy;
    this.glitchOffset = Math.sin(Date.now() * 0.05) * 5;
  }

  draw(ctx) {
    ctx.save();
    ctx.translate(this.x + this.glitchOffset, this.y);
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 2;
    ctx.shadowBlur = 10;
    ctx.shadowColor = this.color;
    ctx.beginPath();
    ctx.moveTo(0, -this.size/2);
    ctx.lineTo(this.size/2, this.size/2);
    ctx.lineTo(-this.size/2, this.size/2);
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
  }
}

class Barrier {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.radius = 40;
    this.life = 1.0;
    this.color = '#00ffff';
  }

  update() {
    this.life -= 0.02;
  }

  draw(ctx) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.radius * this.life, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(0, 255, 255, ${this.life})`;
    ctx.lineWidth = 5;
    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.restore();
  }
}

canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  mouseX = e.clientX - rect.left;
  mouseY = e.clientY - rect.top;

  if (isPowerUpActive) {
    for (let i = 0; i < 5; i++) {
      particles.push(new Particle(
        mouseX, mouseY, 
        '#ff00ff', 
        Math.random() * 8 + 2, 
        (Math.random() - 0.5) * 10, 
        (Math.random() - 0.5) * 10, 
        1.0, 
        true
      ));
    }
  }
});

canvas.addEventListener('mousedown', (e) => {
  if (glueCount > 0 && !isPowerUpActive) {
    barriers.push(new Barrier(mouseX, mouseY));
    glueCount--;
    inventoryPanel.textContent = `GLITTER-GLUE: ${glueCount}`;
    
    for (let i = 0; i < 15; i++) {
      particles.push(new Particle(
        mouseX, mouseY, 
        '#00ffff', 
        Math.random() * 4, 
        (Math.random() - 0.5) * 8, 
        (Math.random() - 0.5) * 8, 
        1.0, 
        true
      ));
    }
  }

  if (isChaosMode) {
    // Spawn Fox Spirit
    for (let i = 0; i < 10; i++) {
        foxSpirits.push(new Particle(
            mouseX, mouseY,
            Math.random() > 0.5 ? '#ff9800' : '#ffffff',
            Math.random() * 6 + 4,
            (Math.random() - 0.5) * 12,
            (Math.random() - 0.5) * 12,
            1.5,
            false,
            true
        ));
    }
    addLogEntry("✨ Chaos Sparkle!");
  }
});

cocoaBtn.addEventListener('click', () => {
  if (cocoaMeter >= 100) {
    isPowerUpActive = true;
    powerUpTimer = 300;
    cocoaMeter = 0;
    cocoaMeterFill.style.width = '0%';
  }
});

// Sidebar Logic
sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
});

const chaosToggle = document.getElementById('chaos-toggle');
chaosToggle.addEventListener('change', (e) => {
    isChaosMode = e.target.checked;
    if (isChaosMode) {
        addLogEntry("🌀 CHAOS ACTIVATED!");
    } else {
        addLogEntry("🛡️ Chaos Stabilized.");
    }
});

function addLogEntry(text) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.textContent = `[${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}] ${text}`;
    glitterLog.prepend(entry);
}

function spawnRaid() {
  const now = Date.now();
  if (now - lastSpawnTime > 1500 - Math.min(1000, denHealth * 10)) {
    raids.push(new Raid());
    lastSpawnTime = now;
  }
}

function update() {
  spawnRaid();
  nebulaTime += 0.01;

  if (isPowerUpActive) {
    powerUpTimer--;
    if (powerUpTimer <= 0) isPowerUpActive = false;
    
    for (let i = 0; i < 3; i++) {
      particles.push(new Particle(
        mouseX, mouseY,
        Math.random() > 0.5 ? '#ffffff' : '#4e342e',
        Math.random() * 6 + 2,
        (Math.random() - 0.5) * 15,
        (Math.random() - 0.5) * 15,
        1.0
      ));
    }
  }

  // Update Fox Spirits
  for (let i = foxSpirits.length - 1; i >= 0; i--) {
    foxSpirits[i].update();
    if (foxSpirits[i].life <= 0) foxSpirits.splice(i, 1);
  }

  // Update Raids
  for (let i = raids.length - 1; i >= 0; i--) {
    const r = raids[i];
    r.update();

    let deflected = false;
    for (let b of barriers) {
      const dist = Math.hypot(r.x - b.x, r.y - b.y);
      if (dist < b.radius + r.size/2) {
        const angle = Math.atan2(r.y - b.y, r.x - b.x);
        r.vx = Math.cos(angle) * 8;
        r.vy = Math.sin(angle) * 8;
        deflected = true;
        particles.push(new Particle(r.x, r.y, '#00ffff', 3, r.vx, r.vy, 0.5, true));
      }
    }

    const distToDen = Math.hypot(r.x - den.x, r.y - den.y);
    if (distToDen < den.radius) {
      denHealth -= 10;
      raids.splice(i, 1);
      statusPanel.textContent = `STATUS: ${denHealth <= 0 ? 'CRITICAL' : 'UNDER ATTACK'}`;
      statusPanel.style.color = '#ff0033';
      statusPanel.style.borderColor = '#ff0033';
      continue;
    }

    if (r.x < -100 || r.x > width + 100 || r.y < -100 || r.y > height + 100) {
      raids.splice(i, 1);
      cocoaMeter = Math.min(100, cocoaMeter + 5);
      cocoaMeterFill.style.width = `${cocoaMeter}%`;
      if (glueCount < 20) glueCount++;
      inventoryPanel.textContent = `GLITTER-GLUE: ${glueCount}`;
    }
  }

  for (let i = barriers.length - 1; i >= 0; i--) {
    barriers[i].update();
    if (barriers[i].life <= 0) barriers.splice(i, 1);
  }

  for (let i = particles.length - 1; i >= 0; i--) {
    particles[i].update();
    if (particles[i].life <= 0) particles.splice(i, 1);
  }

  if (denHealth <= 0) {
    statusPanel.textContent = 'STATUS: DEN BREACHED';
    statusPanel.style.color = '#ff0000';
  }
}

function draw() {
  // Background
  if (isChaosMode) {
    const grad = ctx.createRadialGradient(width/2, height/2, 0, width/2, height/2, width);
    grad.addColorStop(0, `hsla(${nebulaTime * 50 % 360}, 70%, 20%, 1)`);
    grad.addColorStop(0.5, `hsla(${(nebulaTime * 50 + 120) % 360}, 70%, 10%, 1)`);
    grad.addColorStop(1, '#050505');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);
  } else {
    ctx.fillStyle = '#050505';
    ctx.fillRect(0, 0, width, height);
  }

  // Starfield
  stars.forEach(s => {
    ctx.fillStyle = `rgba(255, 255, 255, ${s.opacity})`;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
    ctx.fill();
    s.y += s.speed;
    if (s.y > height) s.y = 0;
  });

  // Draw Den
  ctx.save();
  ctx.shadowBlur = 20;
  ctx.shadowColor = '#ff9800';
  ctx.fillStyle = '#ff9800';
  ctx.beginPath();
  ctx.arc(den.x, den.y, den.radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Draw Entities
  barriers.forEach(b => b.draw(ctx));
  raids.forEach(r => r.draw(ctx));
  particles.forEach(p => p.draw(ctx));
  foxSpirits.forEach(f => f.draw(ctx));
}

function loop() {
  update();
  draw();
  requestAnimationFrame(loop);
}

loop();