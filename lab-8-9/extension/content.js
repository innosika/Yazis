// Lector on any page: a small play button next to selected text, and a mini player
// while it reads. Everything lives in a closed shadow root so the page's CSS cannot
// touch it and ours cannot leak. This script never talks to the server itself.

(() => {
  if (window.__lectorContent) return
  window.__lectorContent = true

  const host = document.createElement('lector-reader')
  host.style.cssText = 'all: initial; position: fixed; z-index: 2147483647; top: 0; left: 0; width: 0; height: 0;'
  const root = host.attachShadow({ mode: 'closed' })
  root.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; font-family: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif; }
      .fab {
        position: fixed; width: 34px; height: 34px; border-radius: 999px; border: 0; cursor: pointer;
        background: #1d3b8a; color: #fff; display: none; align-items: center; justify-content: center;
        box-shadow: 0 1px 2px rgb(0 0 0 / .12), 0 8px 20px -6px rgb(0 0 0 / .35);
        transition: transform .12s ease;
      }
      .fab:hover { transform: scale(1.06); }
      .fab:focus-visible, button:focus-visible { outline: 2px solid #ffd84d; outline-offset: 2px; }
      .fab.show { display: flex; }
      .player {
        position: fixed; right: 16px; bottom: 16px; display: none; align-items: center; gap: 4px;
        padding: 6px 6px 6px 14px; border-radius: 999px; background: #ffffff; color: #1b1d22;
        border: 1px solid #e4e3dc; box-shadow: 0 1px 2px rgb(0 0 0 / .08), 0 12px 32px -8px rgb(0 0 0 / .3);
        max-width: min(460px, calc(100vw - 32px));
      }
      .player.show { display: flex; }
      .mark { width: 10px; height: 10px; border-radius: 2px; background: #ffe57a; flex: none; }
      .text { display: grid; min-width: 0; margin: 0 6px; }
      .title { font-size: 13px; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .sub { font-size: 11.5px; color: #5c5f66; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .btn {
        width: 32px; height: 32px; border-radius: 999px; border: 0; background: transparent; color: #1b1d22;
        cursor: pointer; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; flex: none;
      }
      .btn:hover { background: #f3f3ef; }
      .btn.primary { background: #1d3b8a; color: #fff; }
      .btn.primary:hover { background: #162f72; }
      .error { color: #b42318; }
      @media (prefers-color-scheme: dark) {
        .player { background: #181c25; color: #e6e8ee; border-color: #262c38; }
        .sub { color: #a0a6b3; }
        .btn { color: #e6e8ee; }
        .btn:hover { background: #262c38; }
        .fab, .btn.primary { background: #93abff; color: #0c1532; }
      }
    </style>
    <button class="fab" part="fab" aria-label="Read the selection aloud with Lector" title="Read aloud (Alt+R)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z"/></svg>
    </button>
    <div class="player" role="region" aria-label="Lector player" aria-live="polite">
      <span class="mark" aria-hidden="true"></span>
      <span class="text"><span class="title">Lector</span><span class="sub"></span></span>
      <button class="btn" data-a="slower" aria-label="Slower" title="Slower">−</button>
      <button class="btn" data-a="faster" aria-label="Faster" title="Faster">+</button>
      <button class="btn primary" data-a="toggle" aria-label="Pause">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>
      </button>
      <button class="btn" data-a="open" aria-label="Open in Lector" title="Open in Lector">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M10 6H5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5"/></svg>
      </button>
      <button class="btn" data-a="stop" aria-label="Stop" title="Stop">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>`
  document.documentElement.appendChild(host)

  const fab = root.querySelector('.fab')
  const player = root.querySelector('.player')
  const title = root.querySelector('.title')
  const sub = root.querySelector('.sub')
  const toggle = root.querySelector('[data-a="toggle"]')
  const PAUSE = toggle.innerHTML
  const PLAY = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z"/></svg>'
  let lastText = ''
  let phase = 'idle'
  let hideTimer = 0

  function selectionText() {
    const s = window.getSelection()
    return s ? String(s).trim() : ''
  }

  function placeFab() {
    const s = window.getSelection()
    const text = selectionText()
    if (!s || !s.rangeCount || text.length < 2) {
      fab.classList.remove('show')
      return
    }
    const rects = s.getRangeAt(0).getClientRects()
    const last = rects[rects.length - 1]
    if (!last) return
    // Just under the end of the selection, so it never covers the selected words;
    // above the line instead when the selection ends near the bottom edge.
    const x = Math.max(8, Math.min(window.innerWidth - 42, last.right - 17))
    const below = last.bottom + 6
    const y = below + 34 > window.innerHeight ? Math.max(8, last.top - 40) : below
    fab.style.left = `${x}px`
    fab.style.top = `${y}px`
    fab.classList.add('show')
    lastText = text
  }

  function send(msg) {
    try {
      return chrome.runtime.sendMessage(msg)
    } catch {
      // the extension was reloaded; this old content script is orphaned
      fab.classList.remove('show')
      return Promise.resolve()
    }
  }

  document.addEventListener('mouseup', (e) => {
    if (e.composedPath().includes(host)) return
    setTimeout(placeFab, 10)
  })
  document.addEventListener('keyup', (e) => {
    if (e.shiftKey || e.key === 'Shift') setTimeout(placeFab, 10)
  })
  document.addEventListener('selectionchange', () => {
    if (!selectionText()) fab.classList.remove('show')
  })
  window.addEventListener('scroll', () => fab.classList.remove('show'), { passive: true })

  fab.addEventListener('mousedown', (e) => e.preventDefault()) // keep the selection
  fab.addEventListener('click', () => {
    const text = lastText || selectionText()
    fab.classList.remove('show')
    if (text) {
      showPlayer('Preparing the voice…', `${text.split(/\s+/).length} words selected`)
      send({ type: 'speak', text })
    }
  })

  player.addEventListener('click', async (e) => {
    const btn = e.target.closest('button')
    if (!btn) return
    const a = btn.dataset.a
    if (a === 'toggle') send({ type: 'control', action: phase === 'paused' ? 'resume' : 'pause' })
    else if (a === 'stop') { send({ type: 'control', action: 'stop' }); player.classList.remove('show') }
    else if (a === 'open') {
      const res = await send({ type: 'open', text: lastText })
      if (res && !res.ok) showPlayer('Could not open Lector', res.error || '', true)
    } else send({ type: 'control', action: a })
  })

  function showPlayer(t, s, isError = false) {
    clearTimeout(hideTimer)
    title.textContent = t
    sub.textContent = s || ''
    title.classList.toggle('error', isError)
    player.classList.add('show')
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type !== 'status') return
    phase = msg.state || msg.phase
    const p = msg.phase || msg.state
    if (p === 'loading') showPlayer('Preparing the voice…', msg.total ? `Part ${msg.index + 1} of ${msg.total}` : '')
    else if (p === 'playing') showPlayer(`Reading, part ${msg.index + 1} of ${msg.total}`, msg.preview || '')
    else if (p === 'paused') showPlayer('Paused', `Part ${msg.index + 1} of ${msg.total}`)
    else if (p === 'done') {
      showPlayer('Finished', 'Select more text to keep listening')
      hideTimer = setTimeout(() => player.classList.remove('show'), 2500)
    } else if (p === 'error') {
      showPlayer(msg.message || 'Something went wrong', 'Is Lector running? make up', true)
      hideTimer = setTimeout(() => player.classList.remove('show'), 6000)
    } else if (p === 'idle') player.classList.remove('show')
    if (msg.speed) sub.textContent = `Speed ${msg.speed.toFixed(1)}×`
    phase = p
    toggle.innerHTML = p === 'paused' ? PLAY : PAUSE
    toggle.setAttribute('aria-label', p === 'paused' ? 'Resume' : 'Pause')
  })
})()
