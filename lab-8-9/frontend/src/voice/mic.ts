/**
 * The microphone: Silero VAD running in the browser (onnxruntime-web, one thread).
 *
 * It only ever hands over finished utterances. Two tuning profiles: `command` ends an
 * utterance after ~0.55 s of silence so short commands feel immediate; `reading` is used
 * while Lector itself is speaking and asks for clearly louder, longer speech before it
 * reacts, because the loudspeaker is in the room too.
 */

import { MicVAD } from '@ricky0123/vad-web'

export interface MicCallbacks {
  onSpeechStart: () => void
  onSpeechEnd: (audio: Float32Array) => void
  onMisfire: () => void
  onLevel: (speechProbability: number) => void
}

export type MicProfile = 'command' | 'reading'

function profileOptions(profile: MicProfile, sensitivity: number) {
  // sensitivity 0..1 -> threshold 0.75..0.35 (higher sensitivity, lower threshold)
  const base = 0.75 - sensitivity * 0.4
  const positive = profile === 'reading' ? Math.max(base, 0.72) : base
  return {
    positiveSpeechThreshold: positive,
    negativeSpeechThreshold: Math.max(0.1, positive - 0.15),
    redemptionMs: profile === 'reading' ? 650 : 550,
    preSpeechPadMs: 300,
    minSpeechMs: profile === 'reading' ? 350 : 250,
  }
}

export class Microphone {
  private vad: MicVAD | null = null
  private starting: Promise<MicVAD> | null = null
  private profile: MicProfile = 'command'
  private sensitivity = 0.5

  constructor(private cb: MicCallbacks) {}

  get active(): boolean {
    return this.vad?.listening ?? false
  }

  private async create(): Promise<MicVAD> {
    return MicVAD.new({
      model: 'v5',
      baseAssetPath: '/vad/',
      onnxWASMBasePath: '/vad/',
      startOnLoad: false,
      submitUserSpeechOnPause: true,
      ortConfig: (ort) => {
        ort.env.wasm.numThreads = 1
        ort.env.logLevel = 'error'
      },
      getStream: () =>
        navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
      resumeStream: () =>
        navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
      ...profileOptions(this.profile, this.sensitivity),
      onSpeechStart: () => this.cb.onSpeechStart(),
      onSpeechEnd: (audio) => this.cb.onSpeechEnd(audio),
      onVADMisfire: () => this.cb.onMisfire(),
      onFrameProcessed: (p) => this.cb.onLevel(p.isSpeech),
    })
  }

  async start(): Promise<void> {
    if (!this.vad) {
      this.starting ??= this.create()
      try {
        this.vad = await this.starting
      } finally {
        this.starting = null
      }
    }
    await this.vad.start()
    if (this.vad.errored) throw new Error(this.vad.errored)
  }

  /** Stop listening; speech in progress is still delivered to onSpeechEnd. */
  async stop(): Promise<void> {
    await this.vad?.pause()
    this.cb.onLevel(0)
  }

  setProfile(profile: MicProfile, sensitivity: number): void {
    if (profile === this.profile && sensitivity === this.sensitivity) return
    this.profile = profile
    this.sensitivity = sensitivity
    this.vad?.setOptions(profileOptions(profile, sensitivity))
  }

  async destroy(): Promise<void> {
    await this.vad?.destroy()
    this.vad = null
  }
}
