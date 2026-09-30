import type { MetricSpec } from "@/lib/api";
import { Formula } from "@/components/math/Formula";
import { HelpTip } from "@/components/ui/HelpTip";
import { editionLabel } from "@/lib/editions";
import { t } from "@/lib/i18n";
import { metricDescription, metricLabel } from "@/lib/metricsRu";

/** Column header with the metric's Russian name, description and formula in a tooltip. */
export function MetricHeader({ spec }: { spec: MetricSpec }) {
  return (
    <span className="inline-flex items-center gap-1">
      {metricLabel(spec)}
      <HelpTip anchor={`metric-${spec.key}`} label={t("About {metric}", { metric: spec.label })}>
        <strong className="block">{spec.label}</strong>
        {spec.label_ru && <span className="block text-text-secondary">{spec.label_ru}</span>}
        <span className="block text-text-tertiary">{editionLabel(spec.edition)}</span>
        <span className="mt-1 block">{metricDescription(spec)}</span>
        {spec.formula_tex && <Formula tex={spec.formula_tex} display className="mt-1" />}
      </HelpTip>
    </span>
  );
}
