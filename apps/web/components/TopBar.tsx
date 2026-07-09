"use client";

import { useStore } from "@/lib/store";
import styles from "./TopBar.module.css";

export function TopBar() {
  const { config, hasResult } = useStore();

  const breadcrumb = hasResult
    ? "02 AFTER GENERATE → 3D PREVIEW · EXPORT"
    : "01 CONFIGURE → MAP SELECT · ALL CONTROLS";

  return (
    <div className={styles.wrap}>
      <div className={styles.breadcrumb}>{breadcrumb}</div>
      <div className={styles.header}>
        <div className={styles.brand}>
          <div className={styles.logo} aria-hidden />
          <span className={styles.title}>TOPOPUZZLE STUDIO</span>
        </div>
        <div className={styles.right}>
          <span className={styles.place}>{config.place || "—"}</span>
          <span className={styles.dot} aria-hidden>
            ·
          </span>
          {hasResult ? (
            <span className={styles.statusDone}>
              <span className={styles.greenDot} aria-hidden /> Generation complete
            </span>
          ) : (
            <span className={styles.status}>unsaved</span>
          )}
          <button type="button" className={styles.presets}>
            Presets
          </button>
        </div>
      </div>
    </div>
  );
}
