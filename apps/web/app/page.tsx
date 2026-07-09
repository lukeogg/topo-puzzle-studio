"use client";

import { StoreProvider, useStore } from "@/lib/store";
import { TopBar } from "@/components/TopBar";
import { ControlPanel } from "@/components/ControlPanel";
import { ExportPanel } from "@/components/ExportPanel";
import { MainPanel } from "@/components/MainPanel";
import styles from "./page.module.css";

function Studio() {
  const { hasResult } = useStore();
  return (
    <div className={styles.app}>
      <TopBar />
      <div className={styles.body}>
        <aside className={styles.left}>
          {hasResult ? <ExportPanel /> : <ControlPanel />}
        </aside>
        <main className={styles.main}>
          <MainPanel />
        </main>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <StoreProvider>
      <Studio />
    </StoreProvider>
  );
}
