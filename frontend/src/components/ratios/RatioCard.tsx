/**
 * One ratio, and everything needed to argue with it.
 *
 * Three rules this component exists to keep:
 *
 * **An unavailable ratio renders no numeral.** Not a zero, not a dash standing
 * in for one. "Could not be computed" and "is zero" are different claims and
 * must not look alike.
 *
 * **A partial ratio states its bound.** The excluded lines and their total are
 * shown, so a reader can place the true value between the figure given and the
 * figure with those added, rather than reading an understated number as exact.
 *
 * **Nothing is clamped.** A negative result keeps its sign and its warning.
 */

import type { ReactElement } from "react";
import {
  BASIS_LABEL,
  describeRatioReason,
  describeRatioWarning,
  ratioLabel,
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
          // Deliberately not a figure component: there is no figure.
          <span>Not computed</span>
        ) : money ? (
          <MoneyValue value={ratio.value} />
        ) : (
          <RatioValue value={ratio.value} />
        )}
      </div>

      <p className={styles.formula}>{ratio.formula}</p>

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

/**
 * What was left out, and what that does to the figure.
 *
 * `excluded_value` is the backend's own bound: the reported value and the
 * value with this added contain the true one.
 */
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
  const hasInputs =
    ratio.numerator_inputs.length > 0 ||
    ratio.denominator_inputs.length > 0 ||
    ratio.excluded.length > 0;

  return (
    <details className={styles.details}>
      <summary className={styles.summary}>How this was computed</summary>

      <p className={styles.definition}>{ratio.definition}</p>

      <dl className={styles.operands}>
        <dt>{money ? "Minuend" : "Numerator"}</dt>
        <dd>
          <MoneyValue value={ratio.numerator} />
          {ratio.numerator_basis && (
            <span className={styles.basis}>
              {BASIS_LABEL[ratio.numerator_basis] ?? ratio.numerator_basis}
            </span>
          )}
        </dd>

        <dt>{money ? "Subtrahend" : "Denominator"}</dt>
        <dd>
          <MoneyValue value={ratio.denominator} />
          {ratio.denominator_basis && (
            <span className={styles.basis}>
              {BASIS_LABEL[ratio.denominator_basis] ?? ratio.denominator_basis}
            </span>
          )}
        </dd>
      </dl>

      {hasInputs && (
        <>
          <InputList
            heading={money ? "Added" : "In the numerator"}
            inputs={ratio.numerator_inputs}
          />
          <InputList
            heading={money ? "Subtracted" : "In the denominator"}
            inputs={ratio.denominator_inputs}
          />
          {ratio.excluded.length > 0 && (
            <InputList
              heading="Excluded — could not be classified"
              inputs={ratio.excluded}
              warn
            />
          )}
        </>
      )}
    </details>
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
      <p className={warn ? styles.excludedHeading : styles.definition}>
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
