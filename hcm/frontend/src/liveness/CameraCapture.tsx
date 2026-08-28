import { useEffect, useRef, useState } from 'react'
import { captureDescriptor, loadModels } from './faceApi'

export interface CaptureResult {
  descriptor: number[] | null
  latitude: number | null
  longitude: number | null
}

function getLocation(): Promise<{ latitude: number | null; longitude: number | null }> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve({ latitude: null, longitude: null })
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => resolve({ latitude: null, longitude: null }),
      { timeout: 5000 },
    )
  })
}

/** Live camera preview + capture button, shared by enrollment and
 * verification. The captured video frame and geolocation never leave the
 * browser as-is — only the derived face descriptor (128 floats) and the
 * coordinates are handed to onCapture, for the caller to POST. */
export function CameraCapture({
  buttonLabel, onCapture, busy,
}: { buttonLabel: string; onCapture: (result: CaptureResult) => void; busy?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  // Both start false and stay false until handleStart runs -- opening this
  // route must not itself fetch camera permission or the face-api.js/
  // TensorFlow.js bundle (HR_Code_report.md M4). Only a click does.
  const [started, setStarted] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [modelsReady, setModelsReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [capturing, setCapturing] = useState(false)

  useEffect(() => {
    if (!started) return
    let cancelled = false

    loadModels()
      .then(() => {
        if (!cancelled) setModelsReady(true)
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load the face-recognition model.')
      })

    navigator.mediaDevices
      ?.getUserMedia({ video: { width: 320, height: 240 } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setCameraReady(true)
      })
      .catch(() => {
        if (!cancelled) setError('Camera access was denied or is unavailable.')
      })

    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [started])

  async function handleCapture() {
    if (!videoRef.current) return
    setCapturing(true)
    setError(null)
    try {
      const [descriptor, location] = await Promise.all([captureDescriptor(videoRef.current), getLocation()])
      onCapture({ descriptor, ...location })
    } catch {
      setError('Capture failed — please try again.')
    } finally {
      setCapturing(false)
    }
  }

  if (!started) {
    return (
      <div className="camera-capture">
        <div className="form-actions" style={{ marginTop: 8 }}>
          <button type="button" className="btn-secondary" onClick={() => setStarted(true)}>
            Start camera
          </button>
        </div>
      </div>
    )
  }

  const label = capturing ? 'Capturing…' : !modelsReady ? 'Loading model…' : !cameraReady ? 'Waiting for camera…' : buttonLabel

  return (
    <div className="camera-capture">
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <video ref={videoRef} autoPlay muted playsInline width={320} height={240} className="camera-preview" />
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn-primary"
          disabled={!cameraReady || !modelsReady || capturing || busy}
          onClick={() => void handleCapture()}
        >
          {label}
        </button>
      </div>
    </div>
  )
}
