// @vladmandic/face-api pulls in TensorFlow.js (~1.3MB minified) — dynamic
// import() here, not a static one, so the JS itself is only fetched and
// parsed once loadModels() actually runs, not merely once this module is
// imported. CameraCapture (the only caller) gates that behind an explicit
// "start" action rather than firing on mount, so opening the identity-
// verification route no longer pays this cost until someone actually
// begins a capture (HR_Code_report.md M4).
//
// Model weights served from /public/models (copied from
// node_modules/@vladmandic/face-api/model — see hcm/README.md's
// identity_verification section). Everything below runs entirely in the
// browser: face detection, landmark alignment, and descriptor extraction
// never send the video frame anywhere. Only the resulting 128-float
// descriptor is ever POSTed to the backend.
const MODEL_URL = '/models'

let modelsLoadedPromise: Promise<typeof import('@vladmandic/face-api')> | null = null

export function loadModels(): Promise<typeof import('@vladmandic/face-api')> {
  if (!modelsLoadedPromise) {
    modelsLoadedPromise = import('@vladmandic/face-api').then(async (faceapi) => {
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
      ])
      return faceapi
    })
  }
  return modelsLoadedPromise
}

/** Detects the most prominent face in the given video frame and returns
 * its 128-float descriptor, or null if no face was detected. */
export async function captureDescriptor(videoEl: HTMLVideoElement): Promise<number[] | null> {
  const faceapi = await loadModels()
  const detection = await faceapi
    .detectSingleFace(videoEl, new faceapi.TinyFaceDetectorOptions())
    .withFaceLandmarks()
    .withFaceDescriptor()
  if (!detection) return null
  return Array.from(detection.descriptor)
}
