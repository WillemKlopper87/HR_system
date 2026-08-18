/** Rand formatting shared by the compensation pages (H2 dedupe). */
export function formatZAR(value: string | number): string {
  return `R ${Number(value).toLocaleString()}`
}
