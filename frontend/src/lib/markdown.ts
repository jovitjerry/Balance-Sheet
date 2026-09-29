export interface Span {
  text: string;
  bold: boolean;
  code: boolean;
}

export type Block =
  | { kind: "heading"; level: 2 | 3; spans: Span[] }
  | { kind: "paragraph"; spans: Span[] }
  | { kind: "list"; ordered: boolean; items: Span[][] }
  | { kind: "table"; headers: Span[][]; rows: Span[][][] };

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;
const TABLE_ROW = /^\s*\|(.+)\|\s*$/;
const TABLE_SEPARATOR = /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/;

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = (text ?? "").replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let items: Span[][] = [];
  let ordered = false;
  let rawTableRows: string[][] = [];
  let hasSeparator = false;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push({ kind: "paragraph", spans: parseSpans(paragraph.join(" ")) });
    paragraph = [];
  };

  const flushList = () => {
    if (items.length === 0) return;
    blocks.push({ kind: "list", ordered, items });
    items = [];
    ordered = false;
  };

  const flushTable = () => {
    if (rawTableRows.length === 0) return;
    let headers: Span[][] = [];
    let rows: Span[][][] = [];
    const firstRow = rawTableRows[0] ?? [];
    if (hasSeparator && rawTableRows.length >= 1) {
      headers = firstRow.map(cell => parseSpans(cell));
      rows = rawTableRows.slice(1).map(row => row.map(cell => parseSpans(cell)));
    } else if (rawTableRows.length > 1) {
      headers = firstRow.map(cell => parseSpans(cell));
      rows = rawTableRows.slice(1).map(row => row.map(cell => parseSpans(cell)));
    } else {
      rows = rawTableRows.map(row => row.map(cell => parseSpans(cell)));
    }
    blocks.push({ kind: "table", headers, rows });
    rawTableRows = [];
    hasSeparator = false;
  };

  for (const line of lines) {
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      flushTable();
      continue;
    }

    if (TABLE_SEPARATOR.test(line)) {
      hasSeparator = true;
      continue;
    }

    const tableMatch = TABLE_ROW.exec(line);
    if (tableMatch) {
      flushParagraph();
      flushList();
      const content = tableMatch[1] ?? "";
      const cells = content.split("|").map(cell => cell.trim());
      rawTableRows.push(cells);
      continue;
    }

    flushTable();

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
      if (items.length > 0 && ordered) flushList();
      ordered = false;
      items.push(parseSpans(bullet[1] ?? ""));
      continue;
    }

    const orderedItem = ORDERED.exec(line);
    if (orderedItem) {
      flushParagraph();
      if (items.length > 0 && !ordered) flushList();
      ordered = true;
      items.push(parseSpans(orderedItem[1] ?? ""));
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  flushTable();
  return blocks;
}

function parseSpans(text: string): Span[] {

  const spans: Span[] = [];

  const TOKENS = /\*\*(.+?)\*\*|`([^`]+)`/g;
  TOKENS.lastIndex = 0;
  let last = 0;
  let match = TOKENS.exec(text);

  while (match !== null) {
    if (match.index > last) {
      spans.push({ text: text.slice(last, match.index), bold: false, code: false });
    }
    if (match[1] !== undefined) {
      spans.push({ text: match[1], bold: true, code: false });
    } else if (match[2] !== undefined) {
      spans.push({ text: match[2], bold: false, code: true });
    }
    last = match.index + match[0].length;
    match = TOKENS.exec(text);
  }

  if (last < text.length) {
    spans.push({ text: text.slice(last), bold: false, code: false });
  }

  return spans.length > 0 ? spans : [{ text, bold: false, code: false }];
}
