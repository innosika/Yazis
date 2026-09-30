// The extension's player. Same pipeline as the web app: the server segments the text,
// synthesizes each unit (cached by content) and this document plays them in order,
// fetching the next unit while the current one plays.

let session = 0
let audio = null
let state = { phase: 'idle', index: 0, total: 0 }
let settings = null
let units = []
let text = ''
let paused = false
let speedDelta = 0
const prepared = new Map()

function send(extra = {}) {
  chrome.runtime.sendMessage({ type: 'status', ...state, ...extra }).catch(() => {})
}

async function api(base, path, body) {
  const res = await fetch(base + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : 'Lector could not read this text')
  }
  return res.json()
}

function synthParams(unitText) {
  const v = settings.voice
  return {
    text: unitText,
    kind: 'text',
    voice: { id: v.voice, blend: v.blend, mix: v.mix },
    speed: Math.min(2, Math.max(0.5, v.speed + speedDelta)),
    pitch: v.pitch,
    options: settings.reading,
    priority: 'background',
  }
}

function prepare(base, i) {
  const key = `${i}:${speedDelta}`
  if (!prepared.has(key)) {
    prepared.set(key, api(base, '/api/tts/synthesize', synthParams(units[i])).then((s) => base + s.audio_url))
  }
  return prepared.get(key)
}

async function run(base, id) {
  for (let i = 0; i < units.length; i++) {
    if (id !== session) return
    state = { phase: 'loading', index: i, total: units.length }
    send()
    const url = await prepare(base, i)
    if (i + 1 < units.length) prepare(base, i + 1).catch(() => {})
    if (id !== session) return
    await new Promise((resolve, reject) => {
      audio = new Audio(url)
      audio.volume = Math.min(1, settings.voice.volume)
      audio.onended = resolve
      audio.onerror = () => reject(new Error('Audio could not be played'))
      audio.play().then(() => {
        state = { phase: paused ? 'paused' : 'playing', index: i, total: units.length }
        if (paused) audio.pause()
        send({ preview: units[i].slice(0, 90) })
      }, reject)
    })
    const gap = settings.voice.sentence_pause * 1000
    if (gap) await new Promise((r) => setTimeout(r, gap))
  }
  if (id === session) {
    state = { phase: 'done', index: units.length, total: units.length }
    send()
  }
}

async function speak(base, newText) {
  const id = ++session
  audio?.pause()
  prepared.clear()
  paused = false
  speedDelta = 0
  text = newText
  state = { phase: 'loading', index: 0, total: 0 }
  send()
  try {
    settings = await (await fetch(base + '/api/settings')).json()
    const seg = await api(base, '/api/tts/segment', { text })
    units = seg.units.map((u) => text.slice(u.start, u.end))
    if (!units.length) throw new Error('Nothing to read in the selection')
    await run(base, id)
  } catch (err) {
    if (id !== session) return
    const offline = err instanceof TypeError
    state = { phase: 'error', index: 0, total: 0 }
    send({ message: offline ? 'Lector is not running. Start it with make up.' : String(err.message || err) })
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.target !== 'offscreen') return false
  if (msg.type === 'speak') void speak(msg.base, msg.text)
  if (msg.type === 'control') {
    if (msg.action === 'pause' && audio) { paused = true; audio.pause(); state.phase = 'paused'; send() }
    if (msg.action === 'resume' && audio) { paused = false; void audio.play(); state.phase = 'playing'; send() }
    if (msg.action === 'stop') { session++; audio?.pause(); state = { phase: 'idle', index: 0, total: 0 }; send() }
    if (msg.action === 'faster' || msg.action === 'slower') {
      speedDelta = Math.round((speedDelta + (msg.action === 'faster' ? 0.1 : -0.1)) * 10) / 10
      if (audio) audio.playbackRate = Math.min(2, Math.max(0.5, (settings.voice.speed + speedDelta) / settings.voice.speed))
      send({ speed: Math.min(2, Math.max(0.5, settings.voice.speed + speedDelta)) })
    }
  }
  return false
})
