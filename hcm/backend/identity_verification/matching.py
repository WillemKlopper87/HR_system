from __future__ import annotations

# face-api.js's own documented convention (SsdMobilenetv1/TinyFaceDetector +
# FaceRecognitionNet): Euclidean distance between two 128-d descriptors
# below this threshold is considered the same person. This has NOT been
# independently validated against this system's own population — treat it
# as a starting point, not a certified accuracy figure (Architecture-
# Design.md's own caution on ADR-003 applies here too: never treat a
# biometric-adjacent match as a determinative decision without specialist
# input — see services.py's human-review-required design).
MATCH_THRESHOLD = 0.6
DESCRIPTOR_LENGTH = 128


class DescriptorError(ValueError):
    pass


def euclidean_distance(a: list[float], b: list[float]) -> float:
    if len(a) != DESCRIPTOR_LENGTH or len(b) != DESCRIPTOR_LENGTH:
        raise DescriptorError(f"Face descriptors must have exactly {DESCRIPTOR_LENGTH} dimensions.")
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
