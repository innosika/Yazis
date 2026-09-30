import { useLang } from "@/lib/i18n";
import { SegmentedControl } from "./SegmentedControl";

const OPTIONS = [
  { value: "ru", label: "RU", hint: "Русский" },
  { value: "en", label: "EN", hint: "English" },
] as const;

export function LangToggle() {
  const { lang, setLang } = useLang();
  return <SegmentedControl ariaLabel="Язык интерфейса / Interface language" size="sm" options={OPTIONS} value={lang} onChange={setLang} />;
}
