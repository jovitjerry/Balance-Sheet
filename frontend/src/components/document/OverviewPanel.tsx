import type { ReactElement } from "react";
import type {
  BalanceSheetDocument,
  EquationCheck,
  IdentificationEvidence,
  PeriodSelection,
  RatioSet,
  ValidationSummary,
} from "../../types/balanceSheet";
import { MoneyValue, RatioValue } from "../common/Figures";
import { StatusPill } from "../common/StatusPill";
import styles from "./OverviewPanel.module.css";

const REJECTION_TITLE: Record<string, string> = {
  unreadable: "Could not be read",
  not_a_balance_sheet: "Not a Balance Sheet",
  missing_required_fields: "A required total is missing",
  equation_unbalanced: "The accounting equation does not balance",
};

export function OverviewPanel({
  document,
}: {
  document: BalanceSheetDocument;
}): ReactElement {
  const check = document.equation_check;
  const ratios = document.ratios;

  return (
    <>
      {document.rejection && (
        <section className={styles.rejection}>
          <h2 className={styles.rejectionTitle}>
            {REJECTION_TITLE[document.rejection.reason] ?? "Rejected"}
          </h2>
          <p>{document.rejection.message}</p>
          <p className="muted">
            The submission was kept rather than discarded, so the verdict and
            the evidence for it stay reviewable.
          </p>
        </section>
      )}

      {document.errors.length > 0 && (
        <section className="card">
          <h2 className="eyebrow">Processing notes</h2>
          <ul className={styles.missing}>
            {document.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </section>
      )}

      {}
      {check && <KpiStrip check={check} ratios={ratios ?? null} />}

      {}
      <div className={styles.overviewLayout}>
        <div className={styles.mainColumn}>
          {check && (
            <EquationPanel
              check={check}
              validation={document.validation ?? null}
            />
          )}
          {check && <StructureBar check={check} />}
        </div>

        <div className={styles.sideColumn}>
          {document.identification && (
            <IdentificationPanel evidence={document.identification} />
          )}
          {document.period && <PeriodPanel period={document.period} />}
        </div>
      </div>
    </>
  );
}

function KpiStrip({
  check,
  ratios,
}: {
  check: EquationCheck;
  ratios: RatioSet | null;
}) {
  const byName = new Map(ratios?.ratios.map((r) => [r.name, r]) ?? []);
  const wc = byName.get("working_capital");
  const cr = byName.get("current_ratio");

  return (
    <div className={styles.kpiStrip}>
      <KpiCard label="Total Assets" value={<MoneyValue value={check.total_assets} />} />
      <KpiCard label="Total Liabilities" value={<MoneyValue value={check.total_liabilities} />} />
      <KpiCard label="Total Equity" value={<MoneyValue value={check.total_equity} />} />
      {wc && wc.status !== "unavailable" && (
        <KpiCard label="Working Capital" value={<MoneyValue value={wc.value} />} />
      )}
      {cr && cr.status !== "unavailable" && (
        <KpiCard
          label="Current Ratio"
          value={<RatioValue value={cr.value} />}
          tone={
            cr.value
              ? parseFloat(cr.value) >= 1.5
                ? "ok"
                : parseFloat(cr.value) >= 1
                ? "warn"
                : "bad"
              : undefined
          }
        />
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactElement;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <div className={styles.kpiCard}>
      <span className={styles.kpiLabel}>{label}</span>
      <span
        className={styles.kpiValue}
        data-tone={tone ?? undefined}
      >
        {value}
      </span>
    </div>
  );
}

function EquationPanel({
  check,
  validation,
}: {
  check: EquationCheck;
  validation: ValidationSummary | null;
}) {
  return (
    <section className="card">
      <h2 className="eyebrow">Accounting equation</h2>
      <dl className={styles.equation}>
        <dt>Total assets</dt>
        <dd>
          <MoneyValue value={check.total_assets} />
        </dd>
        <dt>Total liabilities</dt>
        <dd>
          <MoneyValue value={check.total_liabilities} />
        </dd>
        <dt>Total equity</dt>
        <dd>
          <MoneyValue value={check.total_equity} />
        </dd>
        <div className={styles.equationRule} role="presentation" />
        <dt className={styles.equationTotal}>Liabilities + equity</dt>
        <dd className={styles.equationTotal}>
          <MoneyValue value={check.expected} />
        </dd>
        <dt>Difference</dt>
        <dd>
          <MoneyValue value={check.difference} negativeStyle="minus" />
        </dd>
        <dt>Tolerance applied</dt>
        <dd>
          <MoneyValue value={check.tolerance_applied} trimTrailingZeros />
        </dd>
      </dl>

      <div className={styles.verdict}>
        <StatusPill tone={check.balanced ? "ok" : "bad"}>
          {check.balanced ? "Balances" : "Does not balance"}
        </StatusPill>
        {validation && !validation.required_fields_present && (
          <span className="muted">Required fields missing</span>
        )}
      </div>

      {validation && validation.missing_fields.length > 0 && (
        <ul className={styles.missing}>
          {validation.missing_fields.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StructureBar({ check }: { check: EquationCheck }) {
  const assets = parseFloat(check.total_assets) || 0;
  const liabilities = parseFloat(check.total_liabilities) || 0;
  const equity = parseFloat(check.total_equity) || 0;
  const total = Math.max(assets, liabilities + equity, 1);

  const assetPct = Math.min(100, (assets / total) * 100);
  const liabPct = Math.min(100, (liabilities / total) * 100);
  const eqPct = Math.min(100, (equity / total) * 100);

  return (
    <section className={styles.structureCard}>
      <h2 className="eyebrow">Balance sheet structure</h2>
      <div className={styles.structureGrid}>
        <div className={styles.structureCol}>
          <span className={styles.structureColLabel}>Assets</span>
          <div className={styles.barTrack}>
            <div
              className={`${styles.barFill} ${styles.barAssets}`}
              style={{ width: `${assetPct}%` }}
              title={`Assets ${assetPct.toFixed(1)}%`}
            />
          </div>
          <span className={styles.structureFigure}>
            <MoneyValue value={check.total_assets} />
          </span>
        </div>
        <div className={styles.structureCol}>
          <span className={styles.structureColLabel}>Liabilities + Equity</span>
          <div className={styles.barTrack}>
            <div
              className={`${styles.barFill} ${styles.barLiab}`}
              style={{ width: `${liabPct}%` }}
              title={`Liabilities ${liabPct.toFixed(1)}%`}
            />
            <div
              className={`${styles.barFill} ${styles.barEquity}`}
              style={{ width: `${eqPct}%` }}
              title={`Equity ${eqPct.toFixed(1)}%`}
            />
          </div>
          <div className={styles.structureFigurePair}>
            <span>
              <span className={styles.dotLiab} /> Liabilities{" "}
              <MoneyValue value={check.total_liabilities} />
            </span>
            <span>
              <span className={styles.dotEquity} /> Equity{" "}
              <MoneyValue value={check.total_equity} />
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function IdentificationPanel({
  evidence,
}: {
  evidence: IdentificationEvidence;
}) {
  return (
    <section className="card">
      <h2 className="eyebrow">Identification</h2>
      <div className={styles.score}>
        <span className={styles.scoreValue}>{evidence.score}</span>
        <span className="muted">
          out of a threshold of {evidence.threshold}
        </span>
        <StatusPill tone={evidence.is_balance_sheet ? "ok" : "bad"}>
          {evidence.is_balance_sheet ? "Balance Sheet" : "Not recognised"}
        </StatusPill>
      </div>

      {evidence.signals.length > 0 && (
        <details className={styles.details}>
          <summary className={styles.summary}>
            {evidence.signals.length} matching signal
            {evidence.signals.length === 1 ? "" : "s"}
          </summary>
          <ul className={styles.signals}>
            {evidence.signals.map((signal, index) => (
              <li key={`${signal.kind}-${index}`} className={styles.signal}>
                <span className={styles.signalKind}>
                  {signal.kind.replace(/_/g, " ")}
                </span>
                <span className={styles.signalText}>{signal.text}</span>
                <span className={styles.signalWeight}>+{signal.weight}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function PeriodPanel({ period }: { period: PeriodSelection }) {
  const others = period.candidates.filter(
    (candidate) => candidate.label !== period.selected.label,
  );

  return (
    <section className="card">
      <h2 className="eyebrow">Reporting period</h2>
      <p>
        <strong>{period.selected.label}</strong>
        <span className="muted"> — {period.reason}</span>
      </p>

      {others.length > 0 && (
        <>
          <p className="muted">
            This sheet is comparative. Single-period scope means only the column
            above was analysed; no figure was read from the others.
          </p>
          <ul className={styles.candidates}>
            {others.map((candidate) => (
              <li key={candidate.label}>{candidate.label} — not analysed</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
