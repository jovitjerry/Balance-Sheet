import type { ReactElement } from "react";
import {
  BASIS_LABEL,
  describeRatioReason,
  describeRatioWarning,
  ratioLabel,
  splitFormula,
} from "../../lib/ratios";
import type { RatioResult } from "../../types/balanceSheet";
import { MoneyValue, RatioValue } from "../common/Figures";
import { RATIO_STATUS_LABEL, ratioStatusTone, StatusPill } from "../common/StatusPill";
import styles from "./RatioCard.module.css";

export function RatioCard({
  ratio,
  isExpanded = false,
  onToggle,
}: {
  ratio: RatioResult;
  isExpanded?: boolean;
  onToggle?: () => void;
}): ReactElement {
  const money = ratio.unit === "currency";
  const unavailable = ratio.status === "unavailable";

  return (
    <article
      className={styles.card}
      data-status={ratio.status}
      data-expanded={isExpanded}
    >
      <div className={styles.head}>
        <h3 className={styles.name}>{ratioLabel(ratio.name)}</h3>
        <StatusPill tone={ratioStatusTone(ratio.status)}>
          {RATIO_STATUS_LABEL[ratio.status]}
        </StatusPill>
      </div>

      <div className={styles.value}>
        {unavailable ? (
          <span>Not computed</span>
        ) : money ? (
          <MoneyValue value={ratio.value} />
        ) : (
          <RatioValue value={ratio.value} />
        )}
      </div>

      <p className={styles.formula}>{readableFormula(ratio.formula)}</p>

      {unavailable && ratio.reason && (
        <p className={styles.reason}>{describeRatioReason(ratio.reason)}</p>
      )}

      {ratio.status === "partial" && (
        <PartialBound ratio={ratio} money={money} />
      )}

      {ratio.warnings.map((warning) => (
        <p key={warning} className={styles.warning}>
          {describeRatioWarning(warning)}
        </p>
      ))}

      {!unavailable && onToggle && (
        <button
          type="button"
          className={styles.toggleBtn}
          onClick={onToggle}
          aria-expanded={isExpanded}
        >
          {isExpanded ? "Hide calculation details ▲" : "How this was computed ▼"}
        </button>
      )}
    </article>
  );
}

