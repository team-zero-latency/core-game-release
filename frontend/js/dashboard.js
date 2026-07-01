import { state } from './state.js';
import { verifyAndInit, handleLogout } from './auth.js';
import { connectLiveWebSocket } from './websockets.js';
import { cancelSection, cells } from './ui.js';

async function init() {
    const success = await verifyAndInit(); // Authenticate the user
    if(!success)
        return; // auth.js handles redirect on failure

    document.getElementById('welcomeName').textContent = 'Welcome, ' + state.playerName;
    document.getElementById('uidDisplay').textContent = state.uid;
    document.getElementById('eloDisplay').textContent = state.elo;


    // Attach event listeners to all the buttons
    document.getElementById('cancelBtn').addEventListener('click', () => {
        state.liveWS.send(JSON.stringify({
            action: 'cancel_challenge',
            to_uid: state.challengeTargetUid
        }));
        cancelSection.hidden = true;
    });

    document.getElementById('resignBtn').addEventListener('click', () => {
        state.gameWS.send(JSON.stringify({action: 'resign'}));
    });

    document.getElementById('logoutBtn').addEventListener('click', handleLogout);

    cells.forEach(cell => {
        cell.addEventListener('click', (e) => {
            const cellIndex = parseInt(e.target.getAttribute('data-index'));
            if(state.currentRoomId) {
                state.gameWS.send(JSON.stringify({
                    action: 'play',
                    room_id: state.currentRoomId,
                    box_index: cellIndex
                }));
            }
        });
    });

    // Establish the live websocket connection
    connectLiveWebSocket();
}

// Run the dashboard boot sequence
init();