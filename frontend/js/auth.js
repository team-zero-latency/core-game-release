import { state } from './state.js';

export async function verifyAndInit() {
    try {
        // Fetch /me to validate the server-side cookie
        const res = await fetch(`${state.API_BASE}/me`, {credentials: 'include' });
        if(!res.ok)
            throw new Error('Session Invalid');
        
        const data = await res.json();
        if(data.success) {
            localStorage.setItem('uid', data.uid);
            localStorage.setItem('name', data.name);
            localStorage.setItem('elo', data.elo);

            // Populate the global state
            state.uid = data.uid;
            state.playerName = data.name;
            state.elo = data.elo;

            return true;
        } else{
            throw new Error('Authentication failed');
        }
    } catch(err) {
        console.warn("Authentication check failed, redirecting...");
        localStorage.clear();
        window.location.href = 'index.html';
        return false;
    }
}

export async function handleLogout() {
    try {
        await fetch(`${state.API_BASE}/logout`, { method: 'POST', credentials: 'include'});       
    }
    catch (e) {
        console.warn('[Arena] Logout request failed.');
    }

    // Explicitly kill the websockets before redirecting
    if (state.liveWS) state.liveWS.close();
    if (state.gameWS) state.gameWS.close();
    
    localStorage.clear();
    window.location.href = 'index.html';
}