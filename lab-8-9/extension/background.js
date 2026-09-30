// Lector extension service worker: routes messages, never plays audio itself.
// Chrome stops idle service workers after ~30 s, so the player lives in an offscreen
// document, and every fetch to the local Lector server happens there or here (both
// extension contexts with host permissions: no page CORS, no Local Network Access prompt).

const DEFAULT_BASE = 'http://localhost:8100'
let listenerTab = null // tab that should receive player status updates

async function baseUrl() {
  const { base } = await chrome.storage.sync.get('base')
  return (base || DEFAULT_BASE).replace(/\/$/, '')
}

async function ensureOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] })
  if (contexts.length) return
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['AUDIO_PLAYBACK'],
    justification: 'Play the synthesized speech for the text you selected.',
  })
}

async function toPlayer(message) {
  await ensureOffscreen()
  return chrome.runtime.sendMessage({ ...message, target: 'offscreen', base: await baseUrl() })
}

async function speak(text, tabId) {
  const clean = (text || '').trim()
  if (!clean) return
  listenerTab = tabId ?? listenerTab
  await toPlayer({ type: 'speak', text: clean.slice(0, 20000) })
}

async function openInLector(text, title) {
  const base = await baseUrl()
  const res = await fetch(`${base}/api/documents/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, title: title || undefined }),
  })
  if (!res.ok) throw new Error(`Lector answered ${res.status}`)
  const doc = await res.json()
  await chrome.tabs.create({ url: `${base}/#/doc/${doc.id}` })
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: 'lector-read', title: 'Read aloud with Lector', contexts: ['selection'] })
  chrome.contextMenus.create({ id: 'lector-open', title: 'Open in Lector', contexts: ['selection'] })
})

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'lector-read') void speak(info.selectionText, tab?.id)
  if (info.menuItemId === 'lector-open') void openInLector(info.selectionText, tab?.title).catch(notifyError(tab?.id))
})

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command !== 'read-selection' || !tab?.id) return
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => String(window.getSelection() || ''),
  }).catch(() => [])
  const text = result?.result
  if (text && text.trim()) void speak(text, tab.id)
  else chrome.tabs.sendMessage(tab.id, { type: 'status', state: 'error', message: 'Select some text first' }).catch(() => {})
})

function notifyError(tabId) {
  return (err) => {
    if (tabId) chrome.tabs.sendMessage(tabId, { type: 'status', state: 'error', message: String(err.message || err) }).catch(() => {})
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.target === 'offscreen') return false
  if (msg.type === 'speak') {
    void speak(msg.text, sender.tab?.id)
  } else if (msg.type === 'control') {
    void toPlayer({ type: 'control', action: msg.action })
  } else if (msg.type === 'open') {
    openInLector(msg.text, sender.tab?.title).then(() => sendResponse({ ok: true }), (e) => sendResponse({ ok: false, error: String(e.message || e) }))
    return true
  } else if (msg.type === 'status' && sender.url?.endsWith('offscreen.html')) {
    // Player status from the offscreen document -> the page that asked, and the popup.
    if (listenerTab !== null) chrome.tabs.sendMessage(listenerTab, msg).catch(() => {})
  } else if (msg.type === 'health') {
    baseUrl()
      .then((base) => fetch(`${base}/api/health/ready`).then((r) => r.json()).then((h) => sendResponse({ ok: true, base, health: h })))
      .catch(() => baseUrl().then((base) => sendResponse({ ok: false, base })))
    return true
  } else if (msg.type === 'settings') {
    baseUrl()
      .then((base) => fetch(`${base}/api/settings`).then((r) => r.json()).then((s) => sendResponse({ ok: true, settings: s })))
      .catch(() => sendResponse({ ok: false }))
    return true
  } else if (msg.type === 'save-settings') {
    baseUrl()
      .then((base) => fetch(`${base}/api/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(msg.settings) }))
      .then(() => sendResponse({ ok: true }), () => sendResponse({ ok: false }))
    return true
  }
  return false
})
