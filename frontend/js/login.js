const API_BASE = `http://${window.location.hostname}:8000`;

const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const loginBtn = document.getElementById('loginBtn');
const statusEl = document.getElementById('status');
const statusText = document.getElementById('statusText');
const errBox = document.getElementById('errBox');
const placeholder = document.getElementById('placeholder');
const debugBox = document.getElementById('debugBox');
const debugPreview = document.getElementById('debugPreview');
const debugSize = document.getElementById('debugSize');
const scanLine = document.getElementById('scanLine');

let isRequesting = false;

async function loadFaceModels() {
    setStatus('loading', 'Loading AI models...') ;
    const MODEL_URL = 'https://justadudewhohacks.github.io/face-api.js/models';
    await Promise.all([
        faceapi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
    ]);
    startCamera(); // Start the camera after the models load
}

async function checkExistingSession() {
    try {
        const res = await fetch(`${API_BASE}/me`, {credentials: 'include'});
        const data = await res.json();

        if(data.success){
            window.location.href = 'dashboard.html';
        }
    } catch(err) {
        //Stay on login page only
    }
}

//Check session cookies to see if already logged in
checkExistingSession();

//Camera Initialisation
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
        
        // UI updates once stream is acquired
        placeholder.style.display = 'none';
        scanLine.style.opacity = '1';
        loginBtn.disabled = false;
        setStatus('ready', 'Camera ready — face the camera');
    } catch (err) {
        console.error('[Arena] Camera error:', err);
        setStatus('error', 'Camera error');
        showError('Could not access webcam. Please allow permissions and refresh.');
    }
}

//Capture Webcam Frame
function captureFrame() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    
    // Extract pure Base64 string
    return canvas.toDataURL('image/jpeg').split(',')[1];
}

// Login Flow
loginBtn.addEventListener('click', async () => {
    if (isRequesting) return;
    isRequesting = true;

    hideError();
    setStatus('loading', 'Scanning face…');
    loginBtn.disabled = true;

    try {
    // The client browser handles the ML inference
    const detection = await faceapi.detectSingleFace(video).withFaceLandmarks().withFaceDescriptor();

    if (!detection) {
        setStatus('error', 'Authentication failed');
        showError('No face detected. Please ensure you are clearly visible.');
        loginBtn.disabled = false;
        isRequesting = false;
        return;
    }

    const embeddingArray = Array.from(detection.descriptor);

    setStatus('loading', 'Verifying identity...');

    // Send only the inferred data (numbers) to verify with the backend
        const res = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ embedding: embeddingArray })
        });

        const data = await res.json();

        // Handle 200 OK
        if (res.ok && data.success) {
            setStatus('ready', 'Match found — redirecting…');
            localStorage.setItem('uid', data.uid);
            localStorage.setItem('name', data.name);
            localStorage.setItem('elo', data.elo);
            window.location.href = 'dashboard.html';
        } 
        // Handle 400 & 404 Failures
        else {
            setStatus('error', 'Authentication failed');
            if(res.status === 404 && data.reason === 'user_not_found') {
                showError('User does not exist in the database');
            } else if(res.status === 404 && data.reason === 'no_match') {
                showError('Face not recognised. Identity not verified.');
            } else if(res.status === 400 && data.reason === 'already_logged_in') {
                showError('You are already logged in on another device');
            } else {
                showError('Unknown authentication error occurred')
            }
            loginBtn.disabled = false;
        }
    } catch (err) {
        console.error('[Arena] Fetch error:', err);
        setStatus('error', 'Connection failed');
        showError('Could not connect to the backend. Is the server running?');
        loginBtn.disabled = false;
    }

    isRequesting = false;
});

//Helper functions
function setStatus(type, text) {
    statusEl.className = 'status ' + type;
    statusText.textContent = text;
}

function showError(msg) {
    errBox.textContent = msg;
    errBox.classList.add('show');
}

function hideError() {
    errBox.classList.remove('show');
}

function showDebug(base64) {
    debugBox.classList.add('show');
    debugPreview.textContent = base64.slice(0, 120) + '…';
    debugSize.textContent = `~${Math.round((base64.length * 3) / 4 / 1024)} KB`;
}

// Load the face models
loadFaceModels();