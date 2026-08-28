/**
 * The evidence behind an answer.
 *
 * Two lists, kept apart because they make different claims. **Citations** are
 * what the model actually pointed at - already resolved by the backend, which
 * drops any tag that resolves to nothing rather than shipping one that points
 * nowhere. **Supporting facts** are everything that was placed in its context,
 * cited or not, which is what lets a reader see what it had available and
 * chose not to use.
 */

import type { ReactElement } from "react";
import { humanizeIdentifier, isIdentifier } from "../../lib/labels";
import { ratioLabel } from "../../lib/ratios";
import type { Evidence } from "../../types/answers";
import { MoneyValue } from "../common/Figures";
import styles from "./Ask.module.css";

const KIND_LABEL: Record<string, string> = {
  section_total: "Section total",
  line_item: "Line item",
  ratio: "Ratio",
  equation: "Accounting equation",
  coverage: "Coverage",
  text: "Document text",
};

/**
 * A ratio's evidence label is its formula-set name (`debt_to_equity`); other
 * kinds carry the document's own wording and are left exactly as printed.
 */
function displayLabel(item: Evidence): string {
  if (item.kind === "ratio") return ratioLabel(item.label);
  return isIdentifier(item.label) ? humanizeIdentifier(item.label) : item.label;
}

interface EvidenceListProps {
  items: Evidence[];
  summary: string;
  /** Open by default where the evidence is the answer, as when degraded. */
  open?: boolean;
}

export function EvidenceList({
  items,
  summary,
  open = false,
}: EvidenceListProps): ReactElement | null {
  if (items.length === 0) return null;

  return (
    <details className={styles.evidence} open={open}>
      <summary className={styles.evidenceSummary}>
        {summary} ({items.length})
      </summary>
      <ul className={styles.evidenceList}>
        {items.map((item) => (
          <li key={item.id} className={styles.evidenceItem}>
            <span className={styles.tag}>{item.id}</span>
            <span className={styles.evidenceLabel}>
              {displayLabel(item)}
              {item.value && (
                <>
                  {" — "}
                  {/* Routed through the same formatter as every other figure
                      in the app, so a total does not read as 1350000 here and
                      1,350,000 two tabs away. A ratio takes a minus sign
                      rather than accounting parentheses. */}
                  <MoneyValue
                    value={item.value}
                    negativeStyle={item.kind === "ratio" ? "minus" : "parens"}
                    className={styles.evidenceValue}
                  />
                </>
              )}
            </span>
            {item.detail && (
              <span className={styles.evidenceDetail}>
                {isIdentifier(item.detail)
                  ? humanizeIdentifier(item.detail)
                  : item.detail}
              </span>
            )}
            {item.quote && <blockquote className={styles.quote}>{item.quote}</blockquote>}
            <span className={styles.evidenceSource}>
              {KIND_LABEL[item.kind] ?? item.kind}
              {item.page_index !== null && item.page_index !== undefined && (
                <> · page {item.page_index + 1}</>
              )}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
