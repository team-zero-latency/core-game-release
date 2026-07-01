import { state } from './state.js';
import { verifyAndInit } from './auth.js';
import { renderLobby, startGameUI, handleInvalidMove, updateBoard, handleGameOver, incomingSection, incomingList, cancelSection } from './ui.js';

export function respondChallenge(challengerUid, isAccepted) {
    state.liveWS.send(JSON.stringify({
        action: isAccepted ? 'accept_challenge' : 'decline_challenge',
        to_uid: challengerUid,
        accept: isAccepted
    }));

    //Remove the card from window
    const card = document.getElementById(`req-${challengerUid}`);
    if (card)
        card.remove();
    if(incomingList.children.length === 0)
        incomingSection.hidden = true;
};

//WebSocket Connection
export function connectLiveWebSocket() {
    const LIVE_WS_URL = `ws://${window.location.hostname}:8000/live`;
    state.liveWS = new WebSocket(LIVE_WS_URL);

    state.liveWS.onopen = () => {
        console.log('[Lobby] Websocket Connected');
    };

    state.liveWS.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('[Lobby] WS Message received:', data);

        switch (data.action) {
            case 'lobby_update':
                renderLobby(data.users);
                break;

            case 'receive_challenge':
                if(state.currentRoomId){
                    // Decline if already in game
                    state.liveWS.send(JSON.stringify({
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
                    const reqElement = document.getElementById(`req-${data.from_uid}`);
                    if(reqElement){
                        reqElement.remove();
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

                if(state.uid === data.player_x)
                    assigned_symbol = 'X';
                else
                    assigned_symbol = 'O';

                if(data.player1_uid === state.uid)
                    opponent_name = data.player2_name;
                else
                    opponent_name = data.player1_name;
            
                startGameUI(data.room_id, assigned_symbol, opponent_name);
                break;

        }
    };

    state.liveWS.onclose = (event) => {
        //Check if the connection dropped because a new tab took over
        if(event.code === 4000) {
            console.log('[Lobby] Session taken over by another tab/device');
            if(state.gameWS)
                state.gameWS.onclose = null;
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

export function connectGameWebSocket() {
    const GAME_WS_URL = `ws://${window.location.hostname}:8000/game/${state.currentRoomId}`;
    state.gameWS = new WebSocket(GAME_WS_URL);

    state.gameWS.onopen = () => {
        console.log('[Game] Websocket Connected');
    };

    state.gameWS.onmessage = (event) => {
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