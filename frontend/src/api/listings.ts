import { filterMockListings } from '../mocks/listings'
import type { GeoPoint, Listing, ListingFilters } from '../types/listing'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const USE_MOCK_LISTINGS = import.meta.env.VITE_USE_MOCK_LISTINGS === 'true'
const MOCK_LATENCY_MS = 150

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

export async function fetchListings(
  filters: ListingFilters,
  center: GeoPoint,
  signal?: AbortSignal,
): Promise<Listing[]> {
  if (USE_MOCK_LISTINGS) {
    // Simulated latency keeps loading states honest during UI-only iteration.
    await delay(MOCK_LATENCY_MS, signal)
    return filterMockListings(filters, center)
  }

  const params = new URLSearchParams()

  if (filters.budgetMax !== undefined) {
    params.set('budget_max', String(filters.budgetMax))
  }
  if (filters.minBeds !== undefined) {
    params.set('min_beds', String(filters.minBeds))
  }
  if (filters.minBathrooms !== undefined) {
    params.set('min_bathrooms', String(filters.minBathrooms))
  }
  if (filters.radiusKm !== undefined) {
    params.set('radius_km', String(filters.radiusKm))
    params.set('latitude', String(center.latitude))
    params.set('longitude', String(center.longitude))
  }

  const response = await fetch(`${API_BASE_URL}/api/listings/?${params.toString()}`, { signal })

  if (!response.ok) {
    throw new ApiError(`Failed to fetch listings (${response.status})`, response.status)
  }

  return (await response.json()) as Listing[]
}
