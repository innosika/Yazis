/**
 * Fade the page in on top-level route changes.
 *
 * Keyed on the first path segment only, so switching evaluation sub-tabs does not fade
 * the whole page. Enter-only: `<Outlet/>` always renders the *current* match, so an exit
 * animation would show the new page inside the leaving wrapper.
 */
import { Outlet, useRouterState } from "@tanstack/react-router";
import { motion, useReducedMotion } from "motion/react";

export function AnimatedOutlet() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const reduced = useReducedMotion();
  const segment = pathname.split("/")[1] ?? "";
  return (
    <motion.div
      key={segment}
      initial={reduced ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
    >
      <Outlet />
    </motion.div>
  );
}
