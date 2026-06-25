const API_BASE = `http://${window.location.hostname}:8000`;

async function verifyAndInit() {
    try {
        // Fetch /me to validate the server-side cookie
        const res = await fetch(`${API_BASE}/me`, {credentials: 'include' });
        if(!res.ok)
            throw new Error('Session Invalid');
        
        const data = await res.json();
        if(data.success) {
            localStorage.setItem('uid', data.uid);
            localStorage.setItem('name', data.name);
            localStorage.setItem('elo', data.elo);

            //Start the dashboard
            intialiseDashboard();
        } else{
            throw new Error('Authentication failed');
        }
    } catch(err) {
        console.warn("Authentication check failed, redirecting...");
        localStorage.clear();
        window.location.href = 'index.html';
    }
}

function intialiseDashboard() {
    // Pull name/uid stored during login
    const playerName = localStorage.getItem('name');
    const uid  = localStorage.getItem('uid');
    const LIVE_WS_URL = `ws://${window.location.hostname}:8000/live`;
    let liveWS;
    let gameWS;
    let currentRoomId = null;
    let mySymbol = null;
    let currentChallengerUid = null;
    let challengeTargetUid = null;

    // UI elements mapping to phase 3 
    const welcomeHeader = document.getElementById('welcomeHeader');
    const lobbySection = document.getElementById('lobbySection');
    const lobbyGrid = document.getElementById('lobbyGrid');
    const incomingSection = document.getElementById('incomingSection');
    const incomingList = document.getElementById('incomingList');
    const cancelSection = document.getElementById('cancelSection');
    const cancelBtn = document.getElementById('cancelBtn');
    const gameSection = document.getElementById('gameSection');
    const playerSymbolEl = document.getElementById('playerSymbol');
    const opponentNameDisplay = document.getElementById('opponentNameDisplay');
    const turnIndicator = document.getElementById('turnIndicator');
    const cells = document.querySelectorAll('.cell');
    const actionButtons = document.getElementById('actionButtons');

    document.getElementById('welcomeName').textContent = 'Welcome, ' + playerName;
    document.getElementById('uidDisplay').textContent  = uid;

    const initialElo = localStorage.getItem('elo');
    document.getElementById('eloDisplay').textContent = initialElo;

    //UI Updater functions

    function renderLobby(users) {
        lobbyGrid.replaceChildren();

        // Sort the users such that free users come before in game ones
        users.sort((a, b) => {
            if(a.in_game === false && b.in_game === true)
                return -1;
            if(a.in_game === true && b.in_game === false)
                return 1;
            return 0;
        });

        users.forEach(user => {
            // Don't show the user themselves in the lobby list
            if (user.uid === uid)
                return;

            const userItem = document.createElement('li');
            userItem.classList.add('lobby-user');

            const nameDiv = document.createElement('div');
            nameDiv.classList.add('name');
            nameDiv.textContent = user.name;

            const hintDiv = document.createElement('div');
            hintDiv.classList.add('challenge-hint');
            
            if(user.in_game === false){
                hintDiv.textContent = 'Click to challenge';
            } else{
                hintDiv.textContent = 'User in match';
                userItem.classList.add('busy');
            }

            userItem.appendChild(nameDiv);
            userItem.appendChild(hintDiv);

            userItem.onclick = () => {
                if(user.in_game === false) {
                    if(confirm(`Send match challenge to ${user.name}?`)) {
                        liveWS.send(JSON.stringify({
                            action: 'send_challenge',
                            to_uid: user.uid
                        }));

                        cancelSection.hidden = false;
                        challengeTargetUid = user.uid;
                    }
                }
            };
            lobbyGrid.appendChild(userItem);
        });
    }

    function showChallengeModal(fromUid, fromName) {
        currentChallengerUid = fromUid;
        challengerName.textContent = fromName;
        challengeModal.showModal();
    }

    function startGameUI(roomId, symbol, opponentName) {
        currentRoomId = roomId;
        connectGameWebSocket();
        mySymbol = symbol;

        welcomeHeader.style.display = 'none';
        lobbySection.hidden = true;
        cancelSection.hidden = true;
        gameSection.hidden = false;
        actionButtons.style.display = 'none';
        incomingSection.style.display = 'none';

        document.getElementById('userNameDisplay').textContent = playerName;
        playerSymbolEl.textContent = mySymbol;
        if(mySymbol === 'O'){
            playerSymbolEl.style.color = "var(--error)";
        }
        opponentNameDisplay.textContent = opponentName;
        turnIndicator.textContent = 'Waiting for first move from player with X...';
        turnIndicator.style.color = "var(--muted)";

        //Clear board UI
        cells.forEach(cell => {
            cell.textContent = '';
            cell.className = 'cell';
        });
    }

    function handleInvalidMove(type) {
        if(type === 'block') {
            setTimeout( () => {
                turnIndicator.textContent = "Waiting for opponent...";
                turnIndicator.style.color = "var(--muted)";
            }, 2000);
            turnIndicator.textContent = "It is not your turn yet! Please wait...";
            turnIndicator.style.color = "var(--error)";
        }
        else if(type === 'invalid') {
            setTimeout( () => {
                turnIndicator.textContent = "It is your turn!";
                turnIndicator.style.color = "var(--accent)";
            }, 2000);
            turnIndicator.textContent = "This box has already been marked! Please mark a different one...";
            turnIndicator.style.color = "var(--error)";
        }
    }

    function updateBoard(boardArray, nextTurn) {
        boardArray.forEach((val, index) => {
            const cell = cells[index];
            if(val === -1){
                cell.textContent = '';
            }
            else{
                cell.textContent = val;
                // Adds 'x' or 'o' for colouring
                cell.classList.add(val.toLowerCase());
            }
            
        });

        if(nextTurn === uid) {
            turnIndicator.textContent = "It is your turn!";
            turnIndicator.style.color = "var(--accent)";
        }
        else {
            turnIndicator.textContent = "Waiting for opponent...";
            turnIndicator.style.color = "var(--muted)";
        }
    }

    function handleGameOver(result, reason, newElos) {
        let msg;
        
        if(result === 'both'){
            msg = 'Game Over: It\'s a draw!';
        }
        else if(result === uid){
            if(reason === 'resign_win_disconnect') {
                msg = 'Opponent disconnected. You win!';
            }
            else if(reason === 'resign_win_willing') {
                msg = 'Opponent resigned. You win!';
            }
            else{
                msg = 'Game Over: You win!';
            }
        }
        else {
            if(reason === 'resign_win_willing')
                msg = 'You resigned. Game Over!';
            else{
                msg = 'Game Over: You lose!';
            }
        }
        
        if(newElos && newElos[uid]){
            msg += `\nYour new Elo rating is: ${newElos[uid]}`;
            localStorage.setItem('elo', newElos[uid]);
            document.getElementById('eloDisplay').textContent = newElos[uid];
        }
        alert(msg);

        // Reset back to lobby
        currentRoomId = null;
        welcomeHeader.style.display = 'block';
        gameSection.hidden = true;
        lobbySection.hidden = false;
        actionButtons.style.display = 'flex';
    }

    //WebSocket Connection
    function connectLiveWebSocket() {
        liveWS = new WebSocket(LIVE_WS_URL);

        liveWS.onopen = () => {
            console.log('[Lobby] Websocket Connected');
        };

        liveWS.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('[Lobby] WS Message received:', data);

            switch (data.action) {
                case 'lobby_update':
                    renderLobby(data.users);
                    break;

                case 'receive_challenge':
                    if(currentRoomId){
                        // Decline if already in game
                        liveWS.send(JSON.stringify({
                            action: 'decline_challenge',
                            to_uid: data.from_uid,
                            accept: false
                        }));
                        return;
                    }

                    incomingSection.hidden = false;

                    //Create a challenge card for the challenger
                    const challengeCard = document.createElement('li');
                    challengeCard.id = `req-${data.from_uid}`;
                    challengeCard.classList.add('challenge-request-card');

                    const infoDiv = document.createElement('div');
                    infoDiv.style.lineHeight = '1.4';
                    const nameEl = document.createElement('div');
                    nameEl.style.fontWeight = 'bold';
                    nameEl.style.color = 'var(--text)';
                    nameEl.style.fontSize = '14px';
                    nameEl.textContent = data.from_name;

                    const subtitleEl = document.createElement('div');
                    subtitleEl.style.fontSize = '10px';
                    subtitleEl.style.color = 'var(--accent)';
                    subtitleEl.style.textTransform = 'uppercase';
                    subtitleEl.style.letterSpacing = '1px';
                    subtitleEl.textContent = 'Challenged You';

                    infoDiv.appendChild(nameEl);
                    infoDiv.appendChild(subtitleEl);

                    const btnGroup = document.createElement('div');
                    btnGroup.classList.add('challenge-btn-group');

                    const declineBtn = document.createElement('button');
                    declineBtn.className = 'btn btn-decline btn-small';
                    declineBtn.textContent = 'Decline';
                    declineBtn.addEventListener('click', () => respondChallenge(data.from_uid, false));

                    const acceptBtn = document.createElement('button');
                    acceptBtn.className = 'btn btn-accept btn-small';
                    acceptBtn.textContent ='Accept';
                    acceptBtn.addEventListener('click', () => respondChallenge(data.from_uid, true));

                    btnGroup.appendChild(declineBtn);
                    btnGroup.appendChild(acceptBtn);
                    challengeCard.appendChild(infoDiv);
                    challengeCard.appendChild(btnGroup);

                    incomingList.appendChild(challengeCard);

                    //Remove the element after 30 seconds to match backend main.py
                    setTimeout(() => {
                        if(document.getElementById(`req-${data.from_uid}`)){
                            document.getElementById(`req-${data.from_uid}`).remove();
                            if(incomingList.children.length === 0){
                                incomingSection.hidden = true;
                                cancelSection.hidden = true;
                            }
                        }
                    }, 30000);
                    break;

                case 'challenge_declined':
                    cancelSection.hidden = true;
                    alert('Your challenge was declined!');
                    break;

                case 'challenge_cancelled':
                    //Remove that specific user's card if they cancel
                    const cardToRemove = document.getElementById(`req-${data.from_uid}`);
                    if(cardToRemove){
                        cardToRemove.remove();
                        if(incomingList.children.length === 0)
                            incomingSection.hidden = true;
                    }
                    break;

                case 'challenge_error':
                    alert(data.message); // Will show if they click accept after 30 seconds
                    break;

                case 'redirect_to_room':
                    let assigned_symbol;
                    let opponent_name;

                    if(uid === data.player_x)
                        assigned_symbol = 'X';
                    else
                        assigned_symbol = 'O';

                    if(data.player1_uid === uid)
                        opponent_name = data.player2_name;
                    else
                        opponent_name = data.player1_name;
                
                    startGameUI(data.room_id, assigned_symbol, opponent_name);
                    break;

            }
        };

        liveWS.onclose = (event) => {
            //Check if the connection dropped because a new tab took over
            if(event.code === 4000) {
                console.log('[Lobby] Session taken over by another tab/device');
                if(gameWS)
                    gameWS.onclose = null;
                document.getElementById('disconnectedModal').showModal();
                return;
            }

            if(event.code === 1006) {
                console.warn('[Lobby] Connection refused by server. Verifying session...');
                verifyAndInit(); // This will auto-redirect to login if the session died
                return;
            }

            console.warn('[Lobby] WebSocket Disconnected. Reconnecting in 3s...');
            //Attempt to reconnect if the connection drops
            setTimeout(connectLiveWebSocket, 3000);
        }
    }

    function connectGameWebSocket() {
        const GAME_WS_URL = `ws://${window.location.hostname}:8000/game/${currentRoomId}`;
        gameWS = new WebSocket(GAME_WS_URL);

        gameWS.onopen = () => {
            console.log('[Game] Websocket Connected');
        };

        gameWS.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('[Game] WS Message received:', data);

            switch (data.action) {

                case 'block':
                    handleInvalidMove('block');
                    break;

                case 'invalid':
                    handleInvalidMove('invalid');
                    break;

                case 'update_board':
                    updateBoard(data.board, data.next_turn);
                    break;

                case 'game_end':
                    handleGameOver(data.result, data.reason, data.new_elos);
                    break;
            }
        };
    }

    //Event Listeners

    function respondChallenge(challengerUid, isAccepted) {
        liveWS.send(JSON.stringify({
            action: isAccepted ? 'accept_challenge' : 'decline_challenge',
            to_uid: challengerUid,
            accept: isAccepted
        }));

        //Remove the card from window
        document.getElementById(`req-${challengerUid}`).remove();
        if(incomingList.children.length === 0)
            incomingSection.hidden = true;
    };

    document.getElementById('cancelBtn').addEventListener('click', () => {
        liveWS.send(JSON.stringify({
            action: 'cancel_challenge',
            'to_uid': challengeTargetUid
        }));
        cancelSection.hidden = true;
    });

    document.getElementById('resignBtn').addEventListener('click', () => {
        gameWS.send(JSON.stringify({
            action: 'resign'
        }));
    });

    cells.forEach(cell => {
        cell.addEventListener('click', (e) => {
            const cellIndex = parseInt(e.target.getAttribute('data-index'));
            // Only send a move if the user is in a room
            if(currentRoomId) {
                gameWS.send(JSON.stringify({
                    action: 'play',
                    room_id: currentRoomId,
                    box_index: cellIndex
                }));
            }
        });
    });

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/logout`, {
            method: 'POST',
            credentials: 'include'
            });

            const data = await res.json();

            if(res.ok && data.success) {
                console.log('User has been successfully logged out');
            } else if(res.status === 401 && data.reason === "not_logged_in") {
                console.warn('User was not already logged in');
            }

        } catch (e) {
            console.warn('[Arena] Logout request failed — clearing session locally anyway.');
        }
        // Clear the session and redirect regardless of whether the backend fetch succeeded
        localStorage.clear();
        window.location.href = 'index.html';
    });

    // Start WebSocket connection automatically
    connectLiveWebSocket();
}

//Runs the server-side cookie authentication on page load
verifyAndInit();
