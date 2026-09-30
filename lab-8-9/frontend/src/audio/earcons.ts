/** Tiny synthesized cues so the ear knows what the microphone is doing. */

let ctx: AudioContext | null = null

function context(): AudioContext {
  ctx ??= new AudioContext()
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

function tone(freq: number, start: number, dur: number, gain = 0.06, type: OscillatorType = 'sine'): void {
  const c = context()
  const osc = c.createOscillator()
  const g = c.createGain()
  osc.type = type
  osc.frequency.value = freq
  const t = c.currentTime + start
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(gain, t + 0.012)
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
  osc.connect(g).connect(c.destination)
  osc.start(t)
  osc.stop(t + dur + 0.02)
}

export const earcons = {
  listening: () => {
    tone(660, 0, 0.09)
    tone(880, 0.07, 0.12)
  },
  recognized: () => tone(988, 0, 0.14, 0.05),
  notUnderstood: () => {
    tone(392, 0, 0.1, 0.05, 'triangle')
    tone(330, 0.1, 0.14, 0.05, 'triangle')
  },
  off: () => {
    tone(880, 0, 0.08)
    tone(587, 0.07, 0.12)
  },
}
