import katex from "katex";
import { useMemo } from "react";
import { cx } from "@/lib/format";

interface Props {
  tex: string;
  display?: boolean;
  className?: string;
  /** Spoken description for screen readers; defaults to the TeX source. */
  label?: string;
}

/** KaTeX-typeset formula. The TeX comes from our own constants or our own backend. */
export function Formula({ tex, display = false, className, label }: Props) {
  const html = useMemo(
    () =>
      katex.renderToString(tex, {
        throwOnError: false,
        displayMode: display,
        output: "html",
        trust: false,
        strict: "ignore",
      }),
    [tex, display],
  );
  return (
    <span
      role="math"
      aria-label={label ?? tex}
      className={cx(display ? "block overflow-x-auto py-1" : "inline-block", className)}
      // KaTeX output is generated from constants we control.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
