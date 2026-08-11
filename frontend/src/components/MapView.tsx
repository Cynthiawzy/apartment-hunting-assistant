import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useEffect, useRef, type RefObject } from 'react'
import type { FlyToRequest, GeoPoint, Listing } from '../types/listing'
import { clusterListings } from '../utils/cluster'
import { formatPrice } from '../utils/format'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
// Lets you keep a real token in .env but still skip live map loads (and the
// free-tier usage they cost) while working on anything that isn't map-specific.
const MAPBOX_ENABLED = import.meta.env.VITE_MAPBOX_ENABLED !== 'false'

// Listings whose on-screen positions land within this many pixels of each
// other get grouped into a single number-bubble marker.
const CLUSTER_PIXEL_THRESHOLD = 45

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

  // Kept fresh across renders so the mount-only effect below — and the
  // moveend/zoom handler registered inside it — can always read the latest
  // listings/callbacks without needing to re-run map setup when they change.
  const listingsRef = useRef(listings)
  const onCenterChangeRef = useRef(onCenterChange)
  const onSelectListingRef = useRef(onSelectListing)
  listingsRef.current = listings
  onCenterChangeRef.current = onCenterChange
  onSelectListingRef.current = onSelectListing

  // Re-clustering + re-rendering is triggered from two places (listings
  // changing, and the map panning/zooming) but always needs the same logic,
  // so it lives in a ref rather than being duplicated or re-created per render.
  const renderMarkersRef = useRef<() => void>(() => {})
  renderMarkersRef.current = () => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    popupsRef.current.forEach((popup) => popup.remove())
    popupsRef.current = []

    const clusters = clusterListings(listingsRef.current, map, CLUSTER_PIXEL_THRESHOLD)

    for (const cluster of clusters) {
      if (cluster.listings.length === 1) {
        addListingMarker(map, cluster.listings[0], markersRef, popupsRef, onSelectListingRef)
      } else {
        addClusterMarker(map, cluster, markersRef, popupsRef, onSelectListingRef)
      }
    }
  }

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
      // Pan and zoom both fire moveend, and both can change which listings
      // are close enough on-screen to cluster — re-render every time.
      renderMarkersRef.current()
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    renderMarkersRef.current()
  }, [listings])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyToRequest) return
    map.flyTo({
      center: [flyToRequest.center.longitude, flyToRequest.center.latitude],
      zoom: 13,
    })
    // moveend (fired when the flyTo animation settles) reports the new
    // center back up via onCenterChange and re-renders markers, so no extra
    // handling is needed here.
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

type MarkerRefs = RefObject<mapboxgl.Marker[]>
type PopupRefs = RefObject<mapboxgl.Popup[]>
type SelectListingRef = RefObject<(listing: Listing) => void>

function addListingMarker(
  map: mapboxgl.Map,
  listing: Listing,
  markersRef: MarkerRefs,
  popupsRef: PopupRefs,
  onSelectListingRef: SelectListingRef,
): void {
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

function addClusterMarker(
  map: mapboxgl.Map,
  cluster: { listings: Listing[]; center: GeoPoint },
  markersRef: MarkerRefs,
  popupsRef: PopupRefs,
  onSelectListingRef: SelectListingRef,
): void {
  const count = cluster.listings.length

  const el = document.createElement('div')
  el.className =
    'flex items-center justify-center rounded-full bg-blue-600 text-white text-sm font-bold ' +
    'shadow-md border-2 border-white cursor-pointer select-none hover:bg-blue-700 transition-colors'
  el.style.width = '36px'
  el.style.height = '36px'
  el.textContent = String(count)
  el.setAttribute('role', 'button')
  el.setAttribute('aria-label', `${count} listings in this area — click to view`)

  const popupContent = document.createElement('div')
  popupContent.className = 'max-h-64 w-64 overflow-y-auto text-sm'

  const header = document.createElement('div')
  header.className = 'mb-1 font-semibold text-slate-900'
  header.textContent = `${count} listings here`
  popupContent.append(header)

  const list = document.createElement('div')
  list.className = 'flex flex-col divide-y divide-slate-100'
  for (const listing of cluster.listings) {
    const row = document.createElement('button')
    row.type = 'button'
    row.className = 'py-1.5 text-left hover:bg-slate-50'

    const priceEl = document.createElement('div')
    priceEl.className = 'font-semibold text-slate-900'
    priceEl.textContent = formatPrice(listing.price)

    const addressEl = document.createElement('div')
    addressEl.className = 'truncate text-xs text-slate-500'
    addressEl.textContent = listing.address_line

    row.append(priceEl, addressEl)
    row.addEventListener('click', () => {
      popup.remove()
      onSelectListingRef.current(listing)
    })
    list.append(row)
  }
  popupContent.append(list)

  const popup = new mapboxgl.Popup({
    offset: 20,
    closeButton: true,
    closeOnClick: false,
    // Mapbox defaults maxWidth to 240px, narrower than our content's own
    // w-64 (256px) — that mismatch is what was pushing text past the
    // popup's right edge. Let the content's own width govern instead.
    maxWidth: 'none',
  }).setDOMContent(popupContent)

  el.addEventListener('click', () => {
    popup.setLngLat([cluster.center.longitude, cluster.center.latitude]).addTo(map)
  })

  const marker = new mapboxgl.Marker({ element: el })
    .setLngLat([cluster.center.longitude, cluster.center.latitude])
    .addTo(map)

  markersRef.current.push(marker)
  popupsRef.current.push(popup)
}
