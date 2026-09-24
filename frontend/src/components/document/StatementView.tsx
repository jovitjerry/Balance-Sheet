import type { ReactElement } from "react";
import type {
  BalanceSheetDocument,
  BalanceSheetSection,
  LineItem,
} from "../../types/balanceSheet";
import { humanizeIdentifier, sameConcept } from "../../lib/labels";
import { signOf } from "../../lib/money";
import { MoneyValue } from "../common/Figures";
import { StatusPill } from "../common/StatusPill";
import styles from "./StatementView.module.css";
const SECTIONS = [
  { key: "assets", heading: "Assets" },
  { key: "liabilities", heading: "Liabilities" },
  { key: "equity", heading: "Shareholders' equity" },
] as const;
export function StatementView({
  document,
}: {
  document: BalanceSheetDocument;
}): ReactElement | null {
  const extracted = document.extracted;
  if (!extracted) return null;
  return (
    <>
      {extracted.normalization_summary && (
        <NormalizationSummary summary={extracted.normalization_summary} />
      )}
      {SECTIONS.map(({ key, heading }) => (
        <SectionTable
          key={key}
          heading={heading}
          section={extracted[key]}
        />
      ))}
    </>
  );
}
function NormalizationSummary({ summary }: { summary: Record<string, number> }) {
  const entries = Object.entries(summary).filter(([, count]) => count > 0);
  if (entries.length === 0) return null;
  return (
    <section className="card">
      <h2 className="eyebrow">Terminology mapping</h2>
      <p className={styles.summary}>
        {entries.map(([status, count]) => (
          <span key={status}>
            <span className={styles.count}>{count}</span>{" "}
            {status.replace(/_/g, " ")}
          </span>
        ))}
      </p>
      <p className="muted">
        Labels the local model could not confidently map are marked for review
        rather than guessed at. The figures are unaffected — extraction
        completes before any model is consulted.
      </p>
    </section>
  );
}
function SectionTable({
  heading,
  section,
}: {
  heading: string;
  section: BalanceSheetSection;
}) {
  const groups = groupBySubsection(section.line_items);
  return (
    <section className="card">
      <h2 className="eyebrow">{heading}</h2>
      <div className={styles.section}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Line item</th>
              <th scope="col" className={styles.numeric}>
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {groups.map(({ subsection, items }) => (
              <SubsectionRows
                key={subsection ?? "ungrouped"}
                subsection={subsection}
                items={items}
                showHeading={groups.length > 1}
              />
            ))}
            <tr className={styles.total}>
              <td>{section.total_label || `Total ${heading.toLowerCase()}`}</td>
              <td className={styles.numeric}>
                <MoneyValue value={section.total} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <ReconciliationNote section={section} />
    </section>
  );
}
function SubsectionRows({
  subsection,
  items,
  showHeading,
}: {
  subsection: string | null;
  items: LineItem[];
  showHeading: boolean;
}) {
  return (
    <>
      {showHeading && (
        <tr className={styles.subheading}>
          <td colSpan={2}>
            {subsection ? subsection.replace(/_/g, "-") : "Unclassified"}
          </td>
        </tr>
      )}
      {items.map((item, index) => (
        <LineItemRow key={`${item.label}-${index}`} item={item} />
      ))}
    </>
  );
}
function LineItemRow({ item }: { item: LineItem }) {
  const normalization = item.normalization;
  const canonical = normalization?.canonical_label;
  const needsReview =
    normalization?.status === "needs_review" ||
    normalization?.status === "unmapped";
  const unavailable = normalization?.status === "unavailable";
  return (
    <tr>
      <td className={styles.label}>
        {item.label}
        <span className={styles.flags}>
          {needsReview && (
            <StatusPill
              tone="warn"
              title={normalization?.reason ?? "Not mapped to the canonical vocabulary."}
            >
              Needs review
            </StatusPill>
          )}
          {unavailable && (
            <StatusPill tone="neutral" title="The local model was unreachable.">
              Not mapped
            </StatusPill>
          )}
          {item.status === "unparsed_value" && (
            <StatusPill tone="warn" title="The printed figure could not be parsed.">
              Unparsed
            </StatusPill>
          )}
        </span>
        {}
        {canonical && !sameConcept(canonical, item.label) && (
          <span className={styles.canonical}>{humanizeIdentifier(canonical)}</span>
        )}
      </td>
      <td className={styles.numeric}>
        {item.status === "unparsed_value" ? (
          <span className={styles.raw} title="Exactly as printed; it would not parse.">
            {item.raw ?? "—"}
          </span>
        ) : (
          <MoneyValue value={item.value} />
        )}
      </td>
    </tr>
  );
}
function ReconciliationNote({ section }: { section: BalanceSheetSection }) {
  const difference = section.reconciliation_difference;
  if (!difference || signOf(difference) === 0) return null;
  return (
    <p className={styles.reconcile}>
      The printed total differs from the sum of the extracted line items by{" "}
      <MoneyValue value={difference} negativeStyle="minus" />. This is a
      diagnostic, not a validation failure — printed subtotals and rounding make
      exact agreement unusual, and the accounting equation is checked separately.
    </p>
  );
}
function groupBySubsection(items: LineItem[]) {
  const groups: { subsection: string | null; items: LineItem[] }[] = [];
  for (const item of items) {
    const subsection = item.subsection ?? null;
    const last = groups[groups.length - 1];
    if (last && last.subsection === subsection) {
      last.items.push(item);
    } else {
      groups.push({ subsection, items: [item] });
    }
  }
  return groups;
}
