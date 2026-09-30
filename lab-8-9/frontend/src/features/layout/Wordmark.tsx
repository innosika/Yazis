/** The wordmark: the name set in the reading face, with the highlighter under "Lec". */
export function Wordmark() {
  return (
    <span className="relative inline-flex items-baseline font-serif text-[19px] font-semibold tracking-[-0.01em] text-ink">
      <span className="relative">
        <span aria-hidden className="absolute inset-x-[-2px] bottom-[3px] h-[9px] rounded-[2px] bg-marker" />
        <span className="relative">Lec</span>
      </span>
      <span>tor</span>
    </span>
  )
}
