import { EMPTY_FILTER_DRAFT, type FilterDraft, type GeoPoint, type Listing } from '../types/listing'
import { ListingCard } from './ListingCard'
import { LocationSearch } from './LocationSearch'

interface SidebarProps {
  draft: FilterDraft
  onDraftChange: (draft: FilterDraft) => void
  listings: Listing[]
  isLoading: boolean
  error: string | null
  onSelectListing: (listing: Listing) => void
  currentCenter: GeoPoint
  locationLabel: string | null
  onLocationFound: (center: GeoPoint, label: string) => void
  geolocationError: string | null
  onRetryGeolocation: () => void
}

export function Sidebar({
  draft,
  onDraftChange,
  listings,
  isLoading,
  error,
  onSelectListing,
  currentCenter,
  locationLabel,
  onLocationFound,
  geolocationError,
  onRetryGeolocation,
}: SidebarProps) {
  const setField = (field: keyof FilterDraft, value: string) => {
    onDraftChange({ ...draft, [field]: value })
  }

  return (
    <aside className="flex h-full w-96 max-w-full flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-4">
        <h1 className="text-lg font-semibold text-slate-900">Apartment Hunting AI Agent</h1>

        <div className="mt-3">
          <LocationSearch currentCenter={currentCenter} onLocationFound={onLocationFound} />
          {locationLabel && (
            <p className="mt-1 text-xs text-slate-400">Showing listings near {locationLabel}</p>
          )}
          {geolocationError && (
            <div className="mt-2 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
              <p>{geolocationError}</p>
              <button
                type="button"
                onClick={onRetryGeolocation}
                className="mt-1 font-medium underline hover:text-amber-900"
              >
                Retry
              </button>
            </div>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Max budget ($/mo)
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={draft.budgetMax}
              onChange={(e) => setField('budgetMax', e.target.value)}
              placeholder="Any"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Radius (km)
            <input
              type="number"
              min={0}
              step={0.5}
              inputMode="decimal"
              value={draft.radiusKm}
              onChange={(e) => setField('radiusKm', e.target.value)}
              placeholder="Any"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Min beds
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={draft.minBeds}
              onChange={(e) => setField('minBeds', e.target.value)}
              placeholder="Any"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Min baths
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={draft.minBathrooms}
              onChange={(e) => setField('minBathrooms', e.target.value)}
              placeholder="Any"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
          </label>
        </div>

        {draft.radiusKm && (
          <p className="mt-2 text-xs text-slate-400">Radius is measured from the map center.</p>
        )}

        <button
          type="button"
          onClick={() => onDraftChange(EMPTY_FILTER_DRAFT)}
          className="mt-3 text-xs font-medium text-slate-500 hover:text-slate-900 hover:underline"
        >
          Reset filters
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>
        )}

        {isLoading ? (
          <p className="text-sm text-slate-400">Loading listings…</p>
        ) : listings.length === 0 ? (
          <p className="text-sm text-slate-400">No listings match your filters.</p>
        ) : (
          <>
            <p className="mb-3 text-xs font-medium text-slate-400">
              {listings.length} listing{listings.length === 1 ? '' : 's'}
            </p>
            <div className="flex flex-col gap-3">
              {listings.map((listing) => (
                <ListingCard key={listing.id} listing={listing} onSelect={onSelectListing} />
              ))}
            </div>
          </>
        )}
      </div>
    </aside>
  )
}
