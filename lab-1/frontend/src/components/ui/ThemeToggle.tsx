import { useTheme, type ThemePreference } from "@/lib/theme";
import { t } from "@/lib/i18n";
import { SegmentedControl } from "./SegmentedControl";

const OPTIONS = [
  { value: "light", label: <span aria-label="Light">☀︎</span>, hint: "Light" },
  { value: "system", label: <span aria-label="System">◐</span>, hint: "Follow the system" },
  { value: "dark", label: <span aria-label="Dark">☾</span>, hint: "Dark" },
] as const satisfies ReadonlyArray<{ value: ThemePreference; label: unknown; hint: string }>;

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();
  return (
    <SegmentedControl
      ariaLabel={t("Colour theme")}
      size="sm"
      options={OPTIONS.map((o) => ({ ...o, hint: t(o.hint) }))}
      value={preference}
      onChange={setPreference}
    />
  );
}
