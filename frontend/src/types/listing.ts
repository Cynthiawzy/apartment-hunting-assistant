export type SourceSite =
  | 'zillow'
  | 'apartments_com'
  | 'craigslist'
  | 'streeteasy'
  | 'facebook_marketplace'
  | 'other'

export type ListingStatus = 'active' | 'pending' | 'leased' | 'inactive'

export interface Listing {
  id: number
  source_site: SourceSite
  source_listing_id: string
  url: string
  address_line: string
  unit: string | null
  city: string
  state: string
  zip_code: string
  latitude: number
  longitude: number
  price: number
  bedrooms: number
  /** Null for listings with no dedicated bathroom count (e.g. "private room" / shared-housing listings). */
  bathrooms: number | null
  sqft: number | null
  available_date: string | null
  pet_friendly: boolean | null
  amenities: string[] | null
  landlord_name: string | null
  landlord_phone: string | null
  landlord_email: string | null
  description: string | null
  status: ListingStatus
  scraped_at: string
  neighborhood_id: number | null
  distance_km: number | null
  created_at: string
  updated_at: string
}

export interface ListingFilters {
  budgetMax?: number
  minBeds?: number
  minBathrooms?: number
  radiusKm?: number
}

/** Raw sidebar form state; empty string means "unset". Parsed into ListingFilters before fetching. */
export interface FilterDraft {
  budgetMax: string
  minBeds: string
  minBathrooms: string
  radiusKm: string
}

export const EMPTY_FILTER_DRAFT: FilterDraft = {
  budgetMax: '',
  minBeds: '',
  minBathrooms: '',
  radiusKm: '',
}

export interface GeoPoint {
  latitude: number
  longitude: number
}

/** A distinct id forces MapView's fly-to effect to re-fire even for identical coordinates. */
export interface FlyToRequest {
  center: GeoPoint
  requestId: number
}
