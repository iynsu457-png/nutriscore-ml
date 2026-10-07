// Build Word (.docx) manuscripts from markdown with the journal house style
// (three-line tables; title 14pt, body 11pt, captions and tables 10pt).
// Usage: node scripts/build_docx.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, BorderStyle, WidthType, VerticalAlign, Footer, PageNumber,
  LineNumberRestartFormat,
} = require("docx");

const LINE = { style: BorderStyle.SINGLE, size: 8, color: "000000" }; // 1.0 pt
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const CONTENT_W = 9360; // US Letter, 1" margins (DXA)
const NOSP = { before: 0, after: 0 };

function makeRuns(text, font, size, bold = false) {
  const runs = [];
  for (const part of text.split(/(<sup>.*?<\/sup>)/g)) {
    if (!part) continue;
    const m = part.match(/^<sup>(.*?)<\/sup>$/);
    if (m) runs.push(new TextRun({ text: m[1], superScript: true, font, size, bold }));
    else runs.push(new TextRun({ text: part, font, size, bold }));
  }
  return runs;
}

function jpegSize(buf) {
  let i = 2;
  while (i < buf.length - 8) {
    if (buf[i] !== 0xff) { i++; continue; }
    const m = buf[i + 1];
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
      return { height: buf.readUInt16BE(i + 5), width: buf.readUInt16BE(i + 7) };
    }
    i += 2 + buf.readUInt16BE(i + 2);
  }
  return { width: 1000, height: 600 };
}

function parse(md) {
  const lines = md.replace(/<!--[\s\S]*?-->/g, "").split("\n");
  const blocks = [];
  let i = 0, titleSeen = false, h2seen = false;
  while (i < lines.length) {
    const t = lines[i].trim();
    if (t === "") { i++; continue; }
    if (t.startsWith("# ")) { blocks.push({ type: "title", text: t.slice(2).trim() }); titleSeen = true; i++; continue; }
    if (t.startsWith("### ")) { blocks.push({ type: "h3", text: t.slice(4).trim() }); i++; continue; }
    if (t.startsWith("## ")) { blocks.push({ type: "h2", text: t.slice(3).trim() }); h2seen = true; i++; continue; }
    const mImg = t.match(/^!\[[^\]]*\]\(([^)]+)\)$/);
    if (mImg) { blocks.push({ type: "image", path: mImg[1] }); i++; continue; }
    if (t.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) { rows.push(lines[i].trim()); i++; }
      blocks.push({ type: "table", rows }); continue;
    }
    const mFoot = t.match(/^<sup>([a-z])<\/sup>(.*)$/);
    if (mFoot) { blocks.push({ type: "footnote", marker: mFoot[1], rest: mFoot[2].trim() }); i++; continue; }
    if (h2seen && /^(Abbreviations:|Note[.:]|Values are |Percentages are |The FVL-sensitive|FVL-민감|백분율)/.test(t)) {
      blocks.push({ type: "footnote", marker: "", rest: t }); i++; continue;
    }
    const mCap = t.match(/^\*\*((?:TABLE|FIGURE|Table|Figure|표|그림)\s*[A-Za-z]?[0-9]+\.?)\*\*\s*(.*)$/);
    if (mCap) { blocks.push({ type: "caption", label: mCap[1].trim(), rest: mCap[2] }); i++; continue; }
    const mLab = t.match(/^\*\*([^*]+:)\*\*\s*(.*)$/);
    if (mLab) { blocks.push({ type: "label", label: mLab[1], rest: mLab[2] }); i++; continue; }
    const mRefB = t.match(/^\[(\d+)\]\s+(.*)$/);
    if (mRefB) { blocks.push({ type: "ref", num: mRefB[1], text: mRefB[2], bracket: true }); i++; continue; }
    const mRef = t.match(/^(\d+)\.\s+(.*)$/);
    if (mRef) { blocks.push({ type: "ref", num: mRef[1], text: mRef[2] }); i++; continue; }
    if (titleSeen && !h2seen) { blocks.push({ type: "front", text: t }); i++; continue; }
    blocks.push({ type: "body", text: t }); i++;
  }
  return blocks;
}

const splitRow = (line) => line.split("|").slice(1, -1).map((s) => s.trim());

function colWidths(n) {
  const first = Math.round(CONTENT_W * 0.32);
  const rest = Math.floor((CONTENT_W - first) / (n - 1));
  const w = [first];
  for (let k = 1; k < n - 1; k++) w.push(rest);
  w.push(CONTENT_W - first - rest * (n - 2));
  return w;
}

