import type { Map as MapboxMap } from 'mapbox-gl'
import type { GeoPoint, Listing } from '../types/listing'

export interface ListingCluster {
  listings: Listing[]
  center: GeoPoint
}

/**
 * Greedily groups listings whose on-screen pixel distance (at the map's
 * current zoom/position) is within `pixelThreshold` of each other. Pixel-
 * based (not a fixed geo-distance) so it's naturally zoom-aware: the same
 * two listings cluster together when zoomed out and separate once zoomed in
 * enough that they're visually apart — without needing to recompute anything
 * beyond re-running this on the map's `moveend` (pan and zoom both fire it).
 */
export function clusterListings(
  listings: Listing[],
  map: MapboxMap,
  pixelThreshold: number,
): ListingCluster[] {
  const points = listings.map((listing) => ({
    listing,
    pixel: map.project([listing.longitude, listing.latitude]),
  }))

  const clusters: { listings: Listing[]; pixels: { x: number; y: number }[] }[] = []

  for (const point of points) {
    const target = clusters.find((cluster) => {
      const cx = cluster.pixels.reduce((sum, p) => sum + p.x, 0) / cluster.pixels.length
      const cy = cluster.pixels.reduce((sum, p) => sum + p.y, 0) / cluster.pixels.length
      return Math.hypot(point.pixel.x - cx, point.pixel.y - cy) <= pixelThreshold
    })

    if (target) {
      target.listings.push(point.listing)
      target.pixels.push(point.pixel)
    } else {
      clusters.push({ listings: [point.listing], pixels: [point.pixel] })
    }
  }

  return clusters.map((cluster) => ({
    listings: cluster.listings,
    center: {
      latitude: cluster.listings.reduce((sum, l) => sum + l.latitude, 0) / cluster.listings.length,
      longitude: cluster.listings.reduce((sum, l) => sum + l.longitude, 0) / cluster.listings.length,
    },
  }))
}
