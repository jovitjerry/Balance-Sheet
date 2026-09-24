import { useState, type FormEvent, type ReactElement } from "react";
import { MAX_QUESTION_CHARS } from "../../api/insights";
import styles from "./Ask.module.css";
interface QuestionInputProps {
  onAsk: (question: string) => void;
  busy: boolean;
}
export function QuestionInput({
  onAsk,
  busy,
}: QuestionInputProps): ReactElement {
  const [value, setValue] = useState("");
  const tooLong = value.length > MAX_QUESTION_CHARS;
  const canSubmit = value.trim().length > 0 && !tooLong && !busy;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    onAsk(value);
    setValue("");
  }
  return (
    <form className={styles.form} onSubmit={submit}>
      <label htmlFor="question" className="visually-hidden">
        Ask a question about this Balance Sheet
      </label>
      <textarea
        id="question"
        className={styles.textarea}
        value={value}
        placeholder="Ask about the figures, the ratios, or what the document says…"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (canSubmit) submit(event);
          }
        }}
      />
      <div className={styles.formFoot}>
        <button type="submit" className="button" disabled={!canSubmit}>
          Ask
        </button>
        <span className={styles.counter} data-over={tooLong || undefined}>
          {value.length} / {MAX_QUESTION_CHARS}
        </span>
      </div>
    </form>
  );
}
