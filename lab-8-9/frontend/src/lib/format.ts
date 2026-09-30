export function minutesLabel(minutes: number): string {
  if (minutes < 1) return 'under a minute'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m ? `${h} h ${m} min` : `${h} h`
}

export function speedLabel(speed: number): string {
  return `${speed.toFixed(speed % 0.1 === 0 ? 1 : 2).replace(/0$/, '')}×`
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v))
}

export function round(v: number, step: number): number {
  return Math.round(v / step) * step
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  const days = Math.floor(diff / 86400)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

/** Strip LaTeX delimiters for plain-text contexts (titles, toasts). */
export function plainText(text: string): string {
  return text.replace(/\\\((.*?)\\\)/g, '$1').replace(/\$([^$]+)\$/g, '$1')
}
