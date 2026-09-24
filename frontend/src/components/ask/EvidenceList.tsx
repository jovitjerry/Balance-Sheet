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
function displayLabel(item: Evidence): string {
  if (item.kind === "ratio") return ratioLabel(item.label);
  return isIdentifier(item.label) ? humanizeIdentifier(item.label) : item.label;
}
interface EvidenceListProps {
  items: Evidence[];
  summary: string;
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
                  {}
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
