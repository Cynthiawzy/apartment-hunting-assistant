import { useEffect, useState } from 'react'
import { ApiError, fetchListings } from '../api/listings'
import type { GeoPoint, Listing, ListingFilters } from '../types/listing'
import { useDebouncedValue } from './useDebouncedValue'

interface UseListingsResult {
  listings: Listing[]
  isLoading: boolean
  error: string | null
}

export function useListings(filters: ListingFilters, center: GeoPoint): UseListingsResult {
  const debouncedFilters = useDebouncedValue(filters, 400)

  const [listings, setListings] = useState<Listing[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setIsLoading(true)
    setError(null)

    fetchListings(debouncedFilters, center, controller.signal)
      .then((data) => {
        setListings(data)
        setIsLoading(false)
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(err instanceof ApiError ? err.message : 'Failed to load listings')
        setIsLoading(false)
      })

    return () => controller.abort()
  }, [debouncedFilters, center])

  return { listings, isLoading, error }
}
