/**
 * Module 1's verdict and the evidence behind it.
 *
 * A rejection is shown first and in full. `core/schemas.py` keeps rejected
 * submissions deliberately - "an auditor needs to see what was refused and why
 * as much as what was accepted" - and that is only true if the refusal is
 * actually legible here.
 */

import type { ReactElement } from "react";
import type {
  BalanceSheetDocument,
  EquationCheck,
  IdentificationEvidence,
  PeriodSelection,
  ValidationSummary,
} from "../../types/balanceSheet";
import { MoneyValue } from "../common/Figures";
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

      <div className={styles.grid}>
        {document.equation_check && (
          <EquationPanel
            check={document.equation_check}
            validation={document.validation ?? null}
          />
        )}
        {document.identification && (
          <IdentificationPanel evidence={document.identification} />
        )}
      </div>

      {document.period && <PeriodPanel period={document.period} />}
    </>
  );
}

/**
 * Total Assets = Total Liabilities + Equity.
 *
 * `difference` is signed and always shown, so a near-miss inside tolerance is
 * visible rather than silently passing.
 */
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
          {/* A derived threshold, so it arrives with the full scale of the
              percentage that produced it - "11,500.000" among a column of
              whole amounts reads as a typo. The value is unchanged; only
              insignificant trailing zeros are dropped. */}
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

/** Why the system concluded this is - or is not - a Balance Sheet. */
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

/**
 * Which reporting period was analysed.
 *
 * The unanalysed candidates are listed because the scope limit is a real
 * constraint a reader should be able to see: a comparative sheet has other
 * columns, and no figure was ever read from them.
 */
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
