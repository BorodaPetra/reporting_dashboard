const charts = {};                      // containerID -> {spec, overhead, drawnFor}
const FULL_WIDTH = 1200;                // a card this wide keeps the sizes of the spec
const MIN_FONT_FACTOR = 0.75;
const chartFontsLoaded = Promise.all(['400 10px Inter', '600 10px Inter'].map(font => document.fonts.load(font))); // Vega sizes labels and legends with the metrics of the font at draw time: drawn before Inter

let resizeTimer = null;
$(window).on('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        for (const id of Object.keys(charts)) {
            if ($(id).width() !== charts[id].drawnFor) drawChart(id);
        }
    }, 250);
});


function fontFactor(available, spec) {
    // a chart may declare the card width its sizes were chosen for (usermeta.designWidth)
    const design = (spec.usermeta && spec.usermeta.designWidth) || FULL_WIDTH;
    return Math.min(1, Math.max(MIN_FONT_FACTOR, available / design));
}

function isFontKey(key) {               // fontSize, labelFontSize, titleFontSize, ...
    return key === 'fontSize' || key.endsWith('FontSize');
}

function plotWidth(spec) {              // total width of the plot areas, left to right
    if (spec.hconcat) return spec.hconcat.reduce((sum, s) => sum + plotWidth(s), 0);
    if (spec.concat) return spec.concat.reduce((sum, s) => sum + plotWidth(s), 0);
    if (spec.vconcat) return Math.max(...spec.vconcat.map(plotWidth));
    if (typeof spec.width === 'number') return spec.width;
    if (spec.layer) return Math.max(0, ...spec.layer.map(plotWidth));
    return 0;
}

function scaled(spec, factor, fonts = 1) {   // copy: view widths * factor, fonts and heights * fonts
    const copy = Array.isArray(spec) ? [] : {};
    for (const [key, value] of Object.entries(spec)) {
        if (key === 'datasets' || key === 'data') { copy[key] = value; continue; }   // no need to copy data
        if (isFontKey(key) && typeof value === 'number') { copy[key] = Math.max(8, Math.round(value * fonts)); continue; }
        copy[key] = (value && typeof value === 'object') ? scaled(value, factor, fonts) : value;
    }
    const isView = spec.mark || spec.layer || spec.encoding;
    if (isView && typeof spec.width === 'number') copy.width = Math.max(80, Math.floor(spec.width * factor));
    if (isView && typeof spec.height === 'number')       // shrink, but not below 100 px - and never grow
        copy.height = Math.max(Math.min(spec.height, 100), Math.floor(spec.height * fonts));
    return copy;
}

function drawChart(containerID, corrections = 0) {
    const chart = charts[containerID];
    const available = $(containerID).width();
    const fonts = available > 0 ? fontFactor(available, chart.spec) : 1;
    if (chart.fonts !== fonts) { chart.fonts = fonts; chart.overhead = null; }   // label widths change with the fonts
    let spec = fonts < 1 ? scaled(chart.spec, 1, fonts) : chart.spec;    // 1st pass measures with the final fonts
    if (chart.overhead !== null && available > 0) {
        const base = plotWidth(chart.spec);
        if (base > 0) spec = scaled(chart.spec, (available - chart.overhead) / base, fonts);
    }
    chart.drawnFor = available;
    return vegaEmbed(containerID, spec, { "mode": "vega-lite", "ast": true, "actions": false }).then(result => {
        const drawn = $(containerID).find('svg.marks, canvas').first()[0].getBoundingClientRect().width;
        if (chart.overhead === null) {
            chart.overhead = Math.max(0, drawn - plotWidth(spec));      // the widths drawn in this pass
            return drawChart(containerID);          // second pass, now to the card width
        }
        // the overhead was measured on the widest plot, but a row of small panels (stock ranks,
        // the sales selectors) has more axes of its own: still wider than the card, count the
        // excess as overhead too and draw again, twice at most
        if (drawn > available + 1 && corrections < 2) {
            chart.overhead += drawn - available;
            return drawChart(containerID, corrections + 1);
        }
        return result;
    }).catch(console.error);
}


function chartEmbeding(containerID, chartData) {
    charts[containerID] = { spec: chartData, overhead: null, drawnFor: null, fonts: null };
    return chartFontsLoaded.then(() => drawChart(containerID));
}



