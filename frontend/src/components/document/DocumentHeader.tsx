/**
 * Who the document is about, for which period, and in what units.
 *
 * The scale note is prominent for a reason: Modules 1-3 record "in thousands"
 * and deliberately do **not** apply it, so the figures below are exactly as
 * printed. A reader who missed that would be out by a factor of a thousand.
 */

import type { ReactElement } from "react";
import type { BalanceSheetDocument } from "../../types/balanceSheet";
import {
  DOCUMENT_STATUS_LABEL,
  documentStatusTone,
  StatusPill,
} from "../common/StatusPill";
import styles from "./DocumentHeader.module.css";

export function DocumentHeader({
  document,
}: {
  document: BalanceSheetDocument;
}): ReactElement {
  const extracted = document.extracted;
  const currency = extracted?.currency ?? document.units?.currency;
  const scale = document.ratios?.scale_label ?? document.units?.scale_label;
  const period =
    extracted?.period_label ??
    document.period?.selected.label ??
    extracted?.period_end_date;

  // With no entity name the filename becomes the heading, and repeating it as
  // a "File" fact directly underneath says the same thing twice.
  const title = extracted?.entity_name || document.source.filename;
  const showFilename = title !== document.source.filename;

  return (
    <header className={styles.header}>
      <div className={styles.titleRow}>
        <h1 className={styles.entity}>{title}</h1>
        <StatusPill tone={documentStatusTone(document.status)}>
          {DOCUMENT_STATUS_LABEL[document.status]}
        </StatusPill>
      </div>

      <p className={styles.facts}>
        {period && <Fact label="Period" value={period} />}
        {currency && <Fact label="Currency" value={currency} />}
        {showFilename && <Fact label="File" value={document.source.filename} />}
        {scale && (
          <span className={`${styles.fact} ${styles.scaleNote}`}>
            Printed {scale} — figures are shown exactly as printed, unscaled
          </span>
        )}
      </p>
    </header>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <span className={styles.fact}>
      <span className={styles.factLabel}>{label}</span>
      <span className={styles.factValue}>{value}</span>
    </span>
  );
}
