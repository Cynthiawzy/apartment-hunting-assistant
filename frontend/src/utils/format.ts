export function formatPrice(price: number): string {
  return price.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export function formatBedsBaths(bedrooms: number, bathrooms: number): string {
  const beds = bedrooms === 0 ? 'Studio' : `${bedrooms} bd`
  return `${beds} · ${bathrooms} ba`
}

export function formatDistance(distanceKm: number): string {
  return `${distanceKm.toFixed(1)} km away`
}
