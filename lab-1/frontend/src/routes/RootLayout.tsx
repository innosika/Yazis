import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import { cx } from "@/lib/format";
import { StatusPill } from "@/components/ui/StatusPill";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LangToggle } from "@/components/ui/LangToggle";
import { useLang } from "@/lib/i18n";
import { AnimatedOutlet } from "./AnimatedOutlet";

const NAV = [
  { to: "/search", label: "Search" },
  { to: "/corpus", label: "Corpus" },
  { to: "/crawl", label: "Crawl" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/lab", label: "Relevance Lab" },
  { to: "/help", label: "Help" },
] as const;

export function RootLayout() {
  const { lang, t } = useLang();
  const health = useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 15_000 });
  const postgres = health.data?.dependencies.find((d) => d.name === "postgres");
  const redis = health.data?.dependencies.find((d) => d.name === "redis");

  return (
    <div className="flex min-h-screen flex-col bg-ground text-text">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-pill focus:bg-accent focus:px-4 focus:py-2 focus:text-on-accent"
      >
        {t("Skip to content")}
      </a>
      <header className="material-bar hairline-b sticky top-0 z-50">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link
            to="/search"
            search={{}}
            className="shrink-0 font-semibold tracking-tight text-text"
            aria-label={t("Information Retrieval System, home")}
          >
            IRS<span className="ml-1.5 hidden text-text-tertiary font-normal sm:inline">· {t("variant 34")}</span>
          </Link>
          <nav aria-label={t("Primary")} className="-mx-1 min-w-0 flex-1 overflow-x-auto">
            <ul className="flex items-center gap-1 whitespace-nowrap px-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    search={{}}
                    className={cx(
                      "inline-flex rounded-pill px-3 py-1.5 text-[15px] text-text-secondary transition-colors",
                      "hover:bg-surface-sunken hover:text-text",
                    )}
                    activeProps={{
                      className: "bg-accent-soft !text-accent font-medium",
                      "aria-current": "page",
                    }}
                    activeOptions={{ exact: false }}
                  >
                    {t(item.label)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="hidden shrink-0 items-center gap-2 md:flex" aria-label={t("Service status")}>
            <StatusPill
              ok={health.isError ? false : health.data ? health.data.status === "ok" : undefined}
              label="API"
              detail={health.data ? `v${health.data.version} · ${health.data.environment}` : null}
            />
            <StatusPill ok={postgres?.ok} label="Postgres" detail={postgres?.detail ?? null} />
            <StatusPill ok={redis?.ok} label="Redis" detail={redis?.detail ?? null} />
          </div>
          <LangToggle />
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="flex-1">
        <AnimatedOutlet key={lang} />
      </main>
      <footer className="hairline-t mt-16 py-6 text-center text-caption text-text-tertiary">
        {t("Information retrieval system · vector model · English web corpus · lab 1, variant 34")}
      </footer>
    </div>
  );
}
