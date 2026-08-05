import { useEffect } from 'react'
import type { Listing } from '../types/listing'
import { formatBedsBaths, formatDistance, formatPrice } from '../utils/format'

interface ListingModalProps {
  listing: Listing | null
  onClose: () => void
}

export function ListingModal({ listing, onClose }: ListingModalProps) {
  useEffect(() => {
    if (!listing) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [listing, onClose])

  if (!listing) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="listing-modal-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="listing-modal-title" className="text-2xl font-semibold text-slate-900">
              {formatPrice(listing.price)}
              <span className="ml-1 text-base font-normal text-slate-400">/mo</span>
            </h2>
            <p className="text-sm text-slate-600">
              {formatBedsBaths(listing.bedrooms, listing.bathrooms)}
              {listing.sqft !== null ? ` · ${listing.sqft} sqft` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-900"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 border-t border-slate-100 pt-4">
          <p className="font-medium text-slate-900">
            {listing.address_line}
            {listing.unit ? `, ${listing.unit}` : ''}
          </p>
          <p className="text-sm text-slate-600">
            {listing.city}, {listing.state} {listing.zip_code}
          </p>
          {listing.distance_km !== null && (
            <p className="mt-1 text-sm text-slate-400">{formatDistance(listing.distance_km)}</p>
          )}
        </div>

        {listing.description && (
          <p className="mt-4 text-sm text-slate-700">{listing.description}</p>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-slate-400">Available</dt>
          <dd className="text-slate-900">{listing.available_date ?? 'Contact for details'}</dd>

          <dt className="text-slate-400">Pet friendly</dt>
          <dd className="text-slate-900">
            {listing.pet_friendly === null ? 'Unknown' : listing.pet_friendly ? 'Yes' : 'No'}
          </dd>

          <dt className="text-slate-400">Status</dt>
          <dd className="capitalize text-slate-900">{listing.status}</dd>

          <dt className="text-slate-400">Source</dt>
          <dd className="capitalize text-slate-900">{listing.source_site.replace('_', '.')}</dd>
        </dl>

        {listing.amenities && listing.amenities.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-slate-900">Amenities</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {listing.amenities.map((amenity) => (
                <span
                  key={amenity}
                  className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                >
                  {amenity}
                </span>
              ))}
            </div>
          </div>
        )}

        {(listing.landlord_name || listing.landlord_phone || listing.landlord_email) && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <h3 className="text-sm font-medium text-slate-900">Landlord contact</h3>
            <div className="mt-1 space-y-0.5 text-sm text-slate-600">
              {listing.landlord_name && <p>{listing.landlord_name}</p>}
              {listing.landlord_phone && <p>{listing.landlord_phone}</p>}
              {listing.landlord_email && <p>{listing.landlord_email}</p>}
            </div>
          </div>
        )}

        <a
          href={listing.url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-6 block w-full rounded-md bg-slate-900 px-4 py-2 text-center text-sm font-medium text-white hover:bg-slate-700"
        >
          View original listing
        </a>
      </div>
    </div>
  )
}
