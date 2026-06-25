const themeToggleBtn = document.getElementById("themeToggle");
const root = document.documentElement;

if (root.getAttribute('data-theme') === 'light') {
    themeToggleBtn.setAttribute('aria-label', 'Toggle dark theme'); // Set initial aria-label based on the theme set by the <head> script
}

themeToggleBtn.addEventListener('click', ()=> {
    if(root.getAttribute('data-theme') === 'light') {
        root.removeAttribute('data-theme'); // Reverts to dark default
        localStorage.setItem('arena-theme', 'dark');
        themeToggleBtn.setAttribute('aria-label', 'Toggle light theme');
    }
    else {
        root.setAttribute('data-theme', 'light');
        localStorage.setItem('arena-theme', 'light');
        themeToggleBtn.setAttribute('aria-label', 'Toggle dark theme');
    }
});
