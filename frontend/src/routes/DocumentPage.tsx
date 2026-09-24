import { Link, useParams } from "react-router-dom";
import { AskPanel } from "../components/ask/AskPanel";
import { CurrencyProvider } from "../components/common/CurrencyContext";
import { ErrorNotice } from "../components/common/ErrorNotice";
import { Skeleton } from "../components/common/Feedback";
import { DocumentHeader } from "../components/document/DocumentHeader";
import { OverviewPanel } from "../components/document/OverviewPanel";
import { StatementView } from "../components/document/StatementView";
import { RatioGrid } from "../components/ratios/RatioGrid";
import { useDocument } from "../state/useDocument";
import type { BalanceSheetDocument } from "../types/balanceSheet";
import styles from "./DocumentPage.module.css";
const TABS = [
  { key: "", label: "Overview" },
  { key: "statement", label: "Balance Sheet" },
  { key: "ratios", label: "Ratios" },
  { key: "ask", label: "Ask" },
] as const;
export default function DocumentPage() {
  const { documentId, tab = "" } = useParams();
  const { state, reload } = useDocument(documentId);
  if (state.kind === "loading" || state.kind === "idle") {
    return (
      <div className={styles.skeletons}>
        <Skeleton height="2.5rem" />
        <Skeleton height="1rem" width="60%" />
        <Skeleton height="12rem" />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <>
        <ErrorNotice
          error={state.error}
          title="Could not load this document"
          onRetry={reload}
        />
        <p className={styles.back}>
          <Link to="/">Back to upload</Link>
        </p>
      </>
    );
  }
  const document = state.document;
  const id = documentId ?? "";
  return (
    <>
      <DocumentHeader document={document} />
      <nav className={styles.tabs}>
        {TABS.map(({ key, label }) => {
          const to = key ? `/documents/${id}/${key}` : `/documents/${id}`;
          const blocked = isBlocked(document, key);
          if (blocked) {
            return (
              <span
                key={key}
                className={styles.tab}
                aria-disabled="true"
                title={blocked}
              >
                {label}
              </span>
            );
          }
          return (
            <Link
              key={key}
              to={to}
              className={styles.tab}
              aria-current={tab === key ? "page" : undefined}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      {}
      <CurrencyProvider document={document}>
        <div className={styles.panel}>
          <TabContent document={document} tab={tab} documentId={id} />
        </div>
      </CurrencyProvider>
    </>
  );
}
function isBlocked(
  document: BalanceSheetDocument,
  tab: string,
): string | null {
  if (tab === "") return null;
  if (document.status === "rejected") {
    return "This document was rejected during validation, so its figures are not shown.";
  }
  if (document.status === "failed") {
    return "Processing this document failed.";
  }
  if (!document.extracted) {
    return "This document has not been extracted.";
  }
  if (tab === "ratios" && !document.ratios) {
    return "No ratios were computed for this document.";
  }
  return null;
}
function TabContent({
  document,
  tab,
  documentId,
}: {
  document: BalanceSheetDocument;
  tab: string;
  documentId: string;
}) {
  const blocked = isBlocked(document, tab);
  if (blocked) {
    return (
      <div className={styles.blocked}>
        <p className={styles.blockedTitle}>Not available for this document</p>
        <p>{blocked}</p>
        <p>
          <Link to={`/documents/${documentId}`}>See the overview instead</Link>
        </p>
      </div>
    );
  }
  switch (tab) {
    case "statement":
      return <StatementView document={document} />;
    case "ratios":
      return <RatioGrid ratios={document.ratios ?? null} />;
    case "ask":
      return <AskPanel documentId={documentId} />;
    default:
      return <OverviewPanel document={document} />;
  }
}