export function RatioDetailPanel({
  ratio,
  onClose,
}: {
  ratio: RatioResult;
  onClose: () => void;
}): ReactElement {
  const money = ratio.unit === "currency";
  const parts = splitFormula(ratio.formula);
  const hasInputs =
    ratio.numerator_inputs.length > 0 ||
    ratio.denominator_inputs.length > 0 ||
    ratio.excluded.length > 0;

  return (
    <div className={styles.detailPanel}>
      <div className={styles.panelHeader}>
        <h3 className={styles.panelTitle}>{ratioLabel(ratio.name)}</h3>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={onClose}
          aria-label="Close calculation details"
        >
          ✕ Close
        </button>
      </div>

      <div className={styles.panelGrid}>
        {}
        <div className={styles.panelCol}>
          <div className={styles.block}>
            <span className={styles.blockLabel}>Formula</span>
            <code className={styles.formulaCode}>{readableFormula(ratio.formula)}</code>
          </div>

          <div className={styles.block}>
            <span className={styles.blockLabel}>Calculation</span>
            <div className={styles.calcBox}>
              <MoneyValue value={ratio.numerator} negativeStyle="minus" withSymbol />{" "}
              <span className={styles.mathOp}>{parts ? parts.operator : "÷"}</span>{" "}
              <MoneyValue value={ratio.denominator} negativeStyle="minus" withSymbol />
              {" = "}
              <span className={styles.calcResult}>
                {money ? (
                  <MoneyValue value={ratio.value} negativeStyle="minus" withSymbol />
                ) : (
                  <RatioValue value={ratio.value} />
                )}
              </span>
            </div>
          </div>

          <div className={styles.block}>
            <span className={styles.blockLabel}>What it means</span>
            <p className={styles.definitionText}>{ratio.definition}</p>
          </div>
        </div>

        {}
        <div className={styles.panelCol}>
          <div className={styles.block}>
            <span className={styles.blockLabel}>Values Used</span>
            <div className={styles.operandsList}>
              <Operand
                name={parts ? parts.left : money ? "First amount" : "Numerator"}
                value={ratio.numerator}
                basis={ratio.numerator_basis}
              />
              <Operand
                name={parts ? parts.right : money ? "Second amount" : "Denominator"}
                value={ratio.denominator}
                basis={ratio.denominator_basis}
              />
            </div>
          </div>
        </div>
      </div>

      {}
      {hasInputs && (
        <details className={styles.fullBreakdownSection}>
          <summary className={styles.breakdownToggle}>Component line items</summary>
          <div className={styles.breakdownTablesGrid}>
            {ratio.numerator_inputs.length > 0 && (
              <div className={styles.tableBlock}>
                <span className={styles.tableHeading}>
                  {money ? "Lines added up" : "Numerator line items"}
                </span>
                <table className={styles.inputTable}>
                  <thead>
                    <tr>
                      <th>Line Item</th>
                      <th className={styles.rightAlign}>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ratio.numerator_inputs.map((inp, idx) => (
                      <tr key={`num-${inp.label}-${idx}`}>
                        <td>{inp.label}</td>
                        <td className={styles.rightAlign}>
                          <MoneyValue value={inp.value} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {ratio.denominator_inputs.length > 0 && (
              <div className={styles.tableBlock}>
                <span className={styles.tableHeading}>
                  {money ? "Lines subtracted" : "Denominator line items"}
                </span>
                <table className={styles.inputTable}>
                  <thead>
                    <tr>
                      <th>Line Item</th>
                      <th className={styles.rightAlign}>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ratio.denominator_inputs.map((inp, idx) => (
                      <tr key={`den-${inp.label}-${idx}`}>
                        <td>{inp.label}</td>
                        <td className={styles.rightAlign}>
                          <MoneyValue value={inp.value} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {ratio.excluded.length > 0 && (
              <div className={`${styles.tableBlock} ${styles.tableBlockWarn}`}>
                <span className={styles.tableHeadingWarn}>
                  Excluded (unclassified)
                </span>
                <table className={styles.inputTable}>
                  <thead>
                    <tr>
                      <th>Line Item</th>
                      <th className={styles.rightAlign}>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ratio.excluded.map((inp, idx) => (
                      <tr key={`exc-${inp.label}-${idx}`}>
                        <td>{inp.label}</td>
                        <td className={styles.rightAlign}>
                          <MoneyValue value={inp.value} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function readableFormula(formula: string): string {
  const parts = splitFormula(formula);
  return parts ? `${parts.left} ${parts.operator} ${parts.right}` : formula;
}

function PartialBound({
  ratio,
  money,
}: {
  ratio: RatioResult;
  money: boolean;
}) {
  return (
    <p className={styles.bound}>
      {ratio.excluded.length} line
      {ratio.excluded.length === 1 ? " was" : "s were"} left out because
      {ratio.excluded.length === 1 ? " it" : " they"} could not be classified
      {ratio.excluded_value && (
        <>
          , totalling <MoneyValue value={ratio.excluded_value} />
        </>
      )}
      . The true {money ? "amount" : "ratio"} lies between the figure above and
      the figure with those included.
    </p>
  );
}

function Operand({
  name,
  value,
  basis,
}: {
  name: string;
  value: RatioResult["numerator"];
  basis: RatioResult["numerator_basis"];
}) {
  return (
    <div className={styles.operandItem}>
      <div className={styles.operandHeader}>
        <span className={styles.operandName}>{name}</span>
        {basis && (
          <span className={styles.basisBadge}>{BASIS_LABEL[basis] ?? basis}</span>
        )}
      </div>
      <span className={styles.operandValue}>
        <MoneyValue value={value} withSymbol />
      </span>
    </div>
  );
}
