import { useEffect, useState } from "react";
import { getHealth, getPipelineStatus } from "./api/client";
import type { HealthResponse, PipelineStageInfo } from "./types/balanceSheet";

type Connectivity =
  | { kind: "checking" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error"; message: string };

export default function App() {
  const [connectivity, setConnectivity] = useState<Connectivity>({ kind: "checking" });
  const [stages, setStages] = useState<PipelineStageInfo[]>([]);

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((health) => {
        if (!cancelled) setConnectivity({ kind: "ok", health });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setConnectivity({
            kind: "error",
            message: error instanceof Error ? error.message : "Unknown error",
          });
        }
      });

    getPipelineStatus()
      .then((status) => {
        if (!cancelled) setStages(status.stages);
      })
      .catch(() => {
        /* The health indicator already reports backend trouble. */
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <header>
        <h1>BalanceSheet</h1>
        <p className="tagline">
          A Multi-Agent AI Framework for Automated Balance Sheet Review
        </p>
      </header>

      <section className="card">
        <h2>Backend</h2>
        <ConnectivityIndicator connectivity={connectivity} />
      </section>

      <section className="card">
        <h2>Modules</h2>
        {stages.length === 0 ? (
          <p className="muted">Not available.</p>
        ) : (
          <ul className="stages">
            {stages.map((stage) => (
              <li key={stage.stage}>
                <span className={`badge badge--${stage.state}`}>
                  {stage.state === "partial" ? "partial" : "not built"}
                </span>
                <span className="stage-name">
                  Module {stage.module} — {stage.stage}
                </span>
                <span className="muted">{stage.description}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Upload</h2>
        <div className="dropzone" aria-disabled="true">
          <p>Drop a Balance Sheet (PDF or Excel)</p>
          <p className="muted">
            Uploading is not wired up in the UI yet. Parsing, OCR and extraction
            are not implemented — see Module 1.
          </p>
        </div>
      </section>

      <footer className="muted">
        Scope: Balance Sheet only, single reporting period.
      </footer>
    </main>
  );
}

function ConnectivityIndicator({ connectivity }: { connectivity: Connectivity }) {
  if (connectivity.kind === "checking") {
    return <p className="status status--checking">Checking…</p>;
  }

  if (connectivity.kind === "error") {
    return (
      <>
        <p className="status status--down">Unreachable</p>
        <p className="muted">
          {connectivity.message}. Is the backend running on port 8000?
        </p>
      </>
    );
  }

  const dbConnected = connectivity.health.database === "connected";
  return (
    <>
      <p className="status status--up">Connected</p>
      <p className={dbConnected ? "muted" : "status status--down"}>
        MongoDB: {connectivity.health.database}
      </p>
    </>
  );
}
