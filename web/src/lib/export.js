// Shortlist export: spreadsheet (CSV, opens in Excel or Google Sheets) or PDF for the coaching staff.

const stamp = () => new Date().toLocaleDateString('en-CA')   // yyyy-mm-dd in the user's own time zone

function download(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function exportCsv(rows, columns, title) {
  const esc = (v) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [columns.map((c) => esc(c.label)).join(',')]
  for (const r of rows) lines.push(columns.map((c) => esc(c.value(r))).join(','))
  // Byte order mark so Excel reads accented names correctly.
  download(new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' }), `${slug(title)}-${stamp()}.csv`)
}

export async function exportPdf(rows, columns, title, subtitle) {
  const [{ jsPDF }, { default: autoTable }] = await Promise.all([import('jspdf'), import('jspdf-autotable')])
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' })
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(15)
  doc.text(title, 36, 40)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(90)
  doc.text(`${subtitle}   Exported ${stamp()}   ${rows.length} players`, 36, 56)
  autoTable(doc, {
    startY: 68,
    head: [columns.map((c) => c.label)],
    body: rows.map((r) => columns.map((c) => String(c.value(r) ?? ''))),
    styles: { fontSize: columns.length > 22 ? 6 : 7.5, cellPadding: 2.5, overflow: 'linebreak' },
    headStyles: { fillColor: [28, 43, 36], textColor: 255, fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [244, 247, 244] },
    margin: { left: 36, right: 36 },
  })
  doc.save(`${slug(title)}-${stamp()}.pdf`)
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
