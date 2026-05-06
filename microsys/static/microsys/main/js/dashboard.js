document.addEventListener('DOMContentLoaded', function () {
    const chartElement = document.getElementById('activityChart24h');
    const dataElement = document.getElementById('dashboard-activity-24h-data');

    if (!chartElement || !dataElement || typeof window.Plotly === 'undefined') {
        return;
    }

    let data24h = { labels: [], values: [] };
    try {
        data24h = JSON.parse(dataElement.textContent) || data24h;
    } catch (_error) {
        return;
    }

    const commonLayout = {
        autosize: true,
        margin: { t: 20, r: 10, l: 10, b: 0 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        showlegend: false,
        title: {
            text: chartElement.dataset.chartTitle || '',
            font: { family: 'inherit', size: 16, color: '#6c757d' },
            x: 0.5,
            y: 0.95,
        },
        font: { family: 'inherit', color: '#6c757d' },
        xaxis: {
            showgrid: false,
            zeroline: false,
            showticklabels: false,
        },
        yaxis: {
            showgrid: false,
            gridcolor: 'rgba(0,0,0,0.05)',
            zeroline: false,
            showticklabels: false,
        },
    };

    const config = {
        responsive: false,
        displayModeBar: false,
        locale: chartElement.dataset.chartLocale || 'en',
    };

    window.Plotly.newPlot('activityChart24h', [{
        x: data24h.labels || [],
        y: data24h.values || [],
        type: 'scatter',
        mode: 'lines+markers',
        line: { shape: 'spline', width: 3, color: '#0d6efd' },
        marker: { size: 6, color: '#0d6efd' },
        fill: 'tozeroy',
        fillcolor: 'rgba(13, 110, 253, 0.1)',
    }], commonLayout, config);

    const resizeObserver = new ResizeObserver(function () {
        window.Plotly.Plots.resize(chartElement);
    });

    if (chartElement.parentElement) {
        resizeObserver.observe(chartElement.parentElement);
    }
});
