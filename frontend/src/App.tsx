/**
 * The application shell: header, backend status, and wherever the router is.
 *
 * It holds no document state. Everything about a document is loaded by the
 * route that owns its id, which is what keeps two documents from ever being
 * able to share anything.
 */

import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { getHealth } from "./api/meta";
import { isAbort } from "./api/client";
import type { HealthResponse } from "./types/api";
import styles from "./App.module.css";

type Connectivity =
  | { kind: "checking" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error" };

export default function App() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand}>
            <h1>BalanceSheet</h1>
            <p className={styles.tagline}>
              A Multi-Agent AI Framework for Automated Balance Sheet Review
            </p>
          </Link>
          <BackendStatus />
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        Balance Sheet only, single reporting period. Figures are computed in
        deterministic Python; the language model explains them and never
        calculates.
      </footer>
    </div>
  );
}

/**
 * Reports whether the API and its database are reachable.
 *
 * Quiet while healthy: an indicator that shouts when nothing is wrong trains
 * people to ignore it when something is.
 */
function BackendStatus() {
  const [connectivity, setConnectivity] = useState<Connectivity>({
    kind: "checking",
  });

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((health) => setConnectivity({ kind: "ok", health }))
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        setConnectivity({ kind: "error" });
      });

    return () => controller.abort();
  }, []);

  if (connectivity.kind === "checking") {
    return (
      <p className={styles.status}>
        <span className={styles.dot} data-state="checking" />
        Checking backend…
      </p>
    );
  }

  if (connectivity.kind === "error") {
    return (
      <p className={styles.status}>
        <span className={styles.dot} data-state="down" />
        Backend unreachable — start it on port 8000
      </p>
    );
  }

  const dbConnected = connectivity.health.database === "connected";
  return (
    <p className={styles.status}>
      <span className={styles.dot} data-state={dbConnected ? "ok" : "degraded"} />
      {dbConnected ? "Backend connected" : "Backend up, database unavailable"}
    </p>
  );
}
