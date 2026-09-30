/** ROMIP's five-point relevance scale, as the interface presents it. */
export const GRADE_META: Record<string, { label: string; short: string; level: 0 | 1 | 2 | 3 | null }> = {
  VITAL: { label: "vital (соответствующий)", short: "3 · vital", level: 3 },
  RELEVANT_PLUS: { label: "relevant+ (скорее соответствующий)", short: "2 · relevant+", level: 2 },
  RELEVANT_MINUS: { label: "relevant− (возможно соответствующий)", short: "1 · relevant−", level: 1 },
  NOTRELEVANT: { label: "not relevant (не соответствующий)", short: "0 · not relevant", level: 0 },
  CANTBEJUDGED: { label: "cannot be judged", short: "? · unjudgeable", level: null },
};

export const GRADE_ORDER = ["VITAL", "RELEVANT_PLUS", "RELEVANT_MINUS", "NOTRELEVANT", "CANTBEJUDGED"] as const;
