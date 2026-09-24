import type { ReactElement } from "react";
import {
  BASIS_LABEL,
  describeRatioReason,
  describeRatioWarning,
  ratioLabel,
  splitFormula,
} from "../../lib/ratios";
import type { RatioInput, RatioResult } from "../../types/balanceSheet";
import { MoneyValue, RatioValue } from "../common/Figures";
import { RATIO_STATUS_LABEL, ratioStatusTone, StatusPill } from "../common/StatusPill";
import styles from "./RatioCard.module.css";
export function RatioCard({ ratio }: { ratio: RatioResult }): ReactElement {
  const money = ratio.unit === "currency";
  const unavailable = ratio.status === "unavailable";
  return (
    <article className={styles.card} data-status={ratio.status}>
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
      {}
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
      {!unavailable && <RatioDetail ratio={ratio} money={money} />}
    </article>
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
function RatioDetail({ ratio, money }: { ratio: RatioResult; money: boolean }) {
  const parts = splitFormula(ratio.formula);
  const hasInputs =
    ratio.numerator_inputs.length > 0 ||
    ratio.denominator_inputs.length > 0 ||
    ratio.excluded.length > 0;
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>How this was computed</summary>
      <dl className={styles.steps}>
        <dt className={styles.stepLabel}>Formula</dt>
        <dd className={styles.stepBody}>
          <span className={styles.formulaText}>
            {readableFormula(ratio.formula)}
          </span>
        </dd>
        <dt className={styles.stepLabel}>Values used</dt>
        <dd className={styles.stepBody}>
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
        </dd>
        <dt className={styles.stepLabel}>Calculation</dt>
        <dd className={styles.stepBody}>
          <p className={styles.calculation}>
            {ratioLabel(ratio.name)} ={" "}
            <MoneyValue value={ratio.numerator} negativeStyle="minus" withSymbol />{" "}
            {parts ? parts.operator : "÷"}{" "}
            <MoneyValue value={ratio.denominator} negativeStyle="minus" withSymbol />{" "}
            ={" "}
            {money ? (
              <MoneyValue value={ratio.value} negativeStyle="minus" withSymbol />
            ) : (
              <RatioValue value={ratio.value} />
            )}
          </p>
        </dd>
        <dt className={styles.stepLabel}>What it means</dt>
        <dd className={styles.stepBody}>
          <p className={styles.definition}>{ratio.definition}</p>
        </dd>
      </dl>
      {hasInputs && (
        <>
          <InputList
            heading={money ? "Lines added up" : "Lines in the first amount"}
            inputs={ratio.numerator_inputs}
          />
          <InputList
            heading={money ? "Lines subtracted" : "Lines in the second amount"}
            inputs={ratio.denominator_inputs}
          />
          {ratio.excluded.length > 0 && (
            <InputList
              heading="Left out — could not be classified"
              inputs={ratio.excluded}
              warn
            />
          )}
        </>
      )}
    </details>
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
    <p className={styles.operand}>
      <span className={styles.operandName}>{name}</span>
      <MoneyValue value={value} withSymbol />
      {basis && (
        <span className={styles.basis}>{BASIS_LABEL[basis] ?? basis}</span>
      )}
    </p>
  );
}
function InputList({
  heading,
  inputs,
  warn = false,
}: {
  heading: string;
  inputs: RatioInput[];
  warn?: boolean;
}) {
  if (inputs.length === 0) return null;
  return (
    <>
      <p className={warn ? styles.excludedHeading : styles.inputHeading}>
        {heading}
      </p>
      <ul className={styles.inputs}>
        {inputs.map((input, index) => (
          <li key={`${input.label}-${index}`} className={styles.input}>
            <span className={styles.inputLabel}>{input.label}</span>
            <MoneyValue value={input.value} />
          </li>
        ))}
      </ul>
    </>
  );
}
