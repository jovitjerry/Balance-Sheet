/**
 * The seven ratios, in a fixed order.
 *
 * Fixed rather than sorted by value or status: a reader comparing two
 * documents should find the same ratio in the same place, and ordering by
 * outcome would quietly rank them.
 */

import type { ReactElement } from "react";
import { GROUP_LABEL, RATIO_GROUP, RATIO_ORDER } from "../../lib/ratios";
import type { RatioSet } from "../../types/balanceSheet";
import { EmptyState } from "../common/Feedback";
import { RatioCard } from "./RatioCard";
import styles from "./RatioGrid.module.css";

export function RatioGrid({
  ratios,
}: {
  ratios: RatioSet | null;
}): ReactElement {
  if (!ratios || ratios.ratios.length === 0) {
    return (
      <EmptyState title="No ratios were computed">
        <p>This document did not reach the ratio engine.</p>
      </EmptyState>
    );
  }

  const byName = new Map(ratios.ratios.map((ratio) => [ratio.name, ratio]));
  const groups: Array<"liquidity" | "leverage"> = ["liquidity", "leverage"];

  return (
    <>
      {groups.map((group) => {
        const names = RATIO_ORDER.filter((name) => RATIO_GROUP[name] === group);
        const present = names
          .map((name) => byName.get(name))
          .filter((ratio) => ratio !== undefined);

        if (present.length === 0) return null;

        return (
          <section key={group} className={styles.group}>
            <h2 className="eyebrow">{GROUP_LABEL[group]}</h2>
            <div className={styles.grid}>
              {present.map((ratio) => (
                <RatioCard key={ratio.name} ratio={ratio} />
              ))}
            </div>
          </section>
        );
      })}

      <section className="card">
        <h2 className="eyebrow">About these figures</h2>
        <p className={styles.caveat}>
          Computed in deterministic Python from the extracted figures — no
          language model is involved, and none can be. They come from a single
          reporting period, so they carry no trend and no industry benchmark; a
          value is only meaningful beside context this system does not hold.
        </p>
        <p className={styles.meta}>
          <span>Formula set {ratios.spec_version}</span>
          {ratios.taxonomy_version && (
            <span>Vocabulary {ratios.taxonomy_version}</span>
          )}
          {ratios.currency && <span>{ratios.currency}</span>}
          {ratios.scale_label && (
            <span>Printed {ratios.scale_label}, not applied</span>
          )}
        </p>

        {ratios.warnings.length > 0 && (
          <ul className={styles.warnings}>
            {ratios.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
