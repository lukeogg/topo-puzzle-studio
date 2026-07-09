"use client";

import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { Toggle } from "./ui/Toggle";
import { groundMetersPerMm } from "@/lib/geo";
import styles from "./MainPanel.module.css";

const MapSelect = dynamic(() => import("./MapSelect"), {
  ssr: false,
  loading: () => <div className={styles.loading}>loading map…</div>,
});
const Preview3D = dynamic(() => import("./Preview3D"), {
  ssr: false,
  loading: () => <div className={styles.loading}>loading 3D…</div>,
});

export function MainPanel() {
  const { tab, setTab, explode, setExplode, config } = useStore();
  const ground = Math.round(groundMetersPerMm(config.bounds, config.sizeMm));

  return (
    <div className={styles.panel}>
      <div className={styles.tabbar}>
        <div className={styles.tabs}>
          <button
            type="button"
            className={`${styles.tab} ${tab === "map" ? styles.tabActive : ""}`}
            onClick={() => setTab("map")}
          >
            Map
          </button>
          <button
            type="button"
            className={`${styles.tab} ${tab === "3d" ? styles.tabActive : ""}`}
            onClick={() => setTab("3d")}
          >
            3D
          </button>
        </div>
        <div className={styles.tabRight}>
          {tab === "map" ? (
            <span className={styles.ground}>ground: {ground} m / mm</span>
          ) : (
            <span className={styles.explode}>
              <span className={styles.explodeLbl}>Explode</span>
              <Toggle checked={explode} onChange={setExplode} label="Explode" />
            </span>
          )}
        </div>
      </div>

      <div className={styles.stage}>
        {tab === "map" ? <MapSelect /> : <Preview3D />}
      </div>
    </div>
  );
}
