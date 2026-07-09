"use client";

import { useStore } from "@/lib/store";
import { downloadUrl } from "@/lib/api";
import { SectionLabel } from "./ui/SectionLabel";
import styles from "./ExportPanel.module.css";

const LAYOUT_LABEL: Record<string, string> = {
  none: "solid",
  "2x2": "2×2",
  "3x3": "3×3",
  "4x4": "4×4",
  custom: "custom",
};

/** Piece label range, e.g. A1–C3 (rows = letters, cols = numbers). */
function pieceLabelRange(rows: number, cols: number): string {
  if (rows <= 1 && cols <= 1) return "solid";
  const lastRow = String.fromCharCode(64 + rows);
  return `A1–${lastRow}${cols}`;
}

export function ExportPanel() {
  const { config, setConfig, job, jobId, reset } = useStore();

  const pieceCount = job?.piece_count ?? config.rows * config.cols;
  const footprint = job?.footprint_mm;
  const w = footprint ? Math.round(footprint[0]) : config.sizeMm;
  const h = footprint
    ? Math.round(footprint[1])
    : Math.round(config.sizeMm * config.aspect);

  const assemblyLabel =
    config.assembly === "separate-pieces" ? "separate" : "in-place";
  const labelRange = pieceLabelRange(config.rows, config.cols);

  const zipFiles = [
    `${pieceCount} × piece STL (${labelRange})`,
    "color-changes.txt",
    "validation-report.json",
    "attribution.txt",
    "settings.json",
    "print-notes.md",
    "coupon.stl",
    "README.md",
  ];

  const checks = job?.report?.checks ?? [];

  const setFormat = (key: "combinedStl" | "obj" | "threeMf", value: boolean) => {
    setConfig({ formats: { ...config.formats, [key]: value } });
  };

  const onDownload = () => {
    if (!jobId) return;
    window.open(downloadUrl(jobId), "_blank");
  };

  return (
    <div className={styles.panel}>
      <div className={styles.scroll}>
        {/* Summary box */}
        <section className={styles.section}>
          <div className={styles.summary}>
            <div className={styles.summaryLine}>
              {config.place || "—"} · {config.lat.toFixed(2)},{" "}
              {config.lon.toFixed(2)}
            </div>
            <div className={styles.summaryLine}>
              {w} × {h} mm · {LAYOUT_LABEL[config.layout]} · {assemblyLabel}
            </div>
            <div className={styles.summaryLine}>
              z {config.zExaggeration.toFixed(1)}× · base{" "}
              {config.baseMm.toFixed(1)} · gap {config.gapMm.toFixed(2)}
            </div>
          </div>
        </section>

        {/* Export formats */}
        <section className={styles.section}>
          <SectionLabel label="Export Formats" chip="—output" />
          <div className={styles.checks}>
            <label className={`${styles.check} ${styles.checkDisabled}`}>
              <input type="checkbox" checked disabled readOnly />
              <span>STL per piece (ZIP)</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={config.formats.combinedStl}
                onChange={(e) => setFormat("combinedStl", e.target.checked)}
              />
              <span>Combined STL</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={config.formats.obj}
                onChange={(e) => setFormat("obj", e.target.checked)}
              />
              <span>OBJ</span>
            </label>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={config.formats.threeMf}
                onChange={(e) => setFormat("threeMf", e.target.checked)}
              />
              <span>3MF (stretch)</span>
            </label>
          </div>
        </section>

        {/* ZIP contents */}
        <section className={styles.section}>
          <SectionLabel label="ZIP Contents" />
          <ul className={styles.fileList}>
            {zipFiles.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>

        {/* Checks */}
        <section className={styles.section}>
          <SectionLabel label="Checks" />
          <div className={styles.checkList}>
            {checks.length === 0 && (
              <div className={styles.checkOk}>
                ✓ no validation checks reported
              </div>
            )}
            {checks.map((c, i) => {
              const failing = !c.ok && c.level === "error";
              const warning = !c.ok && c.level === "warning";
              return (
                <div
                  key={`${c.name}-${i}`}
                  className={
                    failing
                      ? styles.checkFail
                      : warning
                      ? styles.checkWarn
                      : styles.checkOk
                  }
                >
                  {c.ok ? "✓" : "⚠"} {c.message}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <div className={styles.footer}>
        <button type="button" className={styles.back} onClick={() => reset()}>
          ← Back to configure
        </button>
        <button type="button" className={styles.download} onClick={onDownload}>
          DOWNLOAD ZIP ↓
        </button>
      </div>
    </div>
  );
}
