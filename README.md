## ARENA: Multiplayer Tic-Tac-Toe Game

This project is a real-time Tic-Tac-Toe multiplayer game with facial-auth login, FastAPI/WebSockets backend, MySQL + MongoDB storage, and Elo-based leaderboard updates. Built using Python, HTML, CSS and Javascript. 

## Key Features & Technical Highlights

* **Custom Secure Session Management:** Implements stateful authentication using cryptographically generated, opaque tokens. Tokens are delivered via `HttpOnly` cookies to mitigate XSS vulnerabilities, and the backend actively prevents concurrent logins (handling session takeovers gracefully).
* **Asynchronous Matchmaking Lobby:** Utilizes WebSockets for real-time peer-to-peer matchmaking. Features live lobby status tracking, TTL (Time-To-Live) expiring challenge requests (30-second limits), and automatic cleanup of orphaned connections.
* **Server-Authoritative Game Engine:** The Tic-Tac-Toe game state is strictly validated on the backend to prevent client-side manipulation or cheating. 
* **Fault-Tolerant Disconnect Handling:** The WebSocket manager detects broken pipes or "ragequits" mid-match, safely destroying the isolated game room and automatically penalizing the disconnected player.
* **FIDE-Standard Elo Ranking System:** Implements the official zero-sum Elo rating algorithm (utilizing a K-factor of 32) to mathematically calculate expected win probabilities and dynamically update player rankings based on match outcomes.
* **Dynamic Biometric Onboarding & Hybrid Storage:** Replaces legacy batch-ingestion pipelines with a real-time, transactional registration workflow. Synchronously provisions new accounts by capturing webcam streams, hot-loading facial encodings into an in-memory server cache for instantaneous subsequent authentication, and preserving records across a dual-database layout: **MySQL** for relational gameplay metrics and **MongoDB** for unstructured binary image profiles.

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (or Podman) and a compose tool (`docker compose` / `docker-compose` or `podman-compose`)

Note: face-recognition has native dependencies.

- On Debian/Ubuntu install the common build libraries before installing Python packages:

```bash
sudo apt update && sudo apt install -y build-essential cmake libopenblas-dev liblapack-dev libjpeg-dev
```

- On Fedora (or RHEL/CentOS), install equivalent development packages:

```bash
sudo dnf install -y @development-tools cmake openblas-devel lapack-devel libjpeg-turbo-devel
```

Other distributions may require equivalent packages.

### Pre-run checklist

- Ensure these ports are free or change them in the compose and startup commands: 3306 (MySQL), 27017 (MongoDB), 8000 (backend), 5500 (frontend).

### Environment setup (`.env`)

Create a `.env` file at the project root:

```env
MYSQL_USER=myownuser
MYSQL_PASSWORD=myownpass
MONGO_URI=mongodb://localhost:27017/
```

Note: docker-compose is configured to read values from `.env` (so MySQL user/password are picked up automatically). The example uses simple credentials for local testing; the values can be changed to secure credentials for real deployments or evaluations before starting services.


### 1. Start databases

From repository root (Docker):

```bash
docker-compose up -d
```

Or with Docker Compose plugin:

```bash
docker compose up -d
```

If using Podman:

```bash
podman-compose up -d
```

This starts:
- `arena_mysql` on `localhost:3306`
- `arena_mongo` on `localhost:27017`

### 2. Initialize database schemas

#### MongoDB

Run with Docker:

```bash
docker exec -it arena_mongo mongo arena_db --eval 'db.profile_images.createIndex({uid: 1}, {unique: true})'
```

Or with Podman:

```bash
podman exec -it arena_mongo mongo arena_db --eval 'db.profile_images.createIndex({uid: 1}, {unique: true})'
```

#### MySQL

Run with Docker:

```bash
docker exec -it arena_mysql sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" arena_db -e "
CREATE TABLE IF NOT EXISTS users (
    uid VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) UNIQUE NOT NULL,
    elo_rating INT NOT NULL DEFAULT 1200,
    is_online BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS matches (
    match_id INT AUTO_INCREMENT PRIMARY KEY,
    player_x_uid VARCHAR(50) NOT NULL,
    player_o_uid VARCHAR(50) NOT NULL,
    winner_uid VARCHAR(50),
    forfeit BOOLEAN NOT NULL DEFAULT FALSE,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_x_uid) REFERENCES users(uid),
    FOREIGN KEY (player_o_uid) REFERENCES users(uid),
    FOREIGN KEY (winner_uid) REFERENCES users(uid)
);"'
```

Or with Podman:

```bash
podman exec -it arena_mysql sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" arena_db -e "
CREATE TABLE IF NOT EXISTS users (
    uid VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    elo_rating INT NOT NULL DEFAULT 1200,
    is_online BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS matches (
    match_id INT AUTO_INCREMENT PRIMARY KEY,
    player_x_uid VARCHAR(50) NOT NULL,
    player_o_uid VARCHAR(50) NOT NULL,
    winner_uid VARCHAR(50),
    forfeit BOOLEAN NOT NULL DEFAULT FALSE,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_x_uid) REFERENCES users(uid),
    FOREIGN KEY (player_o_uid) REFERENCES users(uid),
    FOREIGN KEY (winner_uid) REFERENCES users(uid)
);"'
```

### 3. Install dependencies

From repository root:

```bash
uv sync
```

### 4. Start backend (HTTP + WebSocket services)

In terminal 1:

```bash
cd backend
uv run uvicorn main:app --host localhost --port 8000
```

### 5. Start frontend

In terminal 2 (from repository root):

```bash
python3 -m http.server 5500
```

Open:

```text
http://localhost:5500/frontend/register.html
```

Warning: Do not open `register.html` using `file://`.

Note: You must register your face first to create an account before you can log in and access the multiplayer lobby.

## Database schemas

### MySQL (`arena_db`)

#### `users`

| Field      | Type         | Description    |
| ---------- | ------------ | -------------- |
| uid        | VARCHAR(50)  | Primary key    |
| name       | VARCHAR(200) | Player name    |
| elo_rating | INT          | Player ranking |
| is_online  | BOOLEAN      | Online status  |

#### `matches`

| Field        | Type        | Description                     |
| ------------ | ----------- | ------------------------------- |
| match_id     | INT         | Primary key                     |
| player_x_uid | VARCHAR(50) | Player assigned X               |
| player_o_uid | VARCHAR(50) | Player assigned O               |
| winner_uid   | VARCHAR(50) | Winner UID (NULL for draw)      |
| forfeit      | BOOLEAN     | TRUE if winner came by forfeit  |
| played_at    | TIMESTAMP   | Match completion time           |

### MongoDB (`arena_db`)

Collection: `profile_images`

Example document:

```json
{
  "_id": "<ObjectId>",
  "uid": "<user id>",
  "image_data": "<Base64 encoded image>",
  "scraped_at": "<ISODate>"
}
```

### Acknowledgements

This was originally our software systems course project, which we built from scratch. We used LLMs for debugging and syntax. We also used the models to create some boilerplate code for the frontend only. 
