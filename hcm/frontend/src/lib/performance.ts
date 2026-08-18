import type { AgreementElement } from '../api/types'

/** Group a scorecard's KPIs under their Objective heading, in workbook order —
 * the shape the printed scorecard uses, so the table can span the objective
 * cell down its rows. */
export function groupBySection(elements: AgreementElement[]): [string, AgreementElement[]][] {
  const map = new Map<string, AgreementElement[]>()
  for (const element of [...elements].sort((a, b) => a.section_order - b.section_order || a.order - b.order)) {
    const list = map.get(element.section_title) ?? []
    list.push(element)
    map.set(element.section_title, list)
  }
  return [...map.entries()]
}
