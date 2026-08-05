import type { GeoPoint } from '../types/listing'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN

export interface GeocodeResult {
  center: GeoPoint
  placeName: string
}

interface GeocodeV6Feature {
  properties: {
    name: string
    full_address?: string
    place_formatted?: string
    coordinates: { longitude: number; latitude: number }
  }
}

interface GeocodeV6Response {
  features: GeocodeV6Feature[]
}

export class GeocodingError extends Error {}

/** Forward-geocodes free-text (address/city/zip) via Mapbox's Geocoding v6 API. */
export async function geocodeLocation(
  query: string,
  proximity: GeoPoint | null,
  signal?: AbortSignal,
): Promise<GeocodeResult | null> {
  if (!MAPBOX_TOKEN) {
    throw new GeocodingError('VITE_MAPBOX_ACCESS_TOKEN is not set')
  }

  const params = new URLSearchParams({
    q: query,
    access_token: MAPBOX_TOKEN,
    limit: '1',
  })
  if (proximity) {
    params.set('proximity', `${proximity.longitude},${proximity.latitude}`)
  }

  const response = await fetch(`https://api.mapbox.com/search/geocode/v6/forward?${params}`, {
    signal,
  })

  if (!response.ok) {
    throw new GeocodingError(`Geocoding request failed (${response.status})`)
  }

  const data = (await response.json()) as GeocodeV6Response
  const feature = data.features[0]
  if (!feature) return null

  return {
    center: {
      latitude: feature.properties.coordinates.latitude,
      longitude: feature.properties.coordinates.longitude,
    },
    placeName:
      feature.properties.full_address ?? feature.properties.place_formatted ?? feature.properties.name,
  }
}
