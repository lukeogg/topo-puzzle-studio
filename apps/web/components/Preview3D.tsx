"use client";

import React, {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { useStore } from "@/lib/store";
import { previewGlbUrl } from "@/lib/api";
import styles from "./Preview3D.module.css";

// The model arrives in true millimetres, so its raw size varies with the plate
// the user picked. Rescale every model to the same footprint on load; that is
// what lets one fixed camera and one fixed zoom range frame any result.
const TARGET_SPAN = 4;
const GROUND_Y = -0.02;

function pieceLabelRange(rows: number, cols: number): string {
  if (rows <= 1 && cols <= 1) return "solid";
  const lastRow = String.fromCharCode(64 + rows);
  return `A1–${lastRow}${cols}`;
}

/**
 * The GLB nests every piece under a single trimesh "world" node, so the
 * scene root has exactly one child. Descend past the wrappers to the node
 * whose children are the pieces themselves.
 */
function pieceNodes(root: THREE.Object3D): THREE.Object3D[] {
  let node = root;
  while (!(node as THREE.Mesh).isMesh && node.children.length === 1) {
    node = node.children[0];
  }
  return node.children.length > 0 ? node.children : [node];
}

function Model({
  url,
  explode,
  onFramed,
}: {
  url: string;
  explode: boolean;
  onFramed: (framed: { tris: number; height: number }) => void;
}) {
  const { scene } = useGLTF(url);
  const cloned = useMemo(() => scene.clone(true), [scene]);

  // Measured while `cloned` is still detached, so these are its own local
  // coordinates and stay valid once the framing group is applied around it.
  const { pieces, scale, offset, height } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(cloned);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const scale = TARGET_SPAN / Math.max(size.x, size.z, 1e-6);

    const pieces = pieceNodes(cloned).map((child) => {
      const cc = new THREE.Box3().setFromObject(child).getCenter(new THREE.Vector3());
      const dir = cc.clone().sub(center);
      dir.y = 0; // pieces slide apart in the ground plane, never upward
      return { child, base: child.position.clone(), dir };
    });

    return {
      pieces,
      scale,
      // Centre horizontally and rest the underside on the ground plane.
      offset: new THREE.Vector3(-center.x, -box.min.y, -center.z),
      height: size.y * scale,
    };
  }, [cloned]);

  useEffect(() => {
    let tris = 0;
    cloned.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh && mesh.geometry) {
        const g = mesh.geometry as THREE.BufferGeometry;
        if (g.index) tris += g.index.count / 3;
        else if (g.attributes.position) tris += g.attributes.position.count / 3;
      }
    });
    onFramed({ tris: Math.round(tris), height });
  }, [cloned, height, onFramed]);

  useEffect(() => {
    const amount = explode ? 0.4 : 0;
    pieces.forEach(({ child, base, dir }) => {
      child.position.set(base.x + dir.x * amount, base.y, base.z + dir.z * amount);
    });
  }, [explode, pieces]);

  return (
    <group scale={scale}>
      <group position={offset}>
        <primitive object={cloned} />
      </group>
    </group>
  );
}

class GlbErrorBoundary extends React.Component<
  { onError: () => void; children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}

export default function Preview3D() {
  const { hasResult, jobId, job, config, explode } = useStore();
  const [framed, setFramed] = useState<{ tris: number; height: number } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const tris = framed?.tris ?? null;

  // The backend reports whether a preview mesh exists; a blocked/failed job
  // finishes without one, so we skip the GLB load and show a placeholder.
  const hasPreview = job?.has_preview ?? true;
  const showModel = hasResult && jobId && !loadFailed && hasPreview;
  const noPreview = hasResult && !hasPreview;
  const url = jobId ? previewGlbUrl(jobId) : "";
  const pieceCount = job?.piece_count ?? config.rows * config.cols;
  const labelRange = pieceLabelRange(config.rows, config.cols);

  const trisLabel =
    tris != null
      ? tris >= 1000
        ? `${(tris / 1000).toFixed(0)} k tris`
        : `${tris} tris`
      : "— tris";

  return (
    <div className={styles.wrap}>
      <Canvas
        shadows
        camera={{ position: [3, 4, 6], fov: 40 }}
        dpr={[1, 2]}
      >
        <color attach="background" args={["#efe7d6"]} />
        <ambientLight intensity={0.75} />
        <hemisphereLight args={["#fff7e8", "#cdbfa6", 0.5]} />
        <directionalLight
          position={[6, 10, 4]}
          intensity={1.1}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
        {/* Ground plane — a hair below the model so the two never z-fight. */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, GROUND_Y, 0]}
          receiveShadow
        >
          <planeGeometry args={[60, 60]} />
          <meshStandardMaterial color="#e4dac4" />
        </mesh>

        {showModel && url && (
          <Suspense fallback={null}>
            <GlbErrorBoundary onError={() => setLoadFailed(true)}>
              <Model url={url} explode={explode} onFramed={setFramed} />
            </GlbErrorBoundary>
          </Suspense>
        )}

        <OrbitControls
          makeDefault
          enablePan
          enableDamping
          target={[0, (framed?.height ?? 0) / 2, 0]}
          minDistance={1.5}
          maxDistance={30}
        />
      </Canvas>

      {/* Orbit hint */}
      {showModel && (
        <div className={styles.orbitHint}>drag to orbit · scroll to zoom</div>
      )}

      {/* No-preview placeholder (job finished but produced no preview mesh) */}
      {noPreview && (
        <div className={styles.pipeline}>
          No 3D preview available
          <br />
          for this result.
          <br />
          Check the validation report
          <br />
          in the export panel.
        </div>
      )}

      {/* Pre-result / loading overlay */}
      {!showModel && !noPreview && (
        <div className={styles.pipeline}>
          Progress pipeline (fetch
          <br />→ raster → terrain →
          <br />
          split → validate →
          <br />
          package) runs here
          <br />
          during generation ▶
          {loadFailed && (
            <div className={styles.loadFail}>
              (preview.glb unavailable — start the backend to load it)
            </div>
          )}
        </div>
      )}

      {/* Bottom-left readout */}
      {showModel && (
        <div className={styles.readout}>
          {pieceCount} pieces · {trisLabel}
          <br />✓ watertight · labels {labelRange}
        </div>
      )}
    </div>
  );
}
