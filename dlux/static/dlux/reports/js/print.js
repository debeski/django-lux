(function () {
    'use strict';

    const PAPER = '#ffffff';
    const INK = '#0b0b0b';
    const INK_SECONDARY = '#52514e';
    const INK_MUTED = '#898781';
    const GRID = '#e1e0d9';
    const AXIS = '#c3c2b7';
    const SERIES_1 = '#2a78d6';
    const SERIES_2 = '#eb6834';
    /* Validated categorical order (adjacent-pair CVD dE 9.1, normal-vision 19.6 on
       white). Assigned in fixed order and never cycled - the payload folds any tail
       past eight slots into a single "Other" slice server-side. */
    const CATEGORICAL = [
        '#2a78d6', '#eb6834', '#1baf7a', '#eda100',
        '#e87ba4', '#008300', '#4a3aa7', '#e34948',
    ];

    const printTrigger = document.querySelector('[data-dlux-report-print-trigger]');
    if (printTrigger) {
        printTrigger.addEventListener('click', function () { window.print(); });
    }

    const payloadNode = document.getElementById('dlux-report-chart-data');
    if (!payloadNode || typeof Chart === 'undefined') return;

    let payload;
    try {
        payload = JSON.parse(payloadNode.textContent);
    } catch (error) {
        return;
    }

    const isRtl = document.documentElement.dir === 'rtl';
    const charts = [];
    const numberFormat = new Intl.NumberFormat(document.documentElement.lang || 'en');
    const format = function (value) { return numberFormat.format(value || 0); };

    Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = INK_MUTED;

    function canvasFor(name) {
        return document.querySelector('[data-dlux-report-chart="' + name + '"]');
    }

    function luminance(hex) {
        const channels = [1, 3, 5].map(function (offset) {
            const value = parseInt(hex.substr(offset, 2), 16) / 255;
            return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    }

    function ratio(a, b) {
        const high = Math.max(a, b);
        const low = Math.min(a, b);
        return (high + 0.05) / (low + 0.05);
    }

    /* A label sitting inside a colored fill takes whichever of black/paper actually
       wins on contrast against that fill; every slot then clears 4.5:1. Chrome text
       elsewhere keeps the ink tokens - this pair is only ever used on top of a mark. */
    const FILL_INK = '#000000';

    function inkOn(fill) {
        const fillLum = luminance(fill);
        return ratio(fillLum, luminance(FILL_INK)) >= ratio(fillLum, luminance(PAPER)) ? FILL_INK : PAPER;
    }

    function labels(series) { return series.map(function (item) { return item.label; }); }
    function counts(series) { return series.map(function (item) { return item.count; }); }

    function baseOptions(extra) {
        return Object.assign({
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            devicePixelRatio: 2,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: INK,
                    titleColor: PAPER,
                    bodyColor: PAPER,
                    padding: 8,
                    displayColors: true,
                    rtl: isRtl,
                },
            },
        }, extra || {});
    }

    function categoryAxis(overrides) {
        return Object.assign({
            grid: { display: false },
            border: { color: AXIS },
            ticks: { color: INK_SECONDARY, autoSkip: false },
        }, overrides || {});
    }

    function valueAxis(overrides) {
        return Object.assign({
            beginAtZero: true,
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: {
                color: INK_MUTED,
                maxTicksLimit: 6,
                precision: 0,
                callback: function (value) { return format(value); },
            },
        }, overrides || {});
    }

    /* Value at the bar tip, drawn outside the end so it is never clipped by its
       own mark. Text wears an ink token, never the series color. */
    const barTipLabels = {
        id: 'dluxBarTipLabels',
        afterDatasetsDraw: function (chart) {
            const ctx = chart.ctx;
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data) return;
            ctx.save();
            ctx.font = '600 11px ' + Chart.defaults.font.family;
            ctx.fillStyle = INK_SECONDARY;
            ctx.textBaseline = 'middle';
            ctx.textAlign = isRtl ? 'right' : 'left';
            meta.data.forEach(function (bar, index) {
                const value = chart.data.datasets[0].data[index];
                if (!value) return;
                const offset = isRtl ? -6 : 6;
                ctx.fillText(format(value), bar.x + offset, bar.y);
            });
            ctx.restore();
        },
    };

    /* Inline segment labels for the operation mix, drawn only when the text fits
       with padding on both sides; everything else is carried by the legend. */
    const segmentLabels = {
        id: 'dluxSegmentLabels',
        afterDatasetsDraw: function (chart) {
            const ctx = chart.ctx;
            ctx.save();
            ctx.font = '600 11px ' + Chart.defaults.font.family;
            ctx.textBaseline = 'middle';
            ctx.textAlign = 'center';
            chart.data.datasets.forEach(function (dataset, datasetIndex) {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (!meta || meta.hidden || !meta.data.length) return;
                const bar = meta.data[0];
                const text = format(dataset.data[0]);
                const width = Math.abs(bar.base - bar.x);
                if (ctx.measureText(text).width + 16 > width) return;
                ctx.fillStyle = inkOn(CATEGORICAL[datasetIndex % CATEGORICAL.length]);
                ctx.fillText(text, (bar.base + bar.x) / 2, bar.y);
            });
            ctx.restore();
        },
    };

    const days = payload.days || [];
    if (days.length && canvasFor('days')) {
        charts.push(new Chart(canvasFor('days'), {
            type: 'line',
            data: {
                labels: labels(days),
                datasets: [{
                    data: counts(days),
                    borderColor: SERIES_1,
                    borderWidth: 2,
                    borderJoinStyle: 'round',
                    borderCapStyle: 'round',
                    backgroundColor: 'rgba(42, 120, 214, 0.1)',
                    fill: true,
                    tension: 0.25,
                    pointRadius: days.length > 45 ? 0 : 4,
                    pointBackgroundColor: SERIES_1,
                    pointBorderColor: PAPER,
                    pointBorderWidth: 2,
                    pointHoverRadius: 6,
                }],
            },
            options: baseOptions({
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: categoryAxis({
                        reverse: false,
                        ticks: {
                            color: INK_MUTED,
                            autoSkip: true,
                            maxTicksLimit: 12,
                            maxRotation: 0,
                        },
                    }),
                    y: valueAxis(),
                },
            }),
        }));
    }

    [
        { key: 'models', color: SERIES_1 },
        { key: 'users', color: SERIES_2 },
    ].forEach(function (spec) {
        const series = payload[spec.key] || [];
        const canvas = canvasFor(spec.key);
        if (!series.length || !canvas) return;
        charts.push(new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels(series),
                datasets: [{
                    data: counts(series),
                    backgroundColor: spec.color,
                    maxBarThickness: 24,
                    borderRadius: 4,
                    borderSkipped: 'start',
                }],
            },
            options: baseOptions({
                indexAxis: 'y',
                layout: { padding: { right: isRtl ? 8 : 56, left: isRtl ? 56 : 8 } },
                scales: {
                    x: valueAxis({ reverse: isRtl, ticks: { display: false }, grid: { color: GRID, drawTicks: false } }),
                    y: categoryAxis({
                        position: isRtl ? 'right' : 'left',
                        ticks: { color: INK_SECONDARY, autoSkip: false, crossAlign: 'far' },
                    }),
                },
            }),
            plugins: [barTipLabels],
        }));
    });

    const actions = payload.actions || [];
    const actionsCanvas = canvasFor('actions');
    if (actions.length && actionsCanvas) {
        charts.push(new Chart(actionsCanvas, {
            type: 'bar',
            data: {
                labels: [''],
                datasets: actions.map(function (item, index) {
                    return {
                        label: item.label,
                        data: [item.count],
                        backgroundColor: CATEGORICAL[index % CATEGORICAL.length],
                        borderColor: PAPER,
                        borderWidth: 2,
                        borderSkipped: false,
                        maxBarThickness: 24,
                    };
                }),
            },
            options: baseOptions({
                indexAxis: 'y',
                scales: {
                    x: { stacked: true, reverse: isRtl, display: false, grid: { display: false } },
                    y: { stacked: true, display: false, grid: { display: false } },
                },
            }),
            plugins: [segmentLabels],
        }));

        const legend = document.querySelector('[data-dlux-report-legend="actions"]');
        if (legend) {
            const total = actions.reduce(function (sum, item) { return sum + item.count; }, 0);
            actions.forEach(function (item, index) {
                const share = total ? Math.round((item.count / total) * 100) : 0;
                const entry = document.createElement('span');
                entry.className = 'dlux-report-legend-item';
                const swatch = document.createElement('span');
                swatch.className = 'dlux-report-legend-swatch';
                swatch.style.backgroundColor = CATEGORICAL[index % CATEGORICAL.length];
                const text = document.createElement('span');
                text.textContent = item.label + ' ';
                const value = document.createElement('strong');
                value.textContent = format(item.count) + ' (' + share + '%)';
                text.appendChild(value);
                entry.appendChild(swatch);
                entry.appendChild(text);
                legend.appendChild(entry);
            });
        }
    }

    function resizeChartsToContainers() {
        charts.forEach(function (chart) {
            const container = chart.canvas.parentElement;
            const width = Math.max(1, Math.floor(container.clientWidth));
            const height = Math.max(1, Math.floor(container.clientHeight));
            chart.resize(width, height);
            chart.update('none');
        });
    }

    /* Chrome switches to the narrower print layout before firing this event. Use
       its measured containers so Chart.js cannot retain stale screen dimensions. */
    window.addEventListener('beforeprint', function () {
        resizeChartsToContainers();
    });
    window.addEventListener('afterprint', function () {
        charts.forEach(function (chart) { chart.resize(); });
    });
})();
