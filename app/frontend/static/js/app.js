// MindMate Frontend JavaScript

// API Base URL
const API_BASE = 'http://localhost:8000';

// Token management
let authToken = localStorage.getItem('mindmate_token');

// Set authorization header for fetch requests
function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
    };
}

// Check if user is authenticated
function isAuthenticated() {
    return !!authToken;
}

// Save token to localStorage
function saveToken(token) {
    authToken = token;
    localStorage.setItem('mindmate_token', token);
}

// Remove token (logout)
function removeToken() {
    authToken = null;
    localStorage.removeItem('mindmate_token');
}

// Handle API errors
function handleApiError(error) {
    console.error('API Error:', error);
    if (error.status === 401) {
        // Unauthorized - redirect to login
        removeToken();
        window.location.href = '/login';
    }
    return Promise.reject(error);
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Format sentiment score with color
function formatSentiment(score) {
    let color, icon;
    if (score > 0.3) {
        color = 'text-success';
        icon = 'fa-smile-beam';
    } else if (score > 0.1) {
        color = 'text-success';
        icon = 'fa-smile';
    } else if (score > -0.1) {
        color = 'text-secondary';
        icon = 'fa-meh';
    } else if (score > -0.3) {
        color = 'text-warning';
        icon = 'fa-frown';
    } else {
        color = 'text-danger';
        icon = 'fa-angry';
    }
    
    return {
        color,
        icon,
        label: score > 0.1 ? 'Positive' : score < -0.1 ? 'Negative' : 'Neutral'
    };
}

// Create emotion chart
function createEmotionChart(ctx, emotionData) {
    const emotions = Object.keys(emotionData);
    const scores = Object.values(emotionData);
    
    // Emotion colors
    const colors = {
        joy: '#FFD166',
        sadness: '#6C757D',
        anger: '#EF476F',
        fear: '#118AB2',
        surprise: '#06D6A0',
        trust: '#073B4C',
        anticipation: '#FF9A76',
        disgust: '#7209B7'
    };
    
    const backgroundColors = emotions.map(emotion => colors[emotion] || '#CCCCCC');
    
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: emotions.map(e => e.charAt(0).toUpperCase() + e.slice(1)),
            datasets: [{
                label: 'Emotion Intensity',
                data: scores,
                backgroundColor: backgroundColors,
                borderColor: backgroundColors.map(color => color.replace('0.8', '1')),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 1,
                    title: {
                        display: true,
                        text: 'Intensity'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Emotions'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

// Create sentiment trend chart
function createSentimentTrendChart(ctx, entries) {
    const dates = entries.map(entry => 
        new Date(entry.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    );
    const sentiments = entries.map(entry => entry.sentiment);
    const labels = entries.map(entry => entry.label);
    
    // Color points based on sentiment
    const pointBackgroundColors = sentiments.map(score => {
        if (score > 0.1) return '#28a745'; // Green for positive
        if (score < -0.1) return '#dc3545'; // Red for negative
        return '#6c757d'; // Gray for neutral
    });
    
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Sentiment Score',
                data: sentiments,
                borderColor: '#4a6fa5',
                backgroundColor: 'rgba(74, 111, 165, 0.1)',
                pointBackgroundColor: pointBackgroundColors,
                pointBorderColor: '#ffffff',
                pointRadius: 6,
                pointHoverRadius: 8,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: -1,
                    max: 1,
                    title: {
                        display: true,
                        text: 'Sentiment Score'
                    },
                    ticks: {
                        callback: function(value) {
                            if (value === 1) return 'Very Positive';
                            if (value === 0) return 'Neutral';
                            if (value === -1) return 'Very Negative';
                            return value;
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date'
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const index = context.dataIndex;
                            return `Sentiment: ${sentiments[index].toFixed(3)} (${labels[index]})`;
                        }
                    }
                }
            }
        }
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
    
    // Password validation for register form
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;
            
            if (password !== confirmPassword) {
                e.preventDefault();
                alert('Passwords do not match!');
                return false;
            }
            
            if (password.length < 8) {
                e.preventDefault();
                alert('Password must be at least 8 characters long!');
                return false;
            }
        });
    }
    
    // Load dashboard data if on dashboard page
    if (window.location.pathname === '/dashboard' && isAuthenticated()) {
        loadDashboardData();
    }
});

// Load dashboard data
async function loadDashboardData() {
    try {
        // Load entries
        const entriesResponse = await fetch(`${API_BASE}/entries/`, {
            headers: getAuthHeaders()
        });
        
        if (!entriesResponse.ok) {
            throw new Error('Failed to load entries');
        }
        
        const entries = await entriesResponse.json();
        displayRecentEntries(entries.slice(0, 5));
        
        // Load weekly summary
        const summaryResponse = await fetch(`${API_BASE}/entries/weekly-summary`, {
            headers: getAuthHeaders()
        });
        
        if (summaryResponse.ok) {
            const summary = await summaryResponse.json();
            displayWeeklySummary(summary);
        }
        
        // Load emotion trends
        const trendsResponse = await fetch(`${API_BASE}/entries/emotion-trends?days=7`, {
            headers: getAuthHeaders()
        });
        
        if (trendsResponse.ok) {
            const trends = await trendsResponse.json();
            displayEmotionTrends(trends);
        }
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        handleApiError(error);
    }
}

