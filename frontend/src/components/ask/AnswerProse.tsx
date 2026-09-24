import type { ReactElement } from "react";
import { parseBlocks, type Span } from "../../lib/markdown";
import { regroupFigures, type Grouping } from "../../lib/money";
import { useCurrency } from "../common/CurrencyContext";
import styles from "./Ask.module.css";
export function AnswerProse({ text }: { text: string }): ReactElement {
  const { grouping } = useCurrency();
  const blocks = parseBlocks(text);
  return (
    <div className={styles.prose}>
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          const Tag = block.level === 3 ? "h5" : "h4";
          return (
            <Tag key={index} className={styles.proseHeading}>
              <Spans spans={block.spans} grouping={grouping} />
            </Tag>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={index} className={styles.proseList}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <Spans spans={item} grouping={grouping} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className={styles.proseParagraph}>
            <Spans spans={block.spans} grouping={grouping} />
          </p>
        );
      })}
    </div>
  );
}
function Spans({
  spans,
  grouping,
}: {
  spans: Span[];
  grouping: Grouping;
}): ReactElement {
  return (
    <>
      {spans.map((span, index) => {
        const text = regroupFigures(span.text, grouping);
        return span.bold ? <strong key={index}>{text}</strong> : <span key={index}>{text}</span>;
      })}
    </>
  );
}
