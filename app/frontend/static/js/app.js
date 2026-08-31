function escapeHtml(value) {
    const element = document.createElement('div');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}

function readCookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const value = document.cookie.split('; ').find(item => item.startsWith(prefix));
    return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

function capitalize(value) {
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : '';
}

function mindMateChartOptions(yScale = {}, doughnut = false) {
    const options = {
        responsive: true,
        maintainAspectRatio: false,
        animation: {duration: 500},
        plugins: {
            legend: {display: doughnut, position: 'bottom', labels: {color: '#a1a1aa', boxWidth: 8, boxHeight: 8, padding: 16, font: {family: 'JetBrains Mono', size: 10}}},
            tooltip: {backgroundColor: '#18181b', borderColor: '#3f3f46', borderWidth: 1, titleColor: '#fff', bodyColor: '#a1a1aa'}
        }
    };
    if (!doughnut) options.scales = {
        x: {grid: {display: false}, ticks: {color: '#71717a', font: {family: 'JetBrains Mono', size: 9}}},
        y: {...yScale, grid: {color: 'rgba(63,63,70,.45)'}, ticks: {color: '#71717a', font: {family: 'JetBrains Mono', size: 9}}}
    };
    return options;
}

async function csrfFetch(resource, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const url = typeof resource === 'string' ? resource : resource.url;
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && url.startsWith('/')) {
        options.headers = new Headers(options.headers || {});
        const csrfToken = readCookie('csrf_token');
        if (!csrfToken) throw new Error('Missing CSRF cookie. Please sign in again.');
        options.headers.set('X-CSRF-Token', csrfToken);
    }
    return window.fetch(resource, options);
}

document.addEventListener('DOMContentLoaded', () => {
    const navToggle = document.querySelector('[data-nav-toggle]');
    const navLinks = document.querySelector('[data-nav-links]');
    if (navToggle && navLinks) {
        navToggle.addEventListener('click', () => {
            const open = navLinks.classList.toggle('open');
            navToggle.setAttribute('aria-expanded', String(open));
        });
    }
    document.querySelectorAll('.alert:not(.alert-permanent)').forEach(alert => {
        setTimeout(() => alert.remove(), 5000);
    });

    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', event => {
            const password = document.getElementById('password').value;
            const confirmation = document.getElementById('confirm_password').value;
            if (password !== confirmation || password.length < 8) {
                event.preventDefault();
                alert(password !== confirmation
                    ? 'Passwords do not match.'
                    : 'Password must be at least 8 characters long.');
            }
        });
    }
});
