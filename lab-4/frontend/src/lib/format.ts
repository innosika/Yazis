/** Small shared formatters. */

export const percent = (value: number, digits = 0): string =>
  `${(value * 100).toFixed(digits)}%`

export const thousands = (value: number): string => value.toLocaleString('en-US')

export const milliseconds = (value: number): string =>
  value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`

export const dateTime = (iso: string): string => {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.valueOf())
    ? '—'
    : date.toLocaleString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
}

export const DOMAIN_TITLES: Record<string, string> = {
  general: 'General',
  cs: 'Computer Science',
  lit: 'Literature',
}

/** Coverage colour: three bands, with text alongside so colour is never the only signal. */
export function coverageTone(coverage: number): 'success' | 'warning' | 'danger' {
  if (coverage >= 0.9) return 'success'
  if (coverage >= 0.7) return 'warning'
  return 'danger'
}

export function classes(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(' ')
}
