"use client";

import React, {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Bounds, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { useStore } from "@/lib/store";
import { previewGlbUrl } from "@/lib/api";
import styles from "./Preview3D.module.css";

function pieceLabelRange(rows: number, cols: number): string {
  if (rows <= 1 && cols <= 1) return "solid";
  const lastRow = String.fromCharCode(64 + rows);
  return `A1–${lastRow}${cols}`;
}

function Model({
  url,
  explode,
  onStats,
}: {
  url: string;
  explode: boolean;
  onStats: (tris: number) => void;
}) {
  const { scene } = useGLTF(url);
  const cloned = useMemo(() => scene.clone(true), [scene]);

  const pieces = useMemo(() => {
    const box = new THREE.Box3().setFromObject(cloned);
    const center = box.getCenter(new THREE.Vector3());
    return cloned.children.map((child) => {
      const cbox = new THREE.Box3().setFromObject(child);
      const cc = cbox.getCenter(new THREE.Vector3());
      const dir = cc.clone().sub(center);
      dir.y = 0;
      return { child, base: child.position.clone(), dir };
    });
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
    onStats(Math.round(tris));
  }, [cloned, onStats]);

  useEffect(() => {
    const amount = explode ? 0.4 : 0;
    pieces.forEach(({ child, base, dir }) => {
      child.position.set(base.x + dir.x * amount, base.y, base.z + dir.z * amount);
    });
  }, [explode, pieces]);

  return <primitive object={cloned} />;
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
  const [tris, setTris] = useState<number | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const showModel = hasResult && jobId && !loadFailed;
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
        camera={{ position: [4, 3.5, 5], fov: 40 }}
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
        {/* Ground plane */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, -0.6, 0]}
          receiveShadow
        >
          <planeGeometry args={[60, 60]} />
          <meshStandardMaterial color="#e4dac4" />
        </mesh>

        {showModel && url && (
          <Suspense fallback={null}>
            <GlbErrorBoundary onError={() => setLoadFailed(true)}>
              <Bounds fit clip observe margin={1.2}>
                <Model url={url} explode={explode} onStats={setTris} />
              </Bounds>
            </GlbErrorBoundary>
          </Suspense>
        )}

        <OrbitControls
          enablePan
          enableDamping
          minDistance={2}
          maxDistance={40}
        />
      </Canvas>

      {/* Orbit hint */}
      {showModel && (
        <div className={styles.orbitHint}>drag to orbit · scroll to zoom</div>
      )}

      {/* Pre-result / loading overlay */}
      {!showModel && (
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
