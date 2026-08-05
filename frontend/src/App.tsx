import { useEffect, useMemo, useRef, useState } from 'react'
import { ListingModal } from './components/ListingModal'
import { MapView } from './components/MapView'
import { Sidebar } from './components/Sidebar'
import { type GeolocationStatus, useGeolocation } from './hooks/useGeolocation'
import { useListings } from './hooks/useListings'
import {
  EMPTY_FILTER_DRAFT,
  type FilterDraft,
  type FlyToRequest,
  type GeoPoint,
  type Listing,
  type ListingFilters,
} from './types/listing'

// Downtown Boston — fallback center if geolocation is denied/unavailable.
const DEFAULT_CENTER: GeoPoint = { latitude: 42.3398, longitude: -71.0827 }

// Default "nearby" radius applied once we have a real (geolocated or searched) center.
const DEFAULT_RADIUS_KM = '5'

function geolocationErrorMessage(status: GeolocationStatus): string | null {
  switch (status) {
    case 'denied':
      return "Location access denied. Allow it in your browser's site settings, or search a location below."
    case 'unavailable':
      // The most common real-world cause: the browser-level prompt was granted,
      // but the OS itself is blocking location for that browser (very common on
      // macOS — System Settings > Privacy & Security > Location Services).
      return "Couldn't determine your location. Check that Location Services is enabled for your browser in your OS settings, or search a location below."
    case 'timeout':
      return 'Location request timed out. Try again, or search a location below.'
    case 'unsupported':
      return "Your browser doesn't support location detection. Search a location below."
    default:
      return null
  }
}

function draftToFilters(draft: FilterDraft): ListingFilters {
  const filters: ListingFilters = {}

  const budgetMax = Number(draft.budgetMax)
  if (draft.budgetMax !== '' && !Number.isNaN(budgetMax)) filters.budgetMax = budgetMax

  const minBeds = Number(draft.minBeds)
  if (draft.minBeds !== '' && !Number.isNaN(minBeds)) filters.minBeds = minBeds

  const minBathrooms = Number(draft.minBathrooms)
  if (draft.minBathrooms !== '' && !Number.isNaN(minBathrooms)) {
    filters.minBathrooms = minBathrooms
  }

  const radiusKm = Number(draft.radiusKm)
  if (draft.radiusKm !== '' && !Number.isNaN(radiusKm) && radiusKm > 0) {
    filters.radiusKm = radiusKm
  }

  return filters
}

function App() {
  const [filterDraft, setFilterDraft] = useState<FilterDraft>(EMPTY_FILTER_DRAFT)
  const [mapCenter, setMapCenter] = useState<GeoPoint>(DEFAULT_CENTER)
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [flyToRequest, setFlyToRequest] = useState<FlyToRequest | null>(null)
  const [locationLabel, setLocationLabel] = useState<string | null>(null)

  // Resolve the user's live location once on load, then use it as the
  // starting center (and default search radius) instead of DEFAULT_CENTER.
  const geolocation = useGeolocation()
  const [locationReady, setLocationReady] = useState(false)
  const hasGatedInitialRender = useRef(false)

  // Gates the initial map mount exactly once (on the first loading -> settled
  // transition), so a later retry doesn't hide the already-visible map again.
  useEffect(() => {
    if (geolocation.status === 'loading' || hasGatedInitialRender.current) return
    hasGatedInitialRender.current = true
    setLocationReady(true)
  }, [geolocation.status])

  // Applies a resolved position to the map center every time one comes in —
  // including from a manual retry, not just the initial attempt.
  useEffect(() => {
    if (geolocation.status !== 'resolved' || !geolocation.center) return
    setMapCenter(geolocation.center)
    setLocationLabel('your location')
    setFilterDraft((prev) => (prev.radiusKm === '' ? { ...prev, radiusKm: DEFAULT_RADIUS_KM } : prev))
  }, [geolocation.status, geolocation.center])

  const filters = useMemo(() => draftToFilters(filterDraft), [filterDraft])
  const { listings, isLoading, error } = useListings(filters, mapCenter)

  const handleLocationFound = (center: GeoPoint, label: string) => {
    setFlyToRequest({ center, requestId: Date.now() })
    setLocationLabel(label)
    setFilterDraft((prev) => (prev.radiusKm === '' ? { ...prev, radiusKm: DEFAULT_RADIUS_KM } : prev))
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        draft={filterDraft}
        onDraftChange={setFilterDraft}
        listings={listings}
        isLoading={isLoading}
        error={error}
        onSelectListing={setSelectedListing}
        currentCenter={mapCenter}
        locationLabel={locationLabel}
        onLocationFound={handleLocationFound}
        geolocationError={geolocationErrorMessage(geolocation.status)}
        onRetryGeolocation={geolocation.retry}
      />
      <main className="relative flex-1">
        {locationReady ? (
          <MapView
            listings={listings}
            initialCenter={mapCenter}
            flyToRequest={flyToRequest}
            onCenterChange={setMapCenter}
            onSelectListing={setSelectedListing}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-slate-100 text-slate-500">
            Finding your location…
          </div>
        )}
      </main>
      <ListingModal listing={selectedListing} onClose={() => setSelectedListing(null)} />
    </div>
  )
}

export default App
