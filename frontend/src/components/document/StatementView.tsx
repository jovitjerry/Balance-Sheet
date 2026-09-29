import type { ReactElement } from "react";
import type {
  BalanceSheetDocument,
  BalanceSheetSection,
  ExtractedBalanceSheet,
  LineItem,
} from "../../types/balanceSheet";
import { humanizeIdentifier, sameConcept } from "../../lib/labels";
import { signOf } from "../../lib/money";
import { MoneyValue } from "../common/Figures";
import { StatusPill } from "../common/StatusPill";
import styles from "./StatementView.module.css";

export function StatementView({
  document,
}: {
  document: BalanceSheetDocument;
}): ReactElement | null {
  const extracted = document.extracted;
  if (!extracted) return null;

  return (
    <div className={styles.container}>
      {extracted.normalization_summary && (
        <NormalizationSummary summary={extracted.normalization_summary} />
      )}
      <SummaryBar extracted={extracted} />
      <div className={styles.statementLayout}>
        <div className={styles.column}>
          <SectionTable
            heading="Assets"
            section={extracted.assets}
          />
        </div>
        <div className={styles.column}>
          <SectionTable
            heading="Liabilities"
            section={extracted.liabilities}
          />
          <SectionTable
            heading="Shareholders' equity"
            section={extracted.equity}
          />
        </div>
      </div>
    </div>
  );
}

function parseMoney(v: string | null | undefined): number {
  if (!v) return 0;
  return parseFloat(v.replace(/,/g, "")) || 0;
}

function SummaryBar({ extracted }: { extracted: ExtractedBalanceSheet }) {
  const totalAssets = parseMoney(extracted.assets.total);
  const totalLiab   = parseMoney(extracted.liabilities.total);
  const totalEquity = parseMoney(extracted.equity.total);
  const denominator = Math.max(totalAssets, totalLiab + totalEquity, 1);

  const currentAssets = extracted.assets.line_items
    .filter(i => {
      const sub = (i.subsection ?? "").toLowerCase();
      return sub.includes("current") && !sub.includes("non");
    })
    .reduce((s, i) => s + parseMoney(i.value), 0);
  const nonCurrentAssets = Math.max(0, totalAssets - currentAssets);

  const currentLiab = extracted.liabilities.line_items
    .filter(i => {
      const sub = (i.subsection ?? "").toLowerCase();
      return sub.includes("current") && !sub.includes("non");
    })
    .reduce((s, i) => s + parseMoney(i.value), 0);
  const nonCurrentLiab = Math.max(0, totalLiab - currentLiab);

  const pct = (v: number) =>
    `${Math.min(100, Math.max(0, (v / denominator) * 100)).toFixed(2)}%`;

  return (
    <section className={styles.summaryBar}>
      <h2 className="eyebrow">Balance Sheet Structure</h2>
      <div className={styles.summaryStructure}>
        {}
        <div className={styles.summaryHalf}>
          <div className={styles.summaryHalfLabel}>
            Assets
            <span className={styles.summaryHalfTotal}>
              <MoneyValue value={extracted.assets.total} />
            </span>
          </div>
          <div className={styles.segBar}>
            {currentAssets > 0 && (
              <div
                className={`${styles.segment} ${styles.segCA}`}
                style={{ width: pct(currentAssets) }}
                title={`Current assets: ${pct(currentAssets)}`}
              />
            )}
            {nonCurrentAssets > 0 && (
              <div
                className={`${styles.segment} ${styles.segNCA}`}
                style={{ width: pct(nonCurrentAssets) }}
                title={`Non-current assets: ${pct(nonCurrentAssets)}`}
              />
            )}
          </div>
          <div className={styles.segLegend}>
            <span className={styles.segLegendItem}>
              <span className={`${styles.segDot} ${styles.segCA}`} />Current
            </span>
            <span className={styles.segLegendItem}>
              <span className={`${styles.segDot} ${styles.segNCA}`} />Non-current
            </span>
          </div>
        </div>

        <div className={styles.summaryDivider} aria-hidden="true">=</div>

        {}
        <div className={styles.summaryHalf}>
          <div className={styles.summaryHalfLabel}>
            Liabilities + Equity
            <span className={styles.summaryHalfTotal}>
              <MoneyValue value={extracted.liabilities.total} />
              {" + "}
              <MoneyValue value={extracted.equity.total} />
            </span>
          </div>
          <div className={styles.segBar}>
            {currentLiab > 0 && (
              <div
                className={`${styles.segment} ${styles.segCL}`}
                style={{ width: pct(currentLiab) }}
                title={`Current liabilities: ${pct(currentLiab)}`}
              />
            )}
            {nonCurrentLiab > 0 && (
              <div
                className={`${styles.segment} ${styles.segNCL}`}
                style={{ width: pct(nonCurrentLiab) }}
                title={`Non-current liabilities: ${pct(nonCurrentLiab)}`}
              />
            )}
            {totalEquity > 0 && (
              <div
                className={`${styles.segment} ${styles.segEq}`}
                style={{ width: pct(totalEquity) }}
                title={`Equity: ${pct(totalEquity)}`}
              />
            )}
          </div>
          <div className={styles.segLegend}>
            <span className={styles.segLegendItem}>
              <span className={`${styles.segDot} ${styles.segCL}`} />Current liab.
            </span>
            <span className={styles.segLegendItem}>
              <span className={`${styles.segDot} ${styles.segNCL}`} />Non-current liab.
            </span>
            <span className={styles.segLegendItem}>
              <span className={`${styles.segDot} ${styles.segEq}`} />Equity
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function NormalizationSummary({ summary }: { summary: Record<string, number> }) {
  const entries = Object.entries(summary).filter(([, count]) => count > 0);
  if (entries.length === 0) return null;
  return (
    <section className="card">
      <h2 className="eyebrow">Normalization summary</h2>
      <div className={styles.summaryBadges}>
        {entries.map(([status, count]) => (
          <span key={status} className={styles.badgeItem}>
            <span className={styles.count}>{count}</span>{" "}
            {status.replace(/_/g, " ")}
          </span>
        ))}
      </div>
      <p className={styles.mappingNote}>
        Line items mapped to standard canonical accounting vocabulary for consistent financial ratio analysis. Unmapped labels are marked for review.
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
    <section className={`card ${styles.sectionCard}`}>
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
        <span className={styles.labelText}>{item.label}</span>
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
