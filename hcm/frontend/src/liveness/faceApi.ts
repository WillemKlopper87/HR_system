import * as faceapi from '@vladmandic/face-api'

// Model weights served from /public/models (copied from
// node_modules/@vladmandic/face-api/model — see hcm/README.md's
// identity_verification section). Everything below runs entirely in the
// browser: face detection, landmark alignment, and descriptor extraction
// never send the video frame anywhere. Only the resulting 128-float
// descriptor is ever POSTed to the backend.
const MODEL_URL = '/models'

let modelsLoadedPromise: Promise<void> | null = null

export function loadModels(): Promise<void> {
  if (!modelsLoadedPromise) {
    modelsLoadedPromise = Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
      faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
      faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
    ]).then(() => undefined)
  }
  return modelsLoadedPromise
}

/** Detects the most prominent face in the given video frame and returns
 * its 128-float descriptor, or null if no face was detected. */
export async function captureDescriptor(videoEl: HTMLVideoElement): Promise<number[] | null> {
  await loadModels()
  const detection = await faceapi
    .detectSingleFace(videoEl, new faceapi.TinyFaceDetectorOptions())
    .withFaceLandmarks()
    .withFaceDescriptor()
  if (!detection) return null
  return Array.from(detection.descriptor)
}
