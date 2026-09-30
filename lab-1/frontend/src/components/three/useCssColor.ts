import { useMemo } from "react";
import * as THREE from "three";
import { resolveCssVar } from "@/components/charts/rankerColor";
import { useTheme } from "@/lib/theme";

/** CSS-variable colours resolved to Three.js colours; re-resolved when the theme flips. */
export function useSceneColors() {
  const { resolved } = useTheme();
  return useMemo(() => {
    void resolved; // dependency: the same variable names resolve differently per theme
    const c = (name: string, fallback: string) => new THREE.Color(resolveCssVar(name, fallback));
    return {
      ramp: [c("--relevance-0", "#c7c7cc"), c("--relevance-1", "#64d2ff"), c("--relevance-2", "#0071e3"), c("--relevance-3", "#5e5ce6")],
      accent: c("--accent", "#0071e3"),
      negative: c("--negative", "#d70015"),
      positive: c("--positive", "#1d8a4e"),
      hairline: c("--hairline-strong", "#999999"),
      text: c("--text-secondary", "#6e6e73"),
      ground: c("--surface-sunken", "#f5f5f7"),
    };
  }, [resolved]);
}

export type SceneColors = ReturnType<typeof useSceneColors>;

/** Piecewise-linear interpolation through the relevance ramp for a cosine in [0, 1]. */
export function rampColor(ramp: THREE.Color[], value: number, out: THREE.Color): THREE.Color {
  const clamped = Math.max(0, Math.min(1, value));
  // Cosines cluster near 0; a square-root eases the low end so weak matches stay visible.
  const t = Math.sqrt(clamped) * (ramp.length - 1);
  const i = Math.min(ramp.length - 2, Math.floor(t));
  const a = ramp[i];
  const b = ramp[i + 1];
  if (!a || !b) return out.copy(ramp[0] ?? new THREE.Color());
  return out.copy(a).lerp(b, t - i);
}
