import { state } from './state.js';
import { connectGameWebSocket } from './websockets.js';

// DOM element references
export const welcomeHeader = document.getElementById('welcomeHeader');
export const lobbySection = document.getElementById('lobbySection');
export const lobbyGrid = document.getElementById('lobbyGrid');
export const incomingSection = document.getElementById('incomingSection');
export const incomingList = document.getElementById('incomingList');
export const cancelSection = document.getElementById('cancelSection');
export const cancelBtn = document.getElementById('cancelBtn');
export const gameSection = document.getElementById('gameSection');
export const playerSymbolEl = document.getElementById('playerSymbol');
export const opponentNameDisplay = document.getElementById('opponentNameDisplay');
export const turnIndicator = document.getElementById('turnIndicator');
export const cells = document.querySelectorAll('.cell');
export const actionButtons = document.getElementById('actionButtons');

//UI Updater functions

export function renderLobby(users) {
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
        if (user.uid === state.uid)
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
                    state.liveWS.send(JSON.stringify({
                        action: 'send_challenge',
                        to_uid: user.uid
                    }));

                    cancelSection.hidden = false;
                    state.challengeTargetUid = user.uid;
                }
            }
        };
        lobbyGrid.appendChild(userItem);
    });
}

export function startGameUI(roomId, symbol, opponentName) {
    state.currentRoomId = roomId;
    connectGameWebSocket();
    state.mySymbol = symbol;

    welcomeHeader.style.display = 'none';
    lobbySection.hidden = true;
    cancelSection.hidden = true;
    gameSection.hidden = false;
    actionButtons.style.display = 'none';
    incomingSection.style.display = 'none';

    document.getElementById('userNameDisplay').textContent = state.playerName;
    playerSymbolEl.textContent = state.mySymbol;
    if(state.mySymbol === 'O'){
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

export function handleInvalidMove(type) {
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

export function updateBoard(boardArray, nextTurn) {
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

    if(nextTurn === state.uid) {
        turnIndicator.textContent = "It is your turn!";
        turnIndicator.style.color = "var(--accent)";
    }
    else {
        turnIndicator.textContent = "Waiting for opponent...";
        turnIndicator.style.color = "var(--muted)";
    }
}

export function handleGameOver(result, reason, newElos) {
    let msg;
    
    if(result === 'both'){
        msg = 'Game Over: It\'s a draw!';
    }
    else if(result === state.uid){
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
    
    if(newElos && newElos[state.uid]){
        msg += `\nYour new Elo rating is: ${newElos[state.uid]}`;
        localStorage.setItem('elo', newElos[state.uid]);
        document.getElementById('eloDisplay').textContent = newElos[state.uid];
    }
    alert(msg);

    // Reset back to lobby
    state.currentRoomId = null;
    welcomeHeader.style.display = 'block';
    gameSection.hidden = true;
    lobbySection.hidden = false;
    actionButtons.style.display = 'flex';
}