// Display recent entries
function displayRecentEntries(entries) {
    const container = document.getElementById('recentEntries');
    if (!container) return;
    
    if (entries.length === 0) {
        container.innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-book fa-3x text-muted mb-3"></i>
                <h5>No entries yet</h5>
                <p class="text-muted">Start your journaling journey by creating your first entry!</p>
                <a href="/journal" class="btn btn-primary">Write First Entry</a>
            </div>
        `;
        return;
    }
    
    let html = '';
    entries.forEach(entry => {
        const sentiment = formatSentiment(entry.sentiment_score);
        html += `
            <div class="card entry-card mb-3 border-left-${sentiment.color.replace('text-', '')}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <h6 class="card-title mb-1">${entry.title}</h6>
                        <span class="badge ${sentiment.color}">
                            <i class="fas ${sentiment.icon} me-1"></i>${sentiment.label}
                        </span>
                    </div>
                    <p class="card-text text-muted small mb-2">${entry.content.substring(0, 150)}${entry.content.length > 150 ? '...' : ''}</p>
                    <div class="d-flex justify-content-between align-items-center">
                        <small class="text-muted">${formatDate(entry.created_at)}</small>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewEntry(${entry.id})">
                            View <i class="fas fa-arrow-right ms-1"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Display weekly summary
function displayWeeklySummary(summary) {
    const container = document.getElementById('weeklySummary');
    if (!container) return;
    
    container.innerHTML = `
        <div class="card h-100">
            <div class="card-body">
                <h5 class="card-title">
                    <i class="fas fa-chart-bar me-2"></i>Weekly Summary
                </h5>
                <p class="card-text">${summary.summary}</p>
                
                <div class="mt-3">
                    <h6>📈 Statistics</h6>
                    <ul class="list-unstyled">
                        <li><i class="fas fa-book me-2"></i>Total Entries: ${summary.statistics.total_entries}</li>
                        <li><i class="fas fa-chart-line me-2"></i>Average Sentiment: ${summary.statistics.average_sentiment.toFixed(3)}</li>
                    </ul>
                </div>
                
                <div class="mt-3">
                    <h6>💡 Insights</h6>
                    <ul>
                        ${summary.insights.map(insight => `<li>${insight}</li>`).join('')}
                    </ul>
                </div>
                
                <div class="mt-3">
                    <h6>🎯 Recommendations</h6>
                    <ul>
                        ${summary.recommendations.map(rec => `<li>${rec}</li>`).join('')}
                    </ul>
                </div>
            </div>
        </div>
    `;
}

// Display emotion trends
function displayEmotionTrends(trends) {
    const container = document.getElementById('emotionTrends');
    if (!container) return;
    
    container.innerHTML = `
        <div class="card h-100">
            <div class="card-body">
                <h5 class="card-title">
                    <i class="fas fa-chart-line me-2"></i>Emotion Trends (Last ${trends.period_days} days)
                </h5>
                
                <div class="row mt-3">
                    <div class="col-md-6">
                        <canvas id="sentimentTrendChart"></canvas>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-4">
                            <h6>Trend Analysis</h6>
                            <div class="alert alert-${trends.trend_analysis.trend === 'improving' ? 'success' : trends.trend_analysis.trend === 'declining' ? 'warning' : 'info'}">
                                <strong>${trends.trend_analysis.trend.charAt(0).toUpperCase() + trends.trend_analysis.trend.slice(1)}</strong><br>
                                Average Sentiment: ${trends.trend_analysis.average_sentiment.toFixed(3)}<br>
                                Dominant Emotion: ${trends.trend_analysis.dominant_emotion}
                            </div>
                        </div>
                        
                        <div>
                            <h6>Quick Stats</h6>
                            <div class="row">
                                <div class="col-6">
                                    <div class="text-center p-3 bg-light rounded">
                                        <h3 class="mb-0">${trends.total_entries}</h3>
                                        <small class="text-muted">Entries</small>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="text-center p-3 bg-light rounded">
                                        <h3 class="mb-0">${trends.period_days}</h3>
                                        <small class="text-muted">Days</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Initialize chart after container is updated
    setTimeout(() => {
        const ctx = document.getElementById('sentimentTrendChart');
        if (ctx) {
            createSentimentTrendChart(ctx.getContext('2d'), trends.entries);
        }
    }, 100);
}

// View single entry
function viewEntry(entryId) {
    window.location.href = `/entry/${entryId}`;
}