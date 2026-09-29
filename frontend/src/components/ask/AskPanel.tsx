import type { ReactElement } from "react";
import type { BalanceSheetDocument } from "../../types/balanceSheet";
import { useConversation } from "../../state/useConversation";
import { useCurrency } from "../common/CurrencyContext";
import { MoneyValue, RatioValue } from "../common/Figures";
import { ErrorNotice } from "../common/ErrorNotice";
import { EmptyState, Spinner } from "../common/Feedback";
import { AnswerCard } from "./AnswerCard";
import { QuestionInput } from "./QuestionInput";
import styles from "./Ask.module.css";

export function AskPanel({
  documentId,
  document,
}: {
  documentId: string;
  document: BalanceSheetDocument;
}): ReactElement {
  const { exchanges, pending, error, ask } = useConversation(documentId);
  return (
    <div className={styles.askLayout}>
      {}
      <div className={styles.conversationArea}>
        <div className={styles.panel}>
          {exchanges.length === 0 && !pending && (
            <EmptyState title="Ask about this Balance Sheet">
              <p>
                Answers come from the figures already computed and from the
                document's own text. The model explains them; it never calculates,
                and every figure in a reply is checked against its source first.
              </p>
            </EmptyState>
          )}
          <div className={styles.thread}>
            {exchanges.map((exchange, index) => (
              <div key={`${exchange.question}-${index}`}>
                <p className={styles.question}>
                  <span className={styles.questionMark}>Q</span>
                  <span className={styles.questionText}>{exchange.question}</span>
                </p>
                <AnswerCard answer={exchange.answer} />
              </div>
            ))}
            {pending && (
              <div>
                <p className={styles.question}>
                  <span className={styles.questionMark}>Q</span>
                  <span className={styles.questionText}>{pending}</span>
                </p>
                <p className={styles.pending}>
                  <Spinner label="Thinking" />
                  Retrieving and answering — the local model takes a few seconds.
                </p>
              </div>
            )}
          </div>
          {error !== null && (
            <ErrorNotice error={error} title="That question could not be sent" />
          )}
          <QuestionInput onAsk={ask} busy={pending !== null} />
        </div>
      </div>

      <aside className={styles.snapshotPanel}>
        <DocumentSnapshot document={document} />
      </aside>
    </div>
  );
}

function DocumentSnapshot({ document }: { document: BalanceSheetDocument }): ReactElement {
  const { code: currency } = useCurrency();
  const check = document.equation_check;
  const ratios = document.ratios;
  const period =
    document.extracted?.period_label ??
    document.period?.selected.label ??
    document.extracted?.period_end_date;
  const chunks = document.chunk_index?.chunk_count;

  const byName = new Map(ratios?.ratios.map((r) => [r.name, r]) ?? []);
  const kpis = [
    { label: "Total Assets",       val: check?.total_assets },
    { label: "Total Liabilities",  val: check?.total_liabilities },
    { label: "Total Equity",       val: check?.total_equity },
  ].filter((k) => k.val !== undefined);

  const ratioKpis = [
    { label: "Current Ratio",   r: byName.get("current_ratio"),   ratio: true },
    { label: "Quick Ratio",     r: byName.get("quick_ratio"),      ratio: true },
    { label: "Working Capital", r: byName.get("working_capital"),  ratio: false },
    { label: "Debt/Equity",     r: byName.get("debt_to_equity"),   ratio: true },
  ].filter((k) => k.r && k.r.status !== "unavailable");

  return (
    <div className={styles.snapshot}>
      <h2 className={styles.snapshotTitle}>Document Snapshot</h2>

      <div className={styles.snapshotMeta}>
        {period && (
          <div className={styles.snapshotRow}>
            <span className={styles.snapshotLabel}>Period</span>
            <span className={styles.snapshotValue}>{period}</span>
          </div>
        )}
        {currency && (
          <div className={styles.snapshotRow}>
            <span className={styles.snapshotLabel}>Currency</span>
            <span className={styles.snapshotValue}>{currency}</span>
          </div>
        )}
        {ratios?.scale_label && (
          <div className={styles.snapshotRow}>
            <span className={styles.snapshotLabel}>Scale</span>
            <span className={styles.snapshotValue}>{ratios.scale_label}</span>
          </div>
        )}
      </div>

      {kpis.length > 0 && (
        <div className={styles.snapshotSection}>
          <span className={styles.snapshotEyebrow}>Balance Sheet</span>
          {kpis.map((kpi) => (
            <div key={kpi.label} className={styles.snapshotRow}>
              <span className={styles.snapshotLabel}>{kpi.label}</span>
              <span className={styles.snapshotFigure}>
                <MoneyValue value={kpi.val} />
              </span>
            </div>
          ))}
        </div>
      )}

      {ratioKpis.length > 0 && (
        <div className={styles.snapshotSection}>
          <span className={styles.snapshotEyebrow}>Key Ratios</span>
          {ratioKpis.map((kpi) => (
            <div key={kpi.label} className={styles.snapshotRow}>
              <span className={styles.snapshotLabel}>{kpi.label}</span>
              <span className={styles.snapshotFigure}>
                {kpi.ratio
                  ? <RatioValue value={kpi.r!.value} />
                  : <MoneyValue value={kpi.r!.value} />}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className={styles.snapshotSection}>
        <span className={styles.snapshotEyebrow}>Analysis</span>
        <div className={styles.snapshotRow}>
          <span className={styles.snapshotLabel}>Ratios computed</span>
          <span className={styles.snapshotValue}>{ratios ? ratios.ratios.filter(r => r.status !== "unavailable").length : 0}</span>
        </div>
        {chunks !== undefined && (
          <div className={styles.snapshotRow}>
            <span className={styles.snapshotLabel}>Indexed chunks</span>
            <span className={styles.snapshotValue}>{chunks}</span>
          </div>
        )}
        <div className={styles.snapshotRow}>
          <span className={styles.snapshotLabel}>Equation</span>
          <span
            className={styles.snapshotValue}
            data-ok={check?.balanced === true ? "true" : check?.balanced === false ? "false" : undefined}
          >
            {check?.balanced ? "Balances ✓" : check ? "Does not balance" : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
