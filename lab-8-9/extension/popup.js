const $ = (id) => document.getElementById(id)
let settings = null
let base = 'http://localhost:8100'
const VOICES = [
  ['af_heart', 'Heart, American'], ['af_bella', 'Bella, American'], ['af_nicole', 'Nicole, American'],
  ['am_michael', 'Michael, American'], ['am_fenrir', 'Fenrir, American'], ['am_puck', 'Puck, American'],
  ['bf_emma', 'Emma, British'], ['bf_isabella', 'Isabella, British'], ['bm_george', 'George, British'],
  ['bm_fable', 'Fable, British'],
]

async function init() {
  const health = await chrome.runtime.sendMessage({ type: 'health' })
  base = health?.base || base
  if (health?.ok && health.health.status === 'ready') {
    $('dot').className = 'dot ok'
    $('state').textContent = 'Ready'
  } else {
    $('dot').className = 'dot bad'
    $('state').textContent = health?.ok ? 'Preparing…' : 'Not running'
  }
  const res = await chrome.runtime.sendMessage({ type: 'settings' })
  if (!res?.ok) {
    $('read').disabled = true
    $('read').textContent = 'Start Lector with make up'
    return
  }
  settings = res.settings
  const select = $('voice')
  const known = new Set(VOICES.map((v) => v[0]))
  if (!known.has(settings.voice.voice)) VOICES.unshift([settings.voice.voice, settings.voice.voice])
  for (const [id, name] of VOICES) select.add(new Option(name, id, false, id === settings.voice.voice))
  $('speed').value = settings.voice.speed
  $('speedv').textContent = `${Number(settings.voice.speed).toFixed(2)}×`
}

function save() {
  if (settings) void chrome.runtime.sendMessage({ type: 'save-settings', settings })
}

$('voice').addEventListener('change', (e) => { settings.voice.voice = e.target.value; settings.voice.blend = null; save() })
$('speed').addEventListener('input', (e) => { $('speedv').textContent = `${Number(e.target.value).toFixed(2)}×` })
$('speed').addEventListener('change', (e) => { settings.voice.speed = Number(e.target.value); save() })
$('open').addEventListener('click', (e) => { e.preventDefault(); chrome.tabs.create({ url: base }) })
$('read').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) return
  const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => String(window.getSelection() || '') }).catch(() => [])
  const text = r?.result?.trim()
  if (!text) { $('read').textContent = 'Select some text first'; return }
  await chrome.tabs.sendMessage(tab.id, { type: 'status', phase: 'loading', index: 0, total: 0 }).catch(() => {})
  await chrome.runtime.sendMessage({ type: 'speak', text })
  window.close()
})

void init()
