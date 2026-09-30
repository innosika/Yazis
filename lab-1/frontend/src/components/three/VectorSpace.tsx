/**
 * The term space made visible: every document as a point in the 3-D latent space of the
 * term–document matrix, the query as a ray from the origin. Documents are coloured by
 * their *full-space* cosine with the query; hovering one shows the angle in this picture
 * (θ₃) beside the real cosine, because the projection keeps only part of the geometry.
 */
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { rampColor, useSceneColors, type SceneColors } from "./useCssColor";
import { t } from "@/lib/i18n";

export interface ScenePoint {
  id: number;
  title: string;
  position: [number, number, number];
  /** Full-space cosine with the current query, 0 when no term matches. */
  cosine: number;
}

export type Mark = "rel" | "nonrel";

interface Props {
  points: ScenePoint[];
  /** Normalised query direction; the ray animates towards it. */
  query: [number, number, number] | null;
  /** Previous query positions (Rocchio trajectory), oldest first. */
  trail: Array<[number, number, number]>;
  hovered: number | null;
  onHover: (id: number | null) => void;
  marks: Record<number, Mark>;
  onSelect?: (id: number) => void;
}

const ORIGIN = new THREE.Vector3(0, 0, 0);

export function VectorSpace({ points, query, trail, hovered, onHover, marks, onSelect }: Props) {
  const reduced = useReducedMotion();
  const colors = useSceneColors();
  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [2.4, 1.8, 2.4], fov: 42 }}
      frameloop={reduced ? "demand" : "always"}
      gl={{ antialias: true, alpha: true }}
      style={{ background: "transparent" }}
    >
      <ambientLight intensity={1.1} />
      <directionalLight position={[3, 5, 2]} intensity={0.9} />
      <Axes colors={colors} />
      <PointCloud points={points} hovered={hovered} onHover={onHover} marks={marks} colors={colors} onSelect={onSelect} />
      {query && <QueryRay target={query} colors={colors} reduced={Boolean(reduced)} />}
      {trail.map((p, i) => (
        <Line key={i} points={[[0, 0, 0], p]} color={colors.accent} lineWidth={1} transparent opacity={0.25 + (0.4 * i) / Math.max(trail.length, 1)} dashed dashSize={0.03} gapSize={0.02} />
      ))}
      {hovered !== null && query && <AngleArc point={points.find((p) => p.id === hovered)} query={query} colors={colors} />}
      <OrbitControls enablePan={false} enableDamping autoRotate={!reduced} autoRotateSpeed={0.5} minDistance={1.2} maxDistance={6} />
    </Canvas>
  );
}

function Axes({ colors }: { colors: SceneColors }) {
  return (
    <group>
      <Line points={[[-1.2, 0, 0], [1.2, 0, 0]]} color={colors.hairline} lineWidth={1} />
      <Line points={[[0, -1.2, 0], [0, 1.2, 0]]} color={colors.hairline} lineWidth={1} />
      <Line points={[[0, 0, -1.2], [0, 0, 1.2]]} color={colors.hairline} lineWidth={1} />
      <Html position={[1.25, 0, 0]} center style={{ pointerEvents: "none" }}>
        <span className="text-[11px] text-text-tertiary">σ₁</span>
      </Html>
      <Html position={[0, 1.25, 0]} center style={{ pointerEvents: "none" }}>
        <span className="text-[11px] text-text-tertiary">σ₂</span>
      </Html>
      <Html position={[0, 0, 1.25]} center style={{ pointerEvents: "none" }}>
        <span className="text-[11px] text-text-tertiary">σ₃</span>
      </Html>
    </group>
  );
}