function makeTable(rows, font) {
  const header = splitRow(rows[0]);
  const data = rows.slice(2).map(splitRow);
  const n = header.length;
  const widths = colWidths(n);
  const cell = (text, w, bold, borders) =>
    new TableCell({
      width: { size: w, type: WidthType.DXA }, borders,
      margins: { top: 40, bottom: 40, left: 100, right: 100 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ spacing: NOSP, children: [new TextRun({ text, bold, font, size: 20 })] })],
    });
  const hb = { top: LINE, bottom: LINE, left: NONE, right: NONE };
  const trs = [new TableRow({ tableHeader: true, children: header.map((h, c) => cell(h, widths[c], true, hb)) })];
  data.forEach((r, ri) => {
    const last = ri === data.length - 1;
    const b = { top: NONE, bottom: last ? LINE : NONE, left: NONE, right: NONE };
    trs.push(new TableRow({ children: r.map((v, c) => cell(v, widths[c], false, b)) }));
  });
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: trs });
}

function buildDoc(blocks, font, indentFirst, mediaDir) {
  const children = [];
  for (const b of blocks) {
    if (b.type === "title") {
      children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: NOSP,
        children: [new TextRun({ text: b.text, bold: true, font, size: 28 })] }));
    } else if (b.type === "h2") {
      children.push(new Paragraph({ spacing: NOSP, children: [new TextRun({ text: b.text, bold: true, font, size: 26 })] }));
    } else if (b.type === "h3") {
      children.push(new Paragraph({ spacing: NOSP, children: [new TextRun({ text: b.text, bold: true, font, size: 22 })] }));
    } else if (b.type === "front") {
      const mAbbr = b.text.match(/^(Abbreviations:)(.*)$/);
      if (mAbbr) {
        children.push(new Paragraph({ spacing: NOSP, children: [
          new TextRun({ text: "Abbreviations:", italics: true, font, size: 22 }),
          new TextRun({ text: mAbbr[2], font, size: 22 }) ] }));
      } else {
        children.push(new Paragraph({ spacing: NOSP, children: makeRuns(b.text, font, 22) }));
      }
    } else if (b.type === "label") {
      // CDN: "Keywords:" label is italic; other run-in labels (abstract) are bold
      const isKw = /Keywords/i.test(b.label);
      children.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { ...NOSP, line: 480 },
        children: [new TextRun({ text: b.label + " ", bold: !isKw, italics: isKw, font, size: 22 }), new TextRun({ text: b.rest, font, size: 22 })] }));
    } else if (b.type === "caption") {
      children.push(new Paragraph({ spacing: { before: 60, after: 40 },
        children: [new TextRun({ text: b.label + " ", bold: true, font, size: 20 }), new TextRun({ text: b.rest, font, size: 20 })] }));
    } else if (b.type === "table") {
      children.push(makeTable(b.rows, font));
    } else if (b.type === "image") {
      const abs = path.join(mediaDir, b.path);
      const data = fs.readFileSync(abs);
      const d = jpegSize(data);
      const wPx = 540, hPx = Math.round(wPx * d.height / d.width);
      children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
        children: [new ImageRun({ type: "jpg", data, transformation: { width: wPx, height: hPx },
          altText: { title: "Figure", description: b.path, name: b.path } })] }));
    } else if (b.type === "footnote") {
      const fnRuns = [];
      if (b.marker) fnRuns.push(new TextRun({ text: b.marker, superScript: true, font, size: 20 }));
      fnRuns.push(new TextRun({ text: b.rest, font, size: 20 }));
      children.push(new Paragraph({ spacing: { before: 20, after: 100 }, children: fnRuns }));
    } else if (b.type === "ref") {
      const refText = b.bracket ? `[${b.num}] ${b.text}` : `${b.num}. ${b.text}`;
      children.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { ...NOSP, line: 480 }, indent: { left: 480, hanging: 480 },
        children: [new TextRun({ text: refText, font, size: 20 })] }));
    } else {
      children.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { ...NOSP, line: 480 }, indent: { firstLineChars: 100 },
        children: [new TextRun({ text: b.text, font, size: 22 })] }));
    }
  }
  return new Document({
    // keep Latin words whole (no mid-word breaks in the Korean layout)
    styles: { default: { document: { run: { font, size: 22 }, paragraph: { wordWrap: true } } } },
    sections: [{
      properties: {
        page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
      },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font, size: 18 })] })] }) },
      children,
    }],
  });
}

async function build(srcMd, outDocx, font, indentFirst) {
  const blocks = parse(fs.readFileSync(srcMd, "utf8"));
  const doc = buildDoc(blocks, font, indentFirst, path.dirname(srcMd));
  fs.writeFileSync(outDocx, await Packer.toBuffer(doc));
  console.log(`[written] ${outDocx}  (${blocks.length} blocks)`);
}

(async () => {
  const M = path.join(__dirname, "..", "manuscript");
  await build(path.join(M, "MANUSCRIPT.md"), path.join(M, "MANUSCRIPT.docx"), "Times New Roman", 200);
  await build(path.join(M, "MANUSCRIPT_KO.md"), path.join(M, "MANUSCRIPT_KO.docx"), "Malgun Gothic", 220);
  await build(path.join(M, "Supplementary_Methods.md"), path.join(M, "Supplementary_Methods.docx"), "Times New Roman", 200);
})();
