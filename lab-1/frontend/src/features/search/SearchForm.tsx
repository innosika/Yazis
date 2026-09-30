import { useEffect, useRef, useState, type FormEvent } from "react";
import type { RankerInfo } from "@/lib/api";
import { rankerColor, rankerLabel, rankerOrder } from "@/components/charts/rankerColor";
import { Button } from "@/components/ui/Button";
import { HelpTip } from "@/components/ui/HelpTip";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Toggle } from "@/components/ui/Toggle";
import type { SearchSearch } from "@/routes/searchParams";
import { t } from "@/lib/i18n";

interface Props {
  value: SearchSearch;
  rankers: RankerInfo[];
  onSubmit: (next: SearchSearch) => void;
  busy?: boolean;
}

export function SearchForm({ value, rankers, onSubmit, busy }: Props) {
  const [draft, setDraft] = useState(value.q);
  const [from, setFrom] = useState(value.from ?? "");
  const [to, setTo] = useState(value.to ?? "");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => setDraft(value.q), [value.q]);

  // "/" focuses the search field from anywhere on the page.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      event.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({
      ...value,
      q: draft.trim(),
      ...(from ? { from } : { from: undefined }),
      ...(to ? { to } : { to: undefined }),
    });
  };

  const options = [...rankers].sort((a, b) => rankerOrder(a.key, b.key)).map((r) => ({
    value: r.key,
    label: r.is_required_model ? `${rankerLabel(r.key)} ★` : rankerLabel(r.key),
    disabled: !r.available,
    hint: r.available ? r.description : (r.unavailable_reason ?? "unavailable"),
    color: rankerColor(r.key),
  }));

  return (
    <form role="search" onSubmit={submit} className="space-y-4">
      <div className="flex items-center gap-2 rounded-pill border border-hairline-strong bg-surface px-2 py-1.5 shadow-sm focus-within:border-accent">
        <span aria-hidden className="pl-3 text-text-tertiary">⌕</span>
        <input
          ref={input}
          type="search"
          name="q"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("Ask in plain English, e.g. how does an inverted index store term positions")}
          aria-label={t("Search query")}
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent px-1 py-2 text-[17px] text-text placeholder:text-text-tertiary focus:outline-none"
        />
        <Button type="submit" variant="primary" loading={busy ?? false}>
          {t("Search")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-caption text-text-tertiary">{t("Ranker")}</span>
          <SegmentedControl
            ariaLabel={t("Document-selection strategy")}
            size="sm"
            options={options}
            value={value.ranker}
            onChange={(ranker) => onSubmit({ ...value, q: draft.trim(), ranker })}
          />
          <HelpTip anchor="help-search">
            {t("The strategy used to select and order documents. The starred vector model is the one the assignment mandates; the others are baselines and improvement proposals it is measured against.")}
          </HelpTip>
        </div>
        <Toggle
          label={t("All words together")}
          description={t("Only documents containing every query word (allWordsTogether)")}
          checked={value.all}
          onChange={(all) => onSubmit({ ...value, q: draft.trim(), all })}
        />
        <div className="flex flex-wrap items-center gap-2 text-caption text-text-tertiary">
          <label className="flex items-center gap-1">
            {t("from")}
            <input
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              onBlur={submit}
              aria-label={t("Published from")}
              className="rounded-pill border border-hairline bg-surface px-2 py-1 text-caption text-text"
            />
          </label>
          <label className="flex items-center gap-1">
            {t("to")}
            <input
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
              onBlur={submit}
              aria-label={t("Published until")}
              className="rounded-pill border border-hairline bg-surface px-2 py-1 text-caption text-text"
            />
          </label>
        </div>
      </div>
    </form>
  );
}