function PointCloud({ points, hovered, onHover, marks, colors, onSelect }: { points: ScenePoint[]; hovered: number | null; onHover: (id: number | null) => void; marks: Record<number, Mark>; colors: SceneColors; onSelect?: ((id: number) => void) | undefined }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const scratch = useMemo(() => new THREE.Color(), []);

  useEffect(() => {
    const instanced = mesh.current;
    if (!instanced) return;
    points.forEach((point, index) => {
      const mark = marks[point.id];
      const scale = point.id === hovered ? 2.2 : mark ? 1.8 : 1;
      dummy.position.set(...point.position);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      instanced.setMatrixAt(index, dummy.matrix);
      if (mark === "rel") scratch.copy(colors.positive);
      else if (mark === "nonrel") scratch.copy(colors.negative);
      else rampColor(colors.ramp, point.cosine, scratch);
      instanced.setColorAt(index, scratch);
    });
    instanced.count = points.length;
    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
  }, [points, hovered, marks, colors, dummy, scratch]);

  return (
    <instancedMesh
      ref={mesh}
      args={[undefined, undefined, Math.max(points.length, 1)]}
      onPointerMove={(event) => {
        event.stopPropagation();
        const point = event.instanceId !== undefined ? points[event.instanceId] : undefined;
        onHover(point ? point.id : null);
      }}
      onPointerOut={() => onHover(null)}
      onClick={(event) => {
        event.stopPropagation();
        const point = event.instanceId !== undefined ? points[event.instanceId] : undefined;
        if (point && onSelect) onSelect(point.id);
      }}
    >
      <sphereGeometry args={[0.016, 12, 12]} />
      <meshStandardMaterial roughness={0.35} metalness={0.1} />
    </instancedMesh>
  );
}

function QueryRay({ target, colors, reduced }: { target: [number, number, number]; colors: SceneColors; reduced: boolean }) {
  const current = useRef(new THREE.Vector3(...target));
  const goal = useMemo(() => new THREE.Vector3(...target), [target]);
  const line = useRef<THREE.Line>(null);
  const tip = useRef<THREE.Mesh>(null);
  const positions = useMemo(() => new Float32Array(6), []);

  useFrame((_, delta) => {
    if (reduced) current.current.copy(goal);
    else current.current.lerp(goal, 1 - Math.exp(-delta * 6));
    const v = current.current;
    positions.set([0, 0, 0, v.x, v.y, v.z]);
    const geometry = line.current?.geometry;
    const attribute = geometry?.getAttribute("position");
    if (attribute) attribute.needsUpdate = true;
    if (tip.current) {
      tip.current.position.copy(v);
      tip.current.lookAt(ORIGIN);
    }
  });

  return (
    <group>
      <line ref={line as never}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={colors.accent} linewidth={2} />
      </line>
      <mesh ref={tip}>
        <coneGeometry args={[0.03, 0.09, 12]} />
        <meshStandardMaterial color={colors.accent} />
      </mesh>
      <Html position={goal.toArray()} center distanceFactor={4} style={{ pointerEvents: "none" }}>
        <span className="rounded-pill bg-accent px-2 py-0.5 text-[11px] font-medium text-on-accent">q</span>
      </Html>
    </group>
  );
}

function AngleArc({ point, query, colors }: { point: ScenePoint | undefined; query: [number, number, number]; colors: SceneColors }) {
  if (!point) return null;
  const q = new THREE.Vector3(...query).normalize();
  const d = new THREE.Vector3(...point.position);
  const dn = d.clone().normalize();
  const angle = Math.acos(Math.max(-1, Math.min(1, q.dot(dn))));
  const radius = Math.min(0.5, d.length() * 0.8, new THREE.Vector3(...query).length() * 0.8);
  const steps = 24;
  const arc: Array<[number, number, number]> = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const v = new THREE.Vector3().copy(q).multiplyScalar(Math.sin((1 - t) * angle)).add(dn.clone().multiplyScalar(Math.sin(t * angle)));
    if (angle > 1e-6) v.divideScalar(Math.sin(angle));
    arc.push([v.x * radius, v.y * radius, v.z * radius]);
  }
  const mid = arc[Math.floor(steps / 2)] ?? [0, 0, 0];
  return (
    <group>
      <Line points={[[0, 0, 0], d.toArray()]} color={colors.text} lineWidth={1} dashed dashSize={0.02} gapSize={0.015} />
      <Line points={arc} color={colors.negative} lineWidth={2} />
      <Html position={[mid[0] * 1.35, mid[1] * 1.35, mid[2] * 1.35]} center style={{ pointerEvents: "none" }}>
        <div className="whitespace-nowrap rounded-panel border border-hairline bg-surface-raised px-2 py-1 text-[11px] shadow-md">
          <div className="font-medium text-text">{point.title.replace(/ - Wikipedia$/, "")}</div>
          <div className="text-text-secondary">
            {t("θ₃ = {deg}° in this picture · cos θ = {cos} in the full space", { deg: ((angle * 180) / Math.PI).toFixed(1), cos: point.cosine.toFixed(3) })}
          </div>
        </div>
      </Html>
    </group>
  );
}
