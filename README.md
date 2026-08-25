# ARENA: Identity-Verified Multiplayer Tic-Tac-Toe

ARENA is a real-time Tic-Tac-Toe multiplayer game where your face is your password. It features a FastAPI/WebSockets backend, hybrid storage (MySQL + MongoDB), and FIDE-standard Elo matchmaking. 

## Key Technical Features

* **Client-Side Face Recognition:** Instead of sending heavy images to the server, the game uses `face-api.js` to process webcam streams directly in the browser (Edge ML). It computes a 128-d facial array on the user's GPU and passes only this lightweight data to the backend for fast verification.
* **Dockerized Microservices:** The entire stack is containerized using Docker Compose, orchestrating the FastAPI backend, Nginx reverse proxy, MySQL (for relational game data), and MongoDB (for unstructured profile snapshots).
* **Automated Boot Sequence:** The Python backend includes a custom backoff/retry loop. It waits for the databases to fully initialize before booting and automatically generates the required SQL tables and NoSQL indexes on startup.
* **Secure Sessions:** Authentication is stateful, using cryptographically generated opaque tokens. These are stored in `HttpOnly` cookies to prevent XSS attacks, and the backend actively blocks concurrent logins.
* **Real-Time Matchmaking:** The WebSocket lobby handles live peer-to-peer matchmaking, tracks who is online, and manages TTL (Time-To-Live) expiring challenge requests.
* **Disconnect Handling:** If a player loses connection or closes the tab mid-match, the WebSocket manager safely destroys the game room and issues an automatic forfeit penalty to the disconnected player.
* **Elo Ranking System:** Player rankings update dynamically using the standard zero-sum Elo rating algorithm (K-factor of 32).

---

## Prerequisites

Because this project is fully containerized, you do not need complex build tools or local database installations.

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Podman with `podman-compose`)
* Git

---

## Quick Start Guide

### 1. Environment Setup
Clone the repository and create a `.env` file at the project root to configure the databases:

```env
MYSQL_USER=arena_user
MYSQL_PASSWORD=secure_arena_pass
MONGO_URI=mongodb://arena_mongo:27017/
```

### 2. Launch the Application
Build and spin up the microservices in the background:

```bash
docker compose up --build -d
```

### 3. Play the Game (Localhost)
Open your browser and navigate to:
`http://localhost:5500/register.html`

*Note: You must register your face to create an account before you can access the multiplayer lobby.*

### 4. Stopping the Application
To safely spin down the containers and preserve database state:
```bash
docker compose down
```

---

## Testing Multiplayer Over Wi-Fi

**Important Security Note:** Modern browsers block webcam access on unencrypted `http://` connections unless the URL is exactly `localhost`. If you share your local IP address with friends on your Wi-Fi, their browsers will block the camera.

To test across different devices (like your phone or a friend's laptop), use a secure tunnel like [ngrok](https://ngrok.com/):

1. Install `ngrok` on your host machine.
2. Tunnel the Nginx frontend port:
   ```bash
   ngrok http 5500
   ```
3. Ngrok will generate a secure HTTPS link (e.g., `https://abc-123.ngrok.app`).
4. Share this link. The browser will recognize the secure context and allow camera access. 

---

## Database Architecture

### MySQL (`arena_db`)

**`users` Table**
| Field      | Type         | Description    |
| ---------- | ------------ | -------------- |
| uid        | VARCHAR(50)  | Primary key (UUID) |
| name       | VARCHAR(200) | Player name (Unique) |
| elo_rating | INT          | Player ranking |
| is_online  | BOOLEAN      | Real-time online status  |

**`matches` Table**
| Field        | Type        | Description                     |
| ------------ | ----------- | ------------------------------- |
| match_id     | INT         | Primary key                     |
| player_x_uid | VARCHAR(50) | Player assigned X               |
| player_o_uid | VARCHAR(50) | Player assigned O               |
| winner_uid   | VARCHAR(50) | Winner UID (NULL for draw)      |
| forfeit      | BOOLEAN     | TRUE if winner came by forfeit  |
| played_at    | TIMESTAMP   | Match completion time           |

### MongoDB (`arena_db`)

**`profile_images` Collection**
Stores unstructured biometric snapshots captured during registration.
```json
{
  "_id": "<ObjectId>",
  "uid": "<user id>",
  "image_data": "<Base64 encoded jpeg>",
  "scraped_at": "<ISODate>"
}
```

---

## Acknowledgements

This originally started as a software systems course project built by Team Zero Latency. Following the initial build, I did a massive architectural refactor to make it production-ready. 

The major changes in this version include:
1. Moving from a monolithic script to a Docker Compose environment (FastAPI, Nginx, MySQL, MongoDB).
2. Ripping out heavy server-side C++ dependencies (`dlib`, `face_recognition`) to fix dependency hell, replacing them with client-side inference (`face-api.js`).
3. Adding a clean `/register` endpoint to ingest the frontend-computed 128-d face arrays.
4. Breaking down the massive client-side `dashboard.js` "god file" into modular files handling UI, state, and authentication separately.
5. Refactoring the client-side JavaScript to properly handle the new state data, updated cookies, and asynchronous network calls.
6. Breaking down the Python `main.py` "god file" into dedicated routers and adding database connection retry loops.
7. Adding an Nginx reverse proxy and environment-agnostic JavaScript routing to support HTTP tunneling (like ngrok) for cross-device play.
