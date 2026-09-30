/**
 * The voice loop: microphone -> utterance -> recognition -> command -> action -> feedback.
 *
 * Every step is visible to the user: the mic orb shows listening / hearing /
 * recognizing, the HUD line says what was heard and what Lector did about it, a short
 * sound or a spoken reply confirms it, and the Activity panel keeps the history with
 * engines and timings. When the tab is in the background a system notification can
 * carry the same message.
 */

import { earcons } from '@/audio/earcons'
import { encodeWav } from '@/audio/wav'
import { api, ApiError } from '@/lib/api'
import type { Recognition } from '@/lib/types'
import { getEngine, usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { micLevel, useVoice } from '@/stores/voice'

import { runCommand } from './actions'
import type { Microphone } from './mic'

let mic: Microphone | null = null
let speechStartedAt = 0
let pausedForTalk = false // push-to-talk paused the reading and should resume it
let busy = false
let singleShot = false // tap-to-talk: listen for one utterance, then switch off
let singleShotTimer = 0
let echoHits: number[] = [] // times Lector recently heard its own voice
let echoTipShown = 0

function voice() {
  return useVoice.getState()
}

function isReading(): boolean {
  const s = usePlayer.getState().status
  return s === 'playing' || s === 'loading'
}

// The VAD model and ONNX runtime (~800 KB of script) load only when the mic is first used.
async function getMic(): Promise<Microphone> {
  if (mic) return mic
  const { Microphone } = await import('./mic')
  mic ??= new Microphone({
    onSpeechStart: () => {
      speechStartedAt = performance.now()
      if (voice().mic === 'listening') voice().setMic('hearing')
      if (isReading()) getEngine().duck(true)
    },
    onMisfire: () => {
      getEngine().duck(false)
      if (voice().mic === 'hearing') voice().setMic(micOnState())
    },
    onLevel: (p) => micLevel.emit(p),
    onSpeechEnd: (audio) => void handleUtterance(audio),
  })
  return mic
}

function micOnState(): 'listening' | 'off' {
  const { mode } = useSettings.getState().profile.listening
  return mode === 'hands-free' || voice().holding || singleShot ? 'listening' : 'off'
}

function endSingleShot(): void {
  window.clearTimeout(singleShotTimer)
  singleShot = false
  void mic?.stop()
  voice().setMic('off')
}

function notify(title: string, body: string): void {
  const { system_notifications } = useSettings.getState().profile.listening
  if (!system_notifications || !document.hidden || !('Notification' in window)) return
  if (Notification.permission === 'granted') new Notification(title, { body, silent: true })
}

async function handleUtterance(audio: Float32Array): Promise<void> {
  if (busy) return
  busy = true
  const endedAt = performance.now()
  const { listening } = useSettings.getState().profile
  const player = usePlayer.getState()
  const playing = isReading()
  voice().setMic('recognizing')
  let result: Recognition
  try {
    result = await api.recognize(encodeWav(audio), {
      language: listening.language,
      mode: 'command',
      engine: listening.engine,
      playing,
      played_text: playing ? getEngine().spokenBetween(speechStartedAt - 900, endedAt) : '',
      document_id: player.doc?.id ?? null,
      llm_fallback: listening.llm_fallback,
    })
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Recognition failed'
    getEngine().duck(false)
    voice().showHud({ tone: 'error', text: message })
    voice().setMic(micOnState())
    finishTalk()
    busy = false
    if (singleShot) endSingleShot()
    return
  }
  try {
    await handleResult(result, playing)
  } finally {
    getEngine().duck(false)
    busy = false
    if (singleShot) endSingleShot()
    else if (voice().mic !== 'off') voice().setMic(micOnState())
  }
}

async function handleResult(r: Recognition, playing: boolean): Promise<void> {
  const { confirmations } = useSettings.getState().profile.listening
  const outcome = r.outcome
  const match = outcome?.match ?? null
  const base = {
    transcript: r.transcript,
    engine: r.engine,
    asrMs: r.asr_ms,
    matchMs: outcome?.match_ms ?? 0,
    notes: r.notes,
  }
  for (const note of r.notes) voice().showHud({ tone: 'warning', text: note }, 2500)

  if (r.rejected) {
    voice().log({ ...base, command: null, title: null, method: null, confidence: null, rejected: r.rejected, result: 'Ignored' })
    // Echo of Lector's own voice is expected while reading; don't make noise about it,
    // unless it keeps happening: then say how to fix it.
    if (r.rejected === 'echo') {
      const now = Date.now()
      echoHits = [...echoHits.filter((t) => now - t < 30_000), now]
      if (echoHits.length >= 3 && now - echoTipShown > 120_000) {
        echoTipShown = now
        voice().showHud({ tone: 'warning', text: 'The microphone hears the reading voice', detail: 'Use headphones or push-to-talk' }, 6000)
      }
    } else if (!playing) {
      voice().showHud({ tone: 'neutral', text: 'Didn’t catch that', detail: r.rejected })
    }
    finishTalk()
    return
  }
  if (!match) {
    const hint = outcome?.suggestions[0]
    voice().log({ ...base, command: null, title: null, method: null, confidence: null, rejected: 'no command', result: 'Not understood' })
    voice().showHud({
      tone: 'neutral',
      text: `“${r.transcript}”`,
      detail: hint && hint.confidence > 0.55 ? `Did you mean “${hint.phrase}”?` : 'That is not one of the commands',
    }, 4500)
    if (confirmations !== 'off') earcons.notUnderstood()
    finishTalk()
    return
  }

  const wasPlaying = playing || pausedForTalk
  const res = await runCommand(match.command, match.slots, { wasPlaying, source: 'voice' }, match.steps)
  const reply = match.reply && !match.builtin ? match.reply : res.reply
  voice().log({
    ...base, command: match.command, title: match.title, method: match.method, confidence: match.confidence,
    rejected: null, result: res.hud,
  })
  voice().showHud({ tone: res.tone === 'error' ? 'error' : res.tone === 'warning' ? 'warning' : 'success', text: `“${r.transcript.replace(/[.!?]$/, '')}”`, detail: res.hud }, 3600)
  notify('Lector', `${match.title}: ${res.hud}`)

  const readingNow = isReading()
  // A reply the user wrote for their own command is always spoken (unless feedback is off).
  const customReply = Boolean(match.reply && !match.builtin)
  if (reply && !readingNow && (confirmations === 'voice' || (customReply && confirmations !== 'off'))) {
    void getEngine().say(reply).catch(() => undefined)
  } else if (confirmations !== 'off') {
    earcons.recognized()
  }
  if (pausedForTalk && !res.handledPlayback) {
    pausedForTalk = false
    void usePlayer.getState().play()
  }
  pausedForTalk = false
}

function finishTalk(): void {
  if (pausedForTalk) {
    pausedForTalk = false
    void usePlayer.getState().play()
  }
}

// ------------------------------------------------------------------ public controls

export async function startListening(): Promise<void> {
  const v = voice()
  if (v.mic !== 'off' && v.mic !== 'error') return
  v.setMic('starting')
  try {
    await (await getMic()).start()
    applyProfile()
    v.setMic('listening')
    if (useSettings.getState().profile.listening.confirmations !== 'off') earcons.listening()
  } catch (err) {
    const denied = err instanceof DOMException && err.name === 'NotAllowedError'
    const message = denied
      ? 'Microphone access is blocked. Allow it in the browser’s site settings.'
      : 'The microphone could not start.'
    v.setMic('error', message)
    v.showHud({ tone: 'error', text: message }, 6000)
  }
}

export async function stopListening(silent = false): Promise<void> {
  await mic?.stop()
  voice().setMic('off')
  if (!silent && useSettings.getState().profile.listening.confirmations !== 'off') earcons.off()
}

/** Push-to-talk: press. Reading pauses so the microphone hears only the user. */
export async function talkStart(): Promise<void> {
  const v = voice()
  if (v.holding) return
  v.setHolding(true)
  if (isReading()) {
    pausedForTalk = true
    await usePlayer.getState().pause()
  }
  getEngine().stopSaying()
  await startListening()
}

/** Push-to-talk: release. The utterance in progress is submitted. */
export async function talkEnd(): Promise<void> {
  const v = voice()
  if (!v.holding) return
  v.setHolding(false)
  await mic?.stop()
  window.setTimeout(() => {
    // Nothing was said: put the reading back.
    if (!busy && voice().mic !== 'recognizing') {
      voice().setMic('off')
      finishTalk()
    }
  }, 350)
}

/** Tap-to-talk: listen for a single command (up to 8 s), then switch off. */
export async function talkTap(): Promise<void> {
  if (voice().mic !== 'off' && voice().mic !== 'error') {
    endSingleShot()
    finishTalk()
    return
  }
  singleShot = true
  if (isReading()) {
    pausedForTalk = true
    await usePlayer.getState().pause()
  }
  getEngine().stopSaying()
  await startListening()
  window.clearTimeout(singleShotTimer)
  singleShotTimer = window.setTimeout(() => {
    if (singleShot && !busy && voice().mic !== 'recognizing' && voice().mic !== 'hearing') {
      endSingleShot()
      finishTalk()
      voice().showHud({ tone: 'neutral', text: 'Heard nothing', detail: 'Tap the microphone and say a command' })
    }
  }, 8000)
}

export function applyProfile(): void {
  const { sensitivity, mode } = useSettings.getState().profile.listening
  mic?.setProfile(mode === 'hands-free' && isReading() ? 'reading' : 'command', sensitivity)
}

// Keep the VAD profile in step with reading state and settings.
usePlayer.subscribe((s, prev) => {
  if (s.status !== prev.status) applyProfile()
})
useSettings.subscribe((s, prev) => {
  if (s.profile.listening !== prev.profile.listening) {
    applyProfile()
    if (s.profile.listening.mode === 'push-to-talk' && prev.profile.listening.mode === 'hands-free') {
      void stopListening(true)
    }
  }
})
window.addEventListener('lector-mic', (e) => {
  if ((e as CustomEvent).detail === 'off') void stopListening()
})
