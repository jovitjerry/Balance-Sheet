export interface Span {
  text: string;
  bold: boolean;
}
export type Block =
  | { kind: "heading"; level: 2 | 3; spans: Span[] }
  | { kind: "paragraph"; spans: Span[] }
  | { kind: "list"; items: Span[][] };
const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const BOLD = /\*\*(.+?)\*\*/g;
export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = (text ?? "").replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let items: Span[][] = [];
  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push({ kind: "paragraph", spans: parseSpans(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (items.length === 0) return;
    blocks.push({ kind: "list", items });
    items = [];
  };
  for (const line of lines) {
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = (heading[1] ?? "").length >= 3 ? 3 : 2;
      blocks.push({
        kind: "heading",
        level,
        spans: parseSpans(heading[2] ?? ""),
      });
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      flushParagraph();
      items.push(parseSpans(bullet[1] ?? ""));
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}
function parseSpans(text: string): Span[] {
  const spans: Span[] = [];
  let last = 0;
  BOLD.lastIndex = 0;
  let match = BOLD.exec(text);
  while (match !== null) {
    if (match.index > last) {
      spans.push({ text: text.slice(last, match.index), bold: false });
    }
    spans.push({ text: match[1] ?? "", bold: true });
    last = match.index + match[0].length;
    match = BOLD.exec(text);
  }
  if (last < text.length) spans.push({ text: text.slice(last), bold: false });
  return spans.length > 0 ? spans : [{ text, bold: false }];
}
