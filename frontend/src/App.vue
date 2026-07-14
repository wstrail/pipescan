<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const STATUS_POLL_MS = 1000
let statusTimer = null
let dbStatsTimer = null

const robot = ref({
  connected: false,
  mode: 'standby',
  speed: 0.35,
  battery_percent: 0,
  distance_m: 0,
  last_command: 'none',
  error_code: 0,
  message: '',
  temperature_c: null,
  pitch_deg: null,
  roll_deg: null,
  obstacle_detected: false,
  obstacle_distance_m: null,
  obstacle_severity: 'none',
  obstacle_message: '',
  updated_at: ''
})

const camera = ref({
  source: 'mock://camera-0',
  enabled: true,
  resolution: '1280x720'
})

const snapshot = ref(null)
const busy = ref(false)
const error = ref('')
const reportMarkdown = ref('')
const evaluation = ref(null)
const commandSpeed = ref(0.35)
const importedDefectKeys = ref(new Set())
const currentInspectionStartedAt = ref(new Date())
const inspectionStarted = ref(false)
const autoInspectionActive = ref(false)
const dismissedObstacleKey = ref('')
const latestInspectionRecordId = ref(0)
const inspectionBaselineRecordId = ref(0)
const dbStats = ref({
  pipes: 0,
  inspections: 0,
  reports: 0,
  latestPipe: ''
})
const telemetry = ref({
  temperature_c: 32.6,
  humidity_percent: 68,
  pressure_kpa: 101.2,
  pitch_deg: 1.8,
  roll_deg: -0.6,
  signal_percent: 92,
  flow_status: 'normal'
})

const inspection = ref({
  pipe_id: 'P-001',
  pipe_length: 30,
  diameter_mm: 800,
  region_type: 'traffic',
  soil_type: 'medium',
  defects: []
})

const riskText = computed(() => {
  if (!evaluation.value) return '等待评估'
  const repair = evaluation.value.levels.repair_level
  const maintenance = evaluation.value.levels.maintenance_level
  return `${repair.level} ${repair.status} / ${maintenance.level} ${maintenance.status}`
})

const directionText = computed(() => {
  const map = {
    forward: '前进',
    backward: '后退',
    left: '左转',
    right: '右转',
    stop: '停止',
    set_speed: '调速',
    none: '待命'
  }
  return map[robot.value.last_command] || '待命'
})

const defectCount = computed(() => inspection.value.defects.length)

const autoDefectCount = computed(() => {
  return inspection.value.defects.filter((defect) => defect.source === 'auto').length
})

const obstacleAlert = computed(() => {
  if (!robot.value.obstacle_detected) return null

  const distance = robot.value.obstacle_distance_m
  const hasDistance = distance !== null && distance !== undefined
  const severity = robot.value.obstacle_severity === 'critical' ? 'critical' : 'warning'
  const title = severity === 'critical' ? '前方严重障碍' : '前方障碍提醒'
  const message = robot.value.obstacle_message || '检测到前方存在障碍，请控制员减速观察并准备停止。'

  return {
    severity,
    title,
    message,
    distanceText: hasDistance ? `${Number(distance).toFixed(2)} m` : '未知',
    key: [severity, hasDistance ? Number(distance).toFixed(1) : 'unknown', message].join('|')
  }
})

const activeAlert = computed(() => obstacleAlert.value)

const visibleObstacleAlert = computed(() => {
  if (!activeAlert.value) return null
  return activeAlert.value.key === dismissedObstacleKey.value ? null : activeAlert.value
})

// SIMULATION-ONLY: Highlights data produced by scripts/simulate_robot_sensor.py.
// Remove this computed label when the backend is connected to a real robot.
const simulationActive = computed(() => {
  return dbStats.value.latestPipe.startsWith('SIM-') || String(robot.value.message || '').includes('route=')
})

