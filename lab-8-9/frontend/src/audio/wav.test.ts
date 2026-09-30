import { describe, expect, it } from 'vitest'

import { encodeWav } from './wav'

describe('encodeWav', () => {
  it('writes a valid 16-bit mono header and clamps samples', async () => {
    const blob = encodeWav(new Float32Array([0, 1, -1, 2]), 16000)
    const view = new DataView(await blob.arrayBuffer())
    const tag = (o: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => view.getUint8(o + i)))
    expect(tag(0)).toBe('RIFF')
    expect(tag(8)).toBe('WAVE')
    expect(view.getUint16(22, true)).toBe(1)
    expect(view.getUint32(24, true)).toBe(16000)
    expect(view.getUint32(40, true)).toBe(8)
    expect(view.getInt16(46, true)).toBe(0x7fff)
    expect(view.getInt16(48, true)).toBe(-0x8000)
    expect(view.getInt16(50, true)).toBe(0x7fff) // 2 is clamped to 1
  })
})
