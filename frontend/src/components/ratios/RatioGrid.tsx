import { useState, type ReactElement } from "react";
import { GROUP_LABEL, RATIO_GROUP, RATIO_ORDER } from "../../lib/ratios";
import type { RatioResult, RatioSet } from "../../types/balanceSheet";
import { EmptyState } from "../common/Feedback";
import { RatioCard, RatioDetailPanel } from "./RatioCard";
import styles from "./RatioGrid.module.css";

export function RatioGrid({
  ratios,
}: {
  ratios: RatioSet | null;
}): ReactElement {
  const [expandedRatio, setExpandedRatio] = useState<string | null>(null);

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
          .filter((ratio): ratio is RatioResult => ratio !== undefined);
        if (present.length === 0) return null;

        const activeDetailRatio = present.find(
          (ratio) => ratio.name === expandedRatio
        );

        return (
          <section key={group} className={styles.group} data-group={group}>
            <h2 className="eyebrow">{GROUP_LABEL[group]}</h2>
            <div className={styles.grid}>
              {present.map((ratio) => (
                <RatioCard
                  key={ratio.name}
                  ratio={ratio}
                  isExpanded={expandedRatio === ratio.name}
                  onToggle={() =>
                    setExpandedRatio((current) =>
                      current === ratio.name ? null : ratio.name
                    )
                  }
                />
              ))}
            </div>

            {activeDetailRatio && (
              <RatioDetailPanel
                ratio={activeDetailRatio}
                onClose={() => setExpandedRatio(null)}
              />
            )}
          </section>
        );
      })}
    </>
  );
}