const renderedReportHtml = computed(() => renderMarkdown(reportMarkdown.value))

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function renderInline(value) {
  return escapeHtml(value)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function splitTableRow(row) {
  return row
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function renderMarkdown(markdown) {
  if (!markdown) return ''

  const lines = markdown.split(/\r?\n/)
  const html = []
  let tableRows = []
  let listItems = []

  function flushList() {
    if (!listItems.length) return
    html.push(`<ol>${listItems.map((item) => `<li>${renderInline(item)}</li>`).join('')}</ol>`)
    listItems = []
  }

  function flushTable() {
    if (!tableRows.length) return
    const [head, divider, ...body] = tableRows
    const headers = splitTableRow(head)
    const rows = body.filter((row) => row !== divider).map(splitTableRow)
    html.push('<table class="report-table">')
    html.push(`<thead><tr>${headers.map((cell) => `<th>${renderInline(cell)}</th>`).join('')}</tr></thead>`)
    html.push(`<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`)
    html.push('</table>')
    tableRows = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList()
      tableRows.push(trimmed)
      continue
    }

    flushTable()
    if (!trimmed) {
      flushList()
      continue
    }

    if (trimmed.startsWith('# ')) {
      flushList()
      html.push(`<h1>${renderInline(trimmed.slice(2))}</h1>`)
    } else if (trimmed.startsWith('## ')) {
      flushList()
      html.push(`<h2>${renderInline(trimmed.slice(3))}</h2>`)
    } else if (/^\d+\.\s+/.test(trimmed)) {
      listItems.push(trimmed.replace(/^\d+\.\s+/, ''))
    } else if (trimmed.startsWith('- ')) {
      flushList()
      html.push(`<p class="bullet">• ${renderInline(trimmed.slice(2))}</p>`)
    } else {
      flushList()
      html.push(`<p>${renderInline(trimmed)}</p>`)
    }
  }

  flushList()
  flushTable()
  return html.join('')
}

async function request(path, options = {}) {
  error.value = ''
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) {
    throw new Error(`接口请求失败：${response.status}`)
  }
  return response.json()
}

function buildDefectKey(record, defect, index) {
  return [
    record.id,
    index,
    defect.category,
    defect.code,
    defect.distance_m,
    defect.score,
    defect.description
  ].join('|')
}

function importInspectionRecords(records) {
  if (!autoInspectionActive.value) return

  const orderedRecords = [...records]
    .filter((record) => {
      const isSimulationRecord = String(record.pipe_code || '').startsWith('SIM-')
      return isSimulationRecord && Number(record.id || 0) > inspectionBaselineRecordId.value
    })
    .reverse()
  for (const record of orderedRecords) {
    const defects = Array.isArray(record.defects) ? record.defects : []
    defects.forEach((defect, index) => {
      const key = buildDefectKey(record, defect, index)
      if (importedDefectKeys.value.has(key)) return

      importedDefectKeys.value.add(key)
      inspection.value.defects.push({
        category: defect.category || 'structural',
        code: defect.code || '',
        score: Number(defect.score || 0),
        length: Number(defect.length || 0),
        distance_m: Number(defect.distance_m || 0),
        description: defect.description || '',
        source: 'auto',
        record_id: record.id,
        pipe_code: record.pipe_code
      })
    })
  }
}

function stopAutoInspection() {
  autoInspectionActive.value = false
}

function resumeAutoInspection() {
  if (autoInspectionActive.value) return
  autoInspectionActive.value = true
}

function resetInspectionForm() {
  stopAutoInspection()
  currentInspectionStartedAt.value = new Date()
  inspectionStarted.value = false
  importedDefectKeys.value = new Set()
  dismissedObstacleKey.value = ''
  inspectionBaselineRecordId.value = latestInspectionRecordId.value
  inspection.value = {
    ...inspection.value,
    pipe_id: `P-${currentInspectionStartedAt.value.toISOString().slice(0, 10).replaceAll('-', '')}`,
    defects: []
  }
  evaluation.value = null
  reportMarkdown.value = ''
}

async function prepareInspection() {
  resetInspectionForm()
  commandSpeed.value = 0
  try {
    robot.value = await request('/api/robot/reset', { method: 'POST' })
  } catch (err) {
    error.value = err.message
  }
}

function dismissObstacleAlert() {
  if (activeAlert.value) {
    dismissedObstacleKey.value = activeAlert.value.key
  }
}

async function startCurrentInspection() {
  await prepareInspection()
  inspectionStarted.value = true
  autoInspectionActive.value = true
}

function inspectionPayload() {
  return {
    ...inspection.value,
    defects: inspection.value.defects.map((defect) => ({
      category: defect.category,
      code: defect.code,
      score: Number(defect.score || 0),
      length: Number(defect.length || 0),
      distance_m: Number(defect.distance_m || 0),
      description: defect.description || ''
    }))
  }
}

