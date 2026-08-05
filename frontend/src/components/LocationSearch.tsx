import { useState } from 'react'
import { GeocodingError, geocodeLocation } from '../api/geocoding'
import type { GeoPoint } from '../types/listing'

interface LocationSearchProps {
  currentCenter: GeoPoint
  onLocationFound: (center: GeoPoint, label: string) => void
}

export function LocationSearch({ currentCenter, onLocationFound }: LocationSearchProps) {
  const [query, setQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return

    setIsSearching(true)
    setError(null)

    try {
      const result = await geocodeLocation(trimmed, currentCenter)
      if (!result) {
        setError(`No location found for "${trimmed}"`)
        return
      }
      onLocationFound(result.center, result.placeName)
    } catch (err) {
      setError(err instanceof GeocodingError ? err.message : 'Search failed')
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-1">
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search a city, address, or zip…"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
        />
        <button
          type="submit"
          disabled={isSearching || !query.trim()}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSearching ? '…' : 'Go'}
        </button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  )
}
