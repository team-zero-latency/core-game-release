const API_BASE = "";
const leaderboardBody = document.getElementById('leaderboardBody');
const currentUid = localStorage.getItem('uid');

async function verifyLeaderboard() {
    try {
        const res = await fetch(`${API_BASE}/me`, {credentials: 'include'});
        if(!res.ok) throw new Error('Session Invalid');

        const data = await res.json();
        if(data.success) {
            fetchLeaderboard();
        } else {
            throw new Error('Authentication failed');
        }
    } catch(err) {
        localStorage.clear();
        window.location.href = 'index.html';
    }
}   

async function fetchLeaderboard() {
    try {
        const res = await fetch(`${API_BASE}/leaderboard`);
        const data = await res.json();

        if(res.ok && data.players) {
            renderTable(data.players);
        } else {
            showError('Could not connect to the server.');
        } 
    }   catch (err) {
        console.error('[Arena] Leaderboard fetch error:', err);
        showError('Could not connect to the server.')
    }
}

function renderTable(players) {
    leaderboardBody.replaceChildren(); // Clear loading state
    
    if(players.length === 0) {
        showError('No players found');
        return 0;
    }

    players.forEach((player, index) => {
        //Create the row
        const row=document.createElement('tr');

        if(player.uid === currentUid)
            row.classList.add('highlight-row');

        //Create Rank cell
        const rankCell = document.createElement('td');
        rankCell.classList.add('rank-cell');
        rankCell.textContent = `#${index + 1}`;

        //Create Name cell
        const nameCell = document.createElement('td');
        nameCell.textContent = player.name;

        //Create Elo cell
        const eloCell = document.createElement('td');
        eloCell.classList.add('elo-cell');
        eloCell.textContent = player.elo_rating;

        //Append all cells to the row
        row.appendChild(rankCell);
        row.appendChild(nameCell);
        row.appendChild(eloCell);

        //Append row to the leaderboard body
        leaderboardBody.appendChild(row);
    });
}

function showError(msg) {
    leaderboardBody.replaceChildren();

    const row = document.createElement('tr');
    const cell = document.createElement('td');

    cell.colSpan = 3;
    cell.classList.add('cell-error');
    cell.textContent = msg;

    row.appendChild(cell);
    leaderboardBody.appendChild(row);
}

//Verify session cookies immediately on page load to render leaderboard
verifyLeaderboard();