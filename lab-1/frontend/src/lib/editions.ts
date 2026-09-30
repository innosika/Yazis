/** Which ROMIP document defines a metric, as the interface phrases it. */
import { t } from "@/lib/i18n";
const EDITION_LABEL: Record<string, string> = {
  official_2004: "ROMIP 2004 — official",
  extension: "ROMIP 2009/2010 extension",
  reconstruction: "reconstruction of an undefined metric",
  diagnostic: "diagnostic counter",
};

export function editionLabel(edition: string): string {
  return t(EDITION_LABEL[edition] ?? edition);
}

