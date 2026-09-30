/** Highlight ranges returned by the search API, normalised for rendering. */
export interface Range {
  start: number;
  end: number;
  lemma: string;
}

/** Merge overlapping/unsorted ranges and clip them to the text. */
export function normaliseRanges(ranges: Range[], length: number): Range[] {
  const clipped = ranges
    .map((r) => ({ ...r, start: Math.max(0, r.start), end: Math.min(length, r.end) }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);
  const merged: Range[] = [];
  for (const range of clipped) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) {
      last.end = Math.max(last.end, range.end);
      if (!last.lemma.includes(range.lemma)) last.lemma = `${last.lemma}, ${range.lemma}`;
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}
