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
      className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-slate-900"
    >
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
    </button>
  )
}
