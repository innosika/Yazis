import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/ui/EmptyState";
import { t } from "@/lib/i18n";

export function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <EmptyState
        title={t("There is nothing at this address")}
        description={t("The page you followed does not exist in this system.")}
        action={
          <Link to="/search" search={{}} className="text-accent hover:underline">
            {t("Go to Search")}
          </Link>
        }
      />
    </main>
  );
}