async function loadStatus() {
  try {
    robot.value = await request('/api/robot/status')
    camera.value = await request('/api/camera')
    snapshot.value = await request('/api/camera/snapshot')
  } catch (err) {
    error.value = err.message
  }
}

async function refreshRobotStatus() {
  try {
    robot.value = await request('/api/robot/status')
    if (robot.value.temperature_c !== null && robot.value.temperature_c !== undefined) {
      telemetry.value.temperature_c = robot.value.temperature_c
    }
    if (robot.value.pitch_deg !== null && robot.value.pitch_deg !== undefined) {
      telemetry.value.pitch_deg = robot.value.pitch_deg
    }
    if (robot.value.roll_deg !== null && robot.value.roll_deg !== undefined) {
      telemetry.value.roll_deg = robot.value.roll_deg
    }
  } catch (err) {
    error.value = err.message
  }
}

async function loadDatabaseStats() {
  try {
    const [pipes, inspections, reports] = await Promise.all([
      request('/api/pipes'),
      request('/api/inspection/records'),
      request('/api/inspection/reports')
    ])
    dbStats.value = {
      pipes: pipes.length,
      inspections: inspections.length,
      reports: reports.length,
      latestPipe: inspections[0]?.pipe_code || pipes[0]?.pipe_code || ''
    }
    latestInspectionRecordId.value = inspections.reduce((max, record) => Math.max(max, Number(record.id || 0)), latestInspectionRecordId.value)
    if (!inspectionStarted.value) {
      inspectionBaselineRecordId.value = latestInspectionRecordId.value
    }
    importInspectionRecords(inspections)
  } catch (err) {
    error.value = err.message
  }
}

