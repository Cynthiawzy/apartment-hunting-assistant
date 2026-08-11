import type { Listing } from '../types/listing'
import { formatBedsBaths, formatDistance, formatPrice } from '../utils/format'

interface ListingCardProps {
  listing: Listing
  onSelect: (listing: Listing) => void
}

export function ListingCard({ listing, onSelect }: ListingCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(listing)}
      className="flex w-full gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-slate-900"
    >
      {listing.images && listing.images.length > 0 ? (
        <img
          src={listing.images[0]}
          alt=""
          className="h-16 w-16 shrink-0 rounded-md object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-300">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="h-6 w-6"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 4.5h18v15H3v-15z"
            />
          </svg>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-base font-semibold text-slate-900">
            {formatPrice(listing.price)}
          </span>
          <span className="text-xs text-slate-500">
            {formatBedsBaths(listing.bedrooms, listing.bathrooms)}
          </span>
        </div>
        <p className="mt-1 truncate text-sm text-slate-600">{listing.address_line}</p>
        <p className="text-xs text-slate-400">
          {listing.city}, {listing.state}
          {listing.distance_km !== null ? ` · ${formatDistance(listing.distance_km)}` : ''}
        </p>
      </div>
    </button>
  )
}
