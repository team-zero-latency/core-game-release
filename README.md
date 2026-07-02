# ARENA: Identity-Verified Multiplayer Tic-Tac-Toe

This project is a real-time Tic-Tac-Toe multiplayer game featuring zero-latency biometric login, a modular FastAPI/WebSockets backend, resilient hybrid storage (MySQL + MongoDB), and FIDE-standard Elo matchmaking. Built using HTML, CSS, JavaScript and Python.

## Key Features & Technical Highlights

* **Zero-Latency Biometric Onboarding (Edge ML):** Replaces legacy server-side ingestion pipelines with real-time, client-side inference using `face-api.js`. The browser captures webcam streams and computes 128-d facial encodings directly on the user's GPU, passing only lightweight arrays to the backend for split-second Euclidean distance verification.
* **Resilient Microservice Architecture:** The backend operates as a fully modularized FastAPI application, containerized alongside MySQL, MongoDB, and an Nginx frontend via Docker Compose.
* **Automated Environment Provisioning:** Employs intelligent container healthchecks and automated Python backoff/retry loops to guarantee reliable startup sequences. The application self-initializes its relational SQL tables and NoSQL indexes on boot.
* **Custom Secure Session Management:** Implements stateful authentication using cryptographically generated, opaque tokens. Tokens are delivered via `HttpOnly` cookies to mitigate XSS vulnerabilities, and the backend actively prevents concurrent logins.
* **Asynchronous Matchmaking Lobby:** Utilizes WebSockets for real-time peer-to-peer matchmaking. Features live lobby status tracking, TTL (Time-To-Live) expiring challenge requests, and automatic cleanup of orphaned connections.
* **Fault-Tolerant Disconnect Handling:** The WebSocket manager detects broken pipes or "ragequits" mid-match, safely destroying the isolated game room and automatically penalizing the disconnected player.
* **FIDE-Standard Elo Ranking System:** Implements the official zero-sum Elo rating algorithm (K-factor of 32) to mathematically calculate expected win probabilities and dynamically update player rankings.

---

## Prerequisites

Because this project is fully containerized, you no longer need complex C++ build tools, Python environments, or local database installations.

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Podman with `podman-compose`)
* Git

---

## Quick Start Guide

### 1. Environment Setup
Clone the repository and create a `.env` file at the project root to secure your databases:

```env
MYSQL_USER=arena_user
MYSQL_PASSWORD=secure_arena_pass
MONGO_URI=mongodb://arena_mongo:27017/
```

### 2. Launch the Application
From the repository root, build and spin up the entire isolated microservice stack in the background:

```bash
docker compose up --build -d
```
*(Note: The Python backend includes a resilient backoff loop and will intelligently wait for the databases to initialize before booting up and auto-generating the required tables).*

### 3. Play the Game (Localhost)
Open your browser and navigate to:
    `http://localhost:5500/register.html`

*Note: You must register your face first to create an account before you can log in and access the multiplayer lobby.*

### 4. Stopping the Application
To safely spin down the microservices and preserve your database state, run from the repository root:

```bash
docker compose down
```

---

## Multiplayer over Local Network (Cross-Device)

** Important Webcam Security Note:** Modern browsers strictly block webcam access on unencrypted `http://` connections unless the URL is `localhost`. If you want friends to connect via their phones or laptops on your Wi-Fi network, you cannot simply share your Local IP address, as their browsers will block the camera.

To easily test multiplayer across devices, use a secure tunnel like [ngrok](https://ngrok.com/):

1. Install `ngrok` on your host machine.
2. Run the following command in your terminal to tunnel the Nginx frontend port:
   ```bash
   ngrok http 5500
   ```
3. Ngrok will generate a secure HTTPS link (e.g., `https://abc-123.ngrok.app`).
4. Share this `https://` link with your friends on the same Wi-Fi network. The browser will recognize the Secure Context and allow webcam access for biometric registration!

---

## Database Architecture

The application utilizes a hybrid database approach, isolating relational game metrics from unstructured binary profile data.

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

This was originally our software systems course project, built from scratch using Python, HTML, CSS, and plain JavaScript. Initial LLM usage was limited to debugging syntax and generating frontend boilerplate. 

Following the initial build, we utilized an AI assistant to conduct a massive architectural refactor. Together, we:
1. Migrated the monolithic application to a fully containerized Docker Compose environment (FastAPI, Nginx, MySQL, MongoDB).
2. Stripped out heavy, server-side C++ dependencies (`dlib`, `face_recognition`), entirely eliminating dependency hell and Python version conflicts.
3. Rewrote the biometric pipeline to perform client-side edge inference via `face-api.js`, dropping server load to near-zero.
4. Added a clean /register endpoint to ingest frontend-computed 128-d face arrays seamlessly alongside raw unstructured profile images.
5. Refactored the client-side "god file" `dashboard.js`, to smoothly match the revamped state data, cookies, and asynchronous network configurations.
6. Refactored the `main.py` "god file" into a clean, modern microservice architecture with dedicated routers, state managers, and robust database connection retry loops.
7. Implemented an Nginx reverse proxy and environment-agnostic (self-contained) JavaScript routing to seamlessly support secure cross-device play via HTTP tunnels like ngrok.