async function connectRobot() {
  busy.value = true
  try {
    robot.value = await request('/api/robot/connect', { method: 'POST' })
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function sendMotion(action) {
  busy.value = true
  try {
    robot.value = await request('/api/robot/motion', {
      method: 'POST',
      body: JSON.stringify({ action, speed: Number(commandSpeed.value || 0.35), duration_ms: 0 })
    })
    commandSpeed.value = Number(robot.value.speed || 0)
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function syncCommandSpeed() {
  try {
    robot.value = await request('/api/robot/motion', {
      method: 'POST',
      body: JSON.stringify({ action: 'set_speed', speed: Number(commandSpeed.value || 0), duration_ms: 0 })
    })
    commandSpeed.value = Number(robot.value.speed || 0)
  } catch (err) {
    error.value = err.message
  }
}

async function saveCamera() {
  busy.value = true
  try {
    camera.value = await request('/api/camera', {
      method: 'POST',
      body: JSON.stringify(camera.value)
    })
    snapshot.value = await request('/api/camera/snapshot')
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

function addDefect() {
  inspection.value.defects.push({
    category: 'structural',
    code: '',
    score: 1,
    length: 0,
    distance_m: Number(robot.value.distance_m || 0),
    description: '',
    source: 'manual'
  })
}

function removeDefect(index) {
  inspection.value.defects.splice(index, 1)
}

async function evaluateOnly() {
  busy.value = true
  try {
    evaluation.value = await request('/api/inspection/evaluate', {
      method: 'POST',
      body: JSON.stringify(inspectionPayload())
    })
    reportMarkdown.value = ''
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function generateReport() {
  busy.value = true
  try {
    const result = await request('/api/inspection/report', {
      method: 'POST',
      body: JSON.stringify(inspectionPayload())
    })
    evaluation.value = result.evaluation
    reportMarkdown.value = result.markdown
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await prepareInspection()
  loadDatabaseStats()
  statusTimer = window.setInterval(refreshRobotStatus, STATUS_POLL_MS)
  dbStatsTimer = window.setInterval(loadDatabaseStats, STATUS_POLL_MS * 3)
})

onUnmounted(() => {
  if (statusTimer) {
    window.clearInterval(statusTimer)
  }
  if (dbStatsTimer) {
    window.clearInterval(dbStatsTimer)
  }
  stopAutoInspection()
})
</script>

<template>
  <main class="camera-shell">
    <header class="app-header">
      <div>
        <p class="eyebrow">PipeScan Live Console</p>
        <h1>管道机器人摄像控制台</h1>
      </div>
      <div class="header-actions">
        <span :class="['signal', robot.connected ? 'online' : 'offline']">
          {{ robot.connected ? 'ONLINE' : 'OFFLINE' }}
        </span>
        <span v-if="simulationActive" class="simulation-badge">模拟传感器模式</span>
        <button class="primary" :disabled="busy" @click="connectRobot">连接机器人</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="operator-layout">
      <section class="viewfinder-panel">
        <div class="camera-body">
          <div class="viewfinder">
            <div class="hud hud-top">
              <div class="hud-group">
                <strong>{{ directionText }}</strong>
                <span>[ {{ inspection.pipe_id }} ]</span>
                <span>里程 {{ robot.distance_m }} m</span>
              </div>
              <div class="hud-group right">
                <span>电量 {{ robot.battery_percent }}%</span>
                <span>{{ camera.enabled ? '摄像在线' : '摄像关闭' }}</span>
              </div>
            </div>

            <div class="hud hud-left">
              <span>方向 {{ directionText }}</span>
              <span>速度 {{ Number(robot.speed || 0).toFixed(2) }}</span>
              <span>管径 {{ inspection.diameter_mm }}mm</span>
              <span>长度 {{ inspection.pipe_length }}m</span>
              <span>缺陷 {{ defectCount }}处</span>
            </div>

            <div class="hud hud-right">
              <span>温度 {{ telemetry.temperature_c }}°C</span>
              <span>湿度 {{ telemetry.humidity_percent }}%</span>
              <span>压力 {{ telemetry.pressure_kpa }}kPa</span>
              <span>姿态 P{{ telemetry.pitch_deg }}° R{{ telemetry.roll_deg }}°</span>
              <span>信号 {{ telemetry.signal_percent }}%</span>
            </div>

            <div class="camera-feed">
              <div class="video-placeholder">
                <strong>{{ camera.enabled ? '视频已启用' : '视频已关闭' }}</strong>
                <span>{{ camera.resolution }}</span>
                <small>{{ snapshot?.captured_at || '等待帧数据' }}</small>
              </div>
            </div>

            <div v-if="visibleObstacleAlert" :class="['obstacle-banner', visibleObstacleAlert.severity]">
              <button class="alert-close" aria-label="关闭障碍提醒" @click="dismissObstacleAlert">×</button>
              <strong>{{ visibleObstacleAlert.title }}</strong>
              <span>距离 {{ visibleObstacleAlert.distanceText }} · {{ visibleObstacleAlert.message }}</span>
            </div>

            <div class="hud hud-bottom">
              <div class="exposure-card">当前动作 {{ directionText }}</div>
              <div class="exposure-card distance-card">当前距离 {{ robot.distance_m }} m</div>
              <div class="exposure-card">风险 {{ riskText }}</div>
            </div>
          </div>
        </div>

        <div class="camera-settings">
          <label>视频源<input v-model="camera.source" /></label>
          <label>分辨率<input v-model="camera.resolution" /></label>
          <label class="check"><input v-model="camera.enabled" type="checkbox" /> 启用摄像头</label>
          <button @click="saveCamera">保存摄像头配置</button>
        </div>
      </section>

      <aside class="side-stack">
        <section class="panel control-panel">
          <h2>运动控制</h2>
          <div class="control-layout">
            <div>
              <div class="status-grid">
                <div><span>模式</span><strong>{{ robot.mode }}</strong></div>
                <div><span>电量</span><strong>{{ robot.battery_percent }}%</strong></div>
                <div><span>里程</span><strong>{{ robot.distance_m }}m</strong></div>
                <div><span>指令</span><strong>{{ robot.last_command }}</strong></div>
              </div>
              <div v-if="visibleObstacleAlert" :class="['control-alert', visibleObstacleAlert.severity]">
                <div>
                  <span>障碍报警</span>
                  <strong>{{ visibleObstacleAlert.title }}</strong>
                  <button class="alert-dismiss" @click="dismissObstacleAlert">关闭</button>
                </div>
                <p>{{ visibleObstacleAlert.message }}</p>
                <small>前方距离：{{ visibleObstacleAlert.distanceText }}</small>
              </div>
              <div class="database-stats">
                <div class="database-stats-title">
                  <span>数据入库</span>
                  <strong v-if="simulationActive">模拟数据</strong>
                </div>
                <div class="database-stats-grid">
                  <div><span>管段</span><strong>{{ dbStats.pipes }}</strong></div>
                  <div><span>巡检</span><strong>{{ dbStats.inspections }}</strong></div>
                  <div><span>报告</span><strong>{{ dbStats.reports }}</strong></div>
                </div>
                <small>最新管段：{{ dbStats.latestPipe || '暂无' }}</small>
              </div>
              <label class="speed-control">
                设定速度 {{ Number(commandSpeed || 0).toFixed(2) }}
                <input
                  v-model.number="commandSpeed"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  @change="syncCommandSpeed"
                />
              </label>
            </div>
            <div class="dpad">
              <button @click="sendMotion('forward')">↑</button>
              <button @click="sendMotion('left')">←</button>
              <button class="stop" @click="sendMotion('stop')">■</button>
              <button @click="sendMotion('right')">→</button>
              <button @click="sendMotion('backward')">↓</button>
            </div>
          </div>
        </section>
      </aside>
    </section>

    <section class="workbench">
      <section class="panel inspection-panel">
        <div class="section-title">
          <div>
            <p class="panel-kicker">Inspection Input</p>
            <h2>检测数据</h2>
          </div>
          <div class="actions">
            <button @click="startCurrentInspection">新建巡检</button>
            <button v-if="inspectionStarted && autoInspectionActive" class="ghost-neutral" @click="stopAutoInspection">停止录入</button>
            <button v-else-if="inspectionStarted" class="ghost-neutral" @click="resumeAutoInspection">继续录入</button>
            <button @click="addDefect">新增缺陷</button>
            <button @click="evaluateOnly">计算风险</button>
            <button class="primary" @click="generateReport">生成报告</button>
          </div>
        </div>
        <div class="inspection-sync">
          <span>手动录入与自动读入共用此表</span>
          <strong>{{ autoInspectionActive ? '自动录入中' : '未开始自动录入' }} · 自动缺陷 {{ autoDefectCount }} 条</strong>
          <small>仅显示本次巡检新增缺陷，历史数据保留在后台</small>
        </div>

        <div class="form-grid">
          <label>管段编号<input v-model="inspection.pipe_id" /></label>
          <label>长度(m)<input v-model.number="inspection.pipe_length" type="number" min="1" /></label>
          <label>管径(mm)<input v-model.number="inspection.diameter_mm" type="number" min="1" /></label>
          <label>
            区域
            <select v-model="inspection.region_type">
              <option value="central">中心区域</option>
              <option value="traffic">交通干道</option>
              <option value="normal">一般区域</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label>
            土质
            <select v-model="inspection.soil_type">
              <option value="weak">软弱土</option>
              <option value="medium">一般土</option>
              <option value="strong">稳定土</option>
              <option value="unknown">未知</option>
            </select>
          </label>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>距离</th>
                <th>类型</th>
                <th>代码</th>
                <th>分值</th>
                <th>长度</th>
                <th>描述</th>
                <th>来源</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(defect, index) in inspection.defects" :key="index">
                <td><input v-model.number="defect.distance_m" type="number" min="0" /></td>
                <td>
                  <select v-model="defect.category">
                    <option value="structural">结构</option>
                    <option value="functional">功能</option>
                  </select>
                </td>
                <td><input v-model="defect.code" /></td>
                <td><input v-model.number="defect.score" type="number" min="0" max="10" /></td>
                <td><input v-model.number="defect.length" type="number" min="0" /></td>
                <td><input v-model="defect.description" /></td>
                <td>
                  <span :class="['source-pill', defect.source === 'auto' ? 'auto' : 'manual']">
                    {{ defect.source === 'auto' ? '自动' : '手动' }}
                  </span>
                </td>
                <td><button class="ghost" @click="removeDefect(index)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel result-panel">
        <div class="section-title">
          <div>
            <p class="panel-kicker">Assessment Report</p>
            <h2>评估与报告</h2>
          </div>
        </div>
        <div class="risk">{{ riskText }}</div>
        <div class="result-body">
          <pre v-if="evaluation">{{ JSON.stringify(evaluation.parameters, null, 2) }}</pre>
          <div v-if="reportMarkdown" class="report-preview" v-html="renderedReportHtml"></div>
          <div v-else class="empty-report">
            <strong>尚未生成报告</strong>
            <span>填写检测数据后点击“生成报告”，这里会显示渲染后的报告内容。</span>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>
