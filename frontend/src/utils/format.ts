export function formatPrice(price: number): string {
  return price.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export function formatBedsBaths(bedrooms: number, bathrooms: number | null): string {
  const beds = bedrooms === 0 ? 'Studio' : `${bedrooms} bd`
  if (bathrooms === null) return beds
  return `${beds} · ${bathrooms} ba`
}

export function formatDistance(distanceKm: number): string {
  return `${distanceKm.toFixed(1)} km away`
}

/** Scraped descriptions carry the source page's own line breaks (real
 * paragraphs/bullet sections), but 3+ in a row (common when a scraper joins
 * a title and body separately) reads as an oversized gap once rendered with
 * `whitespace-pre-line` — collapse those down to a single paragraph break. */
export function formatDescription(description: string): string {
  return description.trim().replace(/\n{3,}/g, '\n\n')
}
