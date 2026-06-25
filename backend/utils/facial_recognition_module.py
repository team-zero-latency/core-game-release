"""
CS6.201 Black-Box Facial Recognition Module
DO NOT MODIFY THIS FILE.

Dependencies (add to your uv project):
    uv add face-recognition numpy Pillow
"""

import base64
import io

import face_recognition
import numpy as np
from PIL import Image


def _to_bytes(data):
    """
    Accepts either raw bytes or a Base64-encoded string and always returns bytes.
    This allows callers to pass image data in either form.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return base64.b64decode(data)
    raise TypeError(f"Expected bytes or Base64 string, got {type(data).__name__}")


def get_face_encoding(image_data):
    """
    Accepts raw bytes or a Base64 string, locates the first face found,
    and returns its 128-d encoding. Returns None if no face is detected.
    """
    try:
        image_bytes = _to_bytes(image_data)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)
        locs = face_recognition.face_locations(image_np)
        if not locs:
            return None
        encs = face_recognition.face_encodings(image_np, locs)
        return encs[0] if encs else None
    except Exception as e:
        print(f"Error encoding image: {e}")
        return None

def build_encodings_cache(db_images_dict):
    """
    Call once at server startup.
    :param db_images_dict:
        { uid: image_data } fetched from MongoDB.
    :return:
        { uid: encoding } with entries skipped if no face is detected.
    """
    cache = {}
    for uid, img_data in db_images_dict.items():
        enc = get_face_encoding(img_data)
        if enc is not None:
            cache[uid] = enc
    print(f"Encodings cache built: {len(cache)}/{len(db_images_dict)} records encoded.")
    return cache

def find_closest_match(login_image_data, encodings_cache):
    """
    Compares a login attempt against precomputed encodings.
    :param login_image_data:
        The webcam capture as raw bytes or a Base64 string.
    :param encodings_cache:
        { uid: encoding } as returned by build_encodings_cache().
    :return:
        The UID of the closest matching face, or None if no face is
        detected in the login frame or no match clears the threshold.
    """
    print("Processing login frame...")
    login_enc = get_face_encoding(login_image_data)
    if login_enc is None:
        print("No face detected in login frame.")
        return None
    best_uid = None
    best_dist = float("inf")
    print(f"Comparing against {len(encodings_cache)} records in cache...")
    for uid, enc in encodings_cache.items():
        d = face_recognition.face_distance([enc], login_enc)[0]
        if d < best_dist:
            best_dist = d
            best_uid = uid
    threshold = 0.7
    if best_dist <= threshold:
        print(f"Match found: UID={best_uid}  distance={best_dist:.3f}")
        return best_uid
    print(f"No match found. Closest distance was {best_dist:.3f} (threshold is <= {threshold})")
    return None
