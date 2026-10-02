// Report tables: ReusableDataTable over a pandas frame as to_dict("split") ({columns, data});
// the markup comes from the data_table macro (includes/data-table.html). A second call with
// the same id (new data after a filter form) refills the table. options: more options of
// ReusableDataTable for this table (e.g. actionColumns with a cellFormatter for their cells).
const dataTables = {};
const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });
// Flask's JSON writes dates as HTTP dates ("Mon, 30 Sep 2024 00:00:00 GMT"); shown and sorted as ISO
const HTTP_DATE = /^\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/;

function isoDate(value) {
    if (typeof value !== "string" || !HTTP_DATE.test(value)) return value;
    const iso = new Date(value).toISOString();
    return iso.endsWith("T00:00:00.000Z") ? iso.slice(0, 10) : iso.slice(0, 19).replace("T", " ");
}

function makeDataTable(id, frame, exportName, options = {}) {
    const rows = frame.data.map(values => Object.fromEntries(
        frame.columns.map((column, i) => [column, isoDate(values[i])])));
    dataTables[id] ??= new ReusableDataTable({
        table: `#${id}`,
        searchInput: `#${id}-search`,
        info: `#${id}-info`,
        pagination: `#${id}-pagination`,
        prevButton: `#${id}-prev-page`,
        nextButton: `#${id}-next-page`,
        pageInfo: `#${id}-page-info`,
        resetButton: `#${id}-reset-filters`,
        exportButton: `#${id}-export`,
        exportFileBaseName: exportName,
        // 100, not the 1000 of the reference: two tables of 1000 rows (with a comment textarea
        // each) made 32k DOM nodes and froze the sidebar slide for ~0.5 s
        // PERF: render only the visible rows (virtual scrolling) if pages must grow again
        defaultPageSize: 100,
        onWarning: message => console.warn(message),
        ...options,
        // the cellFormatter of the options first (null: not its cell), then the numbers:
        // thousands separators on screen; the xlsx gets the numbers as they are
        cellFormatter: (value, column, row) => options.cellFormatter?.(value, column, row)
            ?? (typeof value === "number"
                ? { text: numberFormat.format(value), classNames: ["text-end", "numeric-cell"] }
                : null),
    });
    dataTables[id].setData({ columns: frame.columns, rows });
}

// Buttons of an action column (actionColumns, cellFormatter returns {node}). deleteForm: a POST
// form with the CSRF token and the fields, a trash button, the question asked by data-confirm
// (includes/scripts.html). rowActions: {edit, delete} urls of a row (delete null when not
// allowed) as a pencil link and that form.
function deleteForm(action, question, label, fields = {}) {
    const form = Object.assign(document.createElement("form"), { method: "post", action });
    form.dataset.confirm = question;
    const token = document.querySelector('meta[name="csrf-token"]').content;
    for (const [name, value] of Object.entries({ csrf_token: token, ...fields })) {
        form.append(Object.assign(document.createElement("input"), { type: "hidden", name, value }));
    }
    const button = Object.assign(document.createElement("button"),
        { type: "submit", className: "icon-button icon-danger", title: label, ariaLabel: label });
    button.innerHTML = '<i class="fas fa-trash-alt"></i>';
    form.append(button);
    return form;
}

function rowActions(actions, question) {
    const cell = Object.assign(document.createElement("div"), { className: "row-actions" });
    const edit = Object.assign(document.createElement("a"),
        { href: actions.edit, className: "icon-button", title: "Edit", ariaLabel: "Edit" });
    edit.innerHTML = '<i class="fas fa-pen"></i>';
    cell.append(edit);
    if (actions.delete) cell.append(deleteForm(actions.delete, question, "Delete"));
    return cell;
}

// A green notice in the middle of the page after a form was sent (sales filter, parts search)
// PERF: a new Notyf (and its container in the DOM) per call; one instance created on the first
//   call and kept in a module variable would reuse the container
function notifySubmitted(message) {
    new Notyf({
        position: { x: "center", y: "center" },
        types: [{
            type: "success",
            background: "#10B981",
            icon: { className: "fas fa-info-circle", tagName: "span", color: "#fff" },
            dismissible: false,
        }],
    }).open({ type: "success", message });
}

