import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useEffect, useRef } from 'react'
import type { FlyToRequest, GeoPoint, Listing } from '../types/listing'
import { formatPrice } from '../utils/format'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
// Lets you keep a real token in .env but still skip live map loads (and the
// free-tier usage they cost) while working on anything that isn't map-specific.
const MAPBOX_ENABLED = import.meta.env.VITE_MAPBOX_ENABLED !== 'false'

interface MapViewProps {
  listings: Listing[]
  initialCenter: GeoPoint
  flyToRequest: FlyToRequest | null
  onCenterChange: (center: GeoPoint) => void
  onSelectListing: (listing: Listing) => void
}

export function MapView({
  listings,
  initialCenter,
  flyToRequest,
  onCenterChange,
  onSelectListing,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const markersRef = useRef<mapboxgl.Marker[]>([])
  const popupsRef = useRef<mapboxgl.Popup[]>([])

  // Kept fresh across renders so the mount-only effect below can call the
  // latest callbacks without re-initializing the map when they change.
  const onCenterChangeRef = useRef(onCenterChange)
  const onSelectListingRef = useRef(onSelectListing)
  onCenterChangeRef.current = onCenterChange
  onSelectListingRef.current = onSelectListing

  useEffect(() => {
    if (!containerRef.current || !MAPBOX_TOKEN || !MAPBOX_ENABLED) return
    // Guards against React StrictMode's dev-only double-invoke creating a
    // second live map instance (and a second billed map load) on mount.
    if (mapRef.current) return

    mapboxgl.accessToken = MAPBOX_TOKEN
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/streets-v12',
      center: [initialCenter.longitude, initialCenter.latitude],
      zoom: 12,
    })
    map.addControl(new mapboxgl.NavigationControl(), 'top-right')

    map.on('moveend', () => {
      const c = map.getCenter()
      onCenterChangeRef.current({ latitude: c.lat, longitude: c.lng })
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    popupsRef.current.forEach((popup) => popup.remove())
    popupsRef.current = []

    for (const listing of listings) {
      const el = document.createElement('div')
      el.className =
        'rounded-full bg-slate-900 text-white text-xs font-semibold px-2 py-1 shadow-md ' +
        'border-2 border-white cursor-pointer select-none hover:bg-slate-700 transition-colors'
      el.textContent = formatPrice(listing.price)
      el.setAttribute('role', 'button')
      el.setAttribute('aria-label', `${formatPrice(listing.price)} at ${listing.address_line}`)

      const priceEl = document.createElement('div')
      priceEl.className = 'font-semibold text-slate-900'
      priceEl.textContent = formatPrice(listing.price)

      const addressEl = document.createElement('div')
      addressEl.className = 'text-slate-600'
      addressEl.textContent = listing.address_line

      const popupContent = document.createElement('div')
      popupContent.className = 'text-sm'
      popupContent.append(priceEl, addressEl)

      const popup = new mapboxgl.Popup({ offset: 16, closeButton: false, closeOnClick: false })
        .setLngLat([listing.longitude, listing.latitude])
        .setDOMContent(popupContent)

      el.addEventListener('mouseenter', () => popup.addTo(map))
      el.addEventListener('mouseleave', () => popup.remove())
      el.addEventListener('click', () => onSelectListingRef.current(listing))

      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat([listing.longitude, listing.latitude])
        .addTo(map)

      markersRef.current.push(marker)
      popupsRef.current.push(popup)
    }
  }, [listings])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyToRequest) return
    map.flyTo({
      center: [flyToRequest.center.longitude, flyToRequest.center.latitude],
      zoom: 13,
    })
    // moveend (fired when the flyTo animation settles) reports the new
    // center back up via onCenterChange, so no extra state sync needed here.
  }, [flyToRequest])

  if (!MAPBOX_TOKEN) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-100 p-6 text-center text-slate-500">
        Set VITE_MAPBOX_ACCESS_TOKEN in your .env to render the map.
      </div>
    )
  }

  if (!MAPBOX_ENABLED) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-100 p-6 text-center text-slate-500">
        Map disabled (VITE_MAPBOX_ENABLED=false) to save free-tier usage.
        <br />
        Set it to "true" or remove it to render the live map.
      </div>
    )
  }

  return <div ref={containerRef} className="h-full w-full" />
}
