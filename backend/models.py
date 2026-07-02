from pydantic import BaseModel
import math

#data model for login request
class login_data(BaseModel):
    embedding: list[float] # The 128-d array from the browser

# data model for register request
class register_data(BaseModel):
    name: str
    image: str
    embedding: list[float]

# custom math functions for the face-recognition workflow
def calculate_distance(emb1, emb2):
    return math.sqrt(sum((a-b)**2 for a, b in zip(emb1, emb2)))

def find_closest_match(login_embedding, cache, threshold=0.45):
    best_match = None
    min_dist = float('inf')
    for uid, known_embed in cache.items():
        if not known_embed:
            continue
        dist = calculate_distance(login_embedding, known_embed)
        if dist < min_dist and dist < threshold:
            min_dist = dist
            best_match = uid
    return best_match