import { useCallback, useEffect, useState } from 'react'
import type { GeoPoint } from '../types/listing'

export type GeolocationStatus =
  | 'loading'
  | 'resolved'
  | 'denied' // user (or a prior site-permission choice) rejected the browser prompt
  | 'unavailable' // browser permission was granted but the OS couldn't produce a position —
  // on macOS this is almost always System Settings > Privacy & Security > Location
  // Services being off, either entirely or for this specific browser
  | 'timeout'
  | 'unsupported'

interface GeolocationState {
  center: GeoPoint | null
  status: GeolocationStatus
}

export function useGeolocation(): GeolocationState & { retry: () => void } {
  const [state, setState] = useState<GeolocationState>({ center: null, status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setState({ center: null, status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setState({ center: null, status: 'unsupported' })
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setState({
          center: { latitude: position.coords.latitude, longitude: position.coords.longitude },
          status: 'resolved',
        })
      },
      (error) => {
        let status: GeolocationStatus = 'unavailable'
        if (error.code === error.PERMISSION_DENIED) status = 'denied'
        else if (error.code === error.TIMEOUT) status = 'timeout'
        setState({ center: null, status })
      },
      { enableHighAccuracy: false, timeout: 12000, maximumAge: 5 * 60 * 1000 },
    )
    // `attempt` is a manual re-trigger token — deliberately not otherwise used in the body.
  }, [attempt])

  return { ...state, retry }
}
