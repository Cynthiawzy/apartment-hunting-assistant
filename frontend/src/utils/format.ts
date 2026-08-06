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