// Switch a card between its two faces (.front / .back of a .faces container: chart / table,
// USD / RUB): a crossfade. Both faces lie in the same grid cell (theme.css), so the old one
// fades out while the new one fades in on top of it. Opacity only: a translate snapped the text
// and the charts to the pixel grid at its end (a visible jitter). Replaces jquery.flip.
const FACE_FADE = { duration: 260, easing: "ease-in-out" };

function showFace(container, back) {
    if (container.classList.contains("show-back") === back) return;
    const face = selector => container.querySelector(`:scope > ${selector}`);
    const [from, to] = back ? [face(".front"), face(".back")] : [face(".back"), face(".front")];
    container.classList.toggle("show-back", back);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // the old face stays visible while it fades (the class above has already hidden it)
    from.animate([{ opacity: 1, visibility: "visible" }, { opacity: 0, visibility: "visible" }], FACE_FADE);
    to.animate([{ opacity: 0 }, { opacity: 1 }], FACE_FADE);
}

document.addEventListener("DOMContentLoaded", () => {

    // activate selected menu item based on nested li.active selector
    const menu_selected = document.querySelector(".sidebar .nav-item:has(li.active) > span.nav-link");
    if (menu_selected) menu_selected.click();

    // hide / show the sidebar; the charts redraw on resize (charts.js), sent once the content
    // has finished sliding so they measure the final width
    const toggles = document.querySelectorAll("[data-sidebar-toggle]");
    const showExpanded = () => toggles.forEach(button => button.setAttribute("aria-expanded",
        String(!document.documentElement.classList.contains("sidebar-collapsed"))));
    showExpanded();
    toggles.forEach(button => button.addEventListener("click", () => {
        const collapsed = document.documentElement.classList.toggle("sidebar-collapsed");
        try { localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0"); } catch (e) { }
        showExpanded();
        // without animation (theme.css) there is no transitionend
        if (matchMedia("(prefers-reduced-motion: reduce)").matches) window.dispatchEvent(new Event("resize"));
    }));
    // sales tiles: the progress bars grow from 0 to data-progress-grow and the percentages count
    // up from 0. Started once the main thread is idle: after DOMContentLoaded, and still after
    // load, the page draws its charts and tables for over a second, which ate the animation.
    // The bars start at width 0 in the markup and the numbers at 0 here, so nothing flashes.
    const whenIdle = window.requestIdleCallback || (callback => setTimeout(callback, 300));   // Safari
    const TILE_ANIMATION_MS = 1800;
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const bars = document.querySelectorAll("[data-progress-grow]");
    // "72%", "- $ 998", "+ $ 4,384": the first number counts, the text around it stays
    const counters = [...document.querySelectorAll("[data-count-up]")].flatMap(el => {
        const [, prefix, number, suffix] = el.textContent.trim().match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/) || [];
        if (number === undefined || reduceMotion) return [];
        const decimals = (number.split(".")[1] || "").length;
        const format = new Intl.NumberFormat("en-US", {
            minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: number.includes(",")
        });
        const show = value => { el.textContent = prefix + format.format(value) + suffix; };
        show(0);
        return [{ show, target: parseFloat(number.replaceAll(",", "")) }];
    });
    window.addEventListener("load", () => whenIdle(() => requestAnimationFrame(start => {
        bars.forEach(bar => {
            if (!reduceMotion) bar.style.transition = `width ${TILE_ANIMATION_MS}ms ease-out`;
            bar.style.width = bar.dataset.progressGrow;
        });
        const step = now => {
            const t = Math.min((now - start) / TILE_ANIMATION_MS, 1);
            const eased = 1 - (1 - t) ** 3;        // ease-out cubic, like the bars' ease-out
            counters.forEach(({ show, target }) => show(target * eased));
            if (t < 1) requestAnimationFrame(step);
        };
        if (counters.length) requestAnimationFrame(step);
    }), { timeout: 3000 }));

    document.querySelector(".content")?.addEventListener("transitionend", event => {
        if (event.target === event.currentTarget && event.propertyName === "margin-left")
            window.dispatchEvent(new Event("resize"));
    });

});