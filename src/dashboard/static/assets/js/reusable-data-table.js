// Copy of parts_potential_v1/static/js/reusable-data-table.js with sorting by a click on a
// column header (option sortable), numbers written to the xlsx as numeric cells instead of
// text, a shorter page info, and action columns (option actionColumns: buttons such as a
// remove form, drawn by cellFormatter; neither searched, filtered, sorted nor exported).

"use strict";


(function () {

    const DEFAULT_OPTIONS = {
        columns: [],
        rows: [],
        defaultPageSize: 1000,
        rowNumberHeader: "#",
        commentHeader: "Comment",
        commentsEnabled: true,
        emptyText: "No data",
        noMatchesText: "0 matching rows",
        filteredRowsLabel: "filtered rows",
        exportFileBaseName: "Table Export",
        hiddenClass: "d-none",
        filterPlaceholder: "All / type...",
        filterSuggestionLimit: 80,
        searchDebounceMs: 120,
        sortable: true,
        actionColumns: [],
        rowId: (row, index) =>
            String(row?.__row_id ?? index),
        cellFormatter: null,
        exportValueFormatter: null,
        onWarning: null,
    };


    class ReusableDataTable {

        constructor(options) {
            this.options = {
                ...DEFAULT_OPTIONS,
                ...options,
            };

            this.el = {
                table: toElement(this.options.table),
                searchInput: toElement(this.options.searchInput),
                info: toElement(this.options.info),
                pagination: toElement(this.options.pagination),
                prevButton: toElement(this.options.prevButton),
                nextButton: toElement(this.options.nextButton),
                pageInfo: toElement(this.options.pageInfo),
                pageSizeSelect: toElement(this.options.pageSizeSelect),
                resetButton: toElement(this.options.resetButton),
                exportButton: toElement(this.options.exportButton),
            };

            if (!this.el.table) {
                throw new Error("ReusableDataTable requires a table element.");
            }

            this.state = {
                columns: asArray(this.options.columns),
                rows: asArray(this.options.rows),
                columnFilters: {},
                sort: { column: null, direction: 0 },     // 1 ascending, -1 descending
                rowComments: {},
                filterValueCache: new Map(),
                page: 1,
                pageSize:
                    Number(this.el.pageSizeSelect?.value) ||
                    Number(this.options.defaultPageSize) ||
                    1000,
            };

            this.boundListeners = [];

            this.bindEvents();
            this.render();
        }


        bindEvents() {
            this.bind(
                this.el.searchInput,
                "input",
                debounce(() => {
                    this.state.page = 1;
                    this.render();
                }, this.options.searchDebounceMs),
            );

            this.bind(
                this.el.resetButton,
                "click",
                () => this.resetFilters(),
            );

            this.bind(
                this.el.exportButton,
                "click",
                () => this.exportXlsx(),
            );

            this.bind(
                this.el.pageSizeSelect,
                "change",
                () => {
                    this.state.pageSize =
                        Number(this.el.pageSizeSelect.value) ||
                        Number(this.options.defaultPageSize) ||
                        1000;
                    this.state.page = 1;
                    this.render();
                },
            );

            this.bind(
                this.el.prevButton,
                "click",
                () => {
                    this.state.page = Math.max(
                        1,
                        this.state.page - 1,
                    );
                    this.render();
                },
            );

            this.bind(
                this.el.nextButton,
                "click",
                () => {
                    this.state.page += 1;
                    this.render();
                },
            );

            this.bind(
                this.el.table,
                "change",
                (event) => this.handleTableChange(event),
            );

            this.bind(
                this.el.table,
                "input",
                (event) => this.handleTableInput(event),
            );

            this.bind(
                this.el.table,
                "focusin",
                (event) => this.handleTableFocus(event),
            );

            this.bind(
                this.el.table,
                "mousedown",
                (event) => this.handleTableMousedown(event),
            );

            this.bind(
                this.el.table,
                "keydown",
                (event) => this.handleTableKeydown(event),
            );

            this.bind(
                this.el.table,
                "click",
                (event) => this.handleTableClick(event),
            );

            this.bind(
                document,
                "mousedown",
                (event) => {
                    if (!this.el.table.contains(event.target)) {
                        this.hideColumnFilterSuggestions();
                    }
                },
            );
        }


        bind(element, eventName, handler) {
            if (!element) {
                return;
            }

            element.addEventListener(eventName, handler);
            this.boundListeners.push({
                element,
                eventName,
                handler,
            });
        }


        destroy() {
            this.boundListeners.forEach(
                ({ element, eventName, handler }) =>
                    element.removeEventListener(eventName, handler),
            );

            this.boundListeners = [];
        }


        setData({
            columns = [],
            rows = [],
            resetFilters = true,
            resetComments = true,
        } = {}) {
            this.state.columns = asArray(columns);
            this.state.rows = asArray(rows);
            this.state.page = 1;
            this.state.filterValueCache =
                new Map();

            if (resetFilters) {
                this.state.columnFilters = {};
                this.state.sort = { column: null, direction: 0 };

                if (this.el.searchInput) {
                    this.el.searchInput.value = "";
                }
            }

            if (resetComments) {
                this.state.rowComments = {};
            }

            this.hideColumnFilterSuggestions();
            this.render();
        }


        getComments() {
            return {
                ...this.state.rowComments,
            };
        }


        getFilteredRows() {
            const searchText =
                (this.el.searchInput?.value || "")
                    .trim()
                    .toLowerCase();

            const columns =
                asArray(this.state.columns);

            let rows =
                asArray(this.state.rows)
                    .map((row, index) => ({
                        row,
                        index,
                    }));

            rows = rows.filter(
                ({ row }) => Object
                    .entries(this.state.columnFilters)
                    .every(([column, selected]) => {
                        if (!selected) {
                            return true;
                        }

                        return tableValue(row[column])
                            .toLowerCase()
                            .includes(
                                selected.toLowerCase(),
                            );
                    }),
            );

            if (!searchText) {
                return this.sortRows(rows);
            }

            return this.sortRows(rows.filter(
                ({ row, index }) => {
                    const rowId =
                        this.getRowId(row, index);

                    return columns
                        .filter((column) => !this.isActionColumn(column))
                        .some(
                            (column) =>
                                tableValue(row[column])
                                    .toLowerCase()
                                    .includes(searchText),
                        ) ||
                        tableValue(
                            this.state.rowComments[rowId],
                        )
                            .toLowerCase()
                            .includes(searchText);
                },
            ));
        }


        // rows is a fresh array (getFilteredRows maps the data), so it is sorted in place;
        // the sort is stable, and missing values go last in both directions
        // PERF: filtering and sorting rerun on every render, a page flip too; cache the filtered,
        // sorted index list until the data, a filter or the sort changes (15k rows: ~10 ms a flip)
        sortRows(rows) {
            const { column, direction } =
                this.state.sort;

            if (!column || !direction) {
                return rows;
            }

            return rows.sort(
                ({ row: a }, { row: b }) => {
                    const x = a[column];
                    const y = b[column];
                    const xMissing = tableValue(x) === "";
                    const yMissing = tableValue(y) === "";

                    if (xMissing || yMissing) {
                        return xMissing - yMissing;
                    }

                    const order =
                        typeof x === "number" && typeof y === "number"
                            ? x - y
                            : naturalCompare(x, y);

                    return order * direction;
                },
            );
        }


        resetFilters() {
            this.state.columnFilters = {};
            this.state.sort = { column: null, direction: 0 };
            this.state.page = 1;

            if (this.el.searchInput) {
                this.el.searchInput.value = "";
            }

            this.hideColumnFilterSuggestions();
            this.render();
        }


        exportXlsx() {
            const columns =
                asArray(this.state.columns);

            const rows =
                this.getFilteredRows();

            if (!columns.length || !rows.length) {
                this.warn("No table rows to export.");
                return;
            }

            const exportedColumns =
                columns.filter(
                    (column) => !this.isActionColumn(column),
                );

            const exportColumns = [
                this.options.rowNumberHeader,
                ...exportedColumns,
            ];

            if (this.options.commentsEnabled) {
                exportColumns.push(
                    this.options.commentHeader,
                );
            }

            const partCount =
                Math.ceil(rows.length / XLSX_MAX_DATA_ROWS);

            if (partCount > 1) {
                this.warn(
                    `Export exceeds Excel row limit and will be downloaded as ${formatNumber(partCount)} XLSX files.`,
                );
            }

            const timestamp =
                timestampForFilename();

            try {
                for (let partIndex = 0; partIndex < partCount; partIndex += 1) {
                    const startIndex =
                        partIndex * XLSX_MAX_DATA_ROWS;

                    const partRows =
                        rows.slice(
                            startIndex,
                            startIndex + XLSX_MAX_DATA_ROWS,
                        );

                    const partLabel =
                        partCount > 1
                            ? ` part ${partIndex + 1} of ${partCount}`
                            : "";

                    const fileBaseName =
                        `${this.options.exportFileBaseName}${partLabel}`;

                    const blob =
                        createXlsxBlob(
                            exportColumns,
                            partRows,
                            fileBaseName,
                            ({ row, index }, localIndex) => {
                                const rowId =
                                    this.getRowId(row, index);

                                const values = [
                                    startIndex + localIndex + 1,
                                    ...exportedColumns.map(
                                        (column) =>
                                            this.getExportValue(
                                                row[column],
                                                column,
                                                row,
                                            ),
                                    ),
                                ];

                                if (this.options.commentsEnabled) {
                                    values.push(
                                        this.state.rowComments[rowId] || "",
                                    );
                                }

                                return values;
                            },
                        );

                    downloadBlob(
                        blob,
                        `${fileBaseName} ${timestamp}.xlsx`,
                    );
                }
            } catch (error) {
                this.warn(
                    error?.message ||
                    "Unable to create XLSX export.",
                );
                return;
            }
        }


        render() {
            const columns =
                asArray(this.state.columns);

            const rows =
                this.getFilteredRows();

            const thead =
                this.el.table.querySelector("thead");

            const tbody =
                this.el.table.querySelector("tbody");

            if (!thead || !tbody) {
                return;
            }

            thead.innerHTML = "";
            tbody.innerHTML = "";

            if (!columns.length) {
                this.setInfo(
                    this.state.rows.length
                        ? this.options.noMatchesText
                        : this.options.emptyText,
                );
                this.updatePagination(0, 1, 0, 0);
                return;
            }

            this.renderHeader(thead, columns);

            if (!rows.length) {
                this.setInfo(
                    this.state.rows.length
                        ? this.options.noMatchesText
                        : this.options.emptyText,
                );
                this.updatePagination(0, 1, 0, 0);
                return;
            }

            const totalRows =
                rows.length;

            const pageSize =
                Math.max(
                    1,
                    Number(this.state.pageSize) || 1000,
                );

            const pageCount =
                Math.max(
                    1,
                    Math.ceil(totalRows / pageSize),
                );

            this.state.page =
                Math.min(
                    Math.max(1, this.state.page),
                    pageCount,
                );

            const startIndex =
                (this.state.page - 1) * pageSize;

            const visibleRows =
                rows.slice(
                    startIndex,
                    startIndex + pageSize,
                );

            this.renderBody(
                tbody,
                columns,
                visibleRows,
                startIndex,
            );

            this.setInfo(
                `${formatNumber(totalRows)} ${this.options.filteredRowsLabel}`,
            );

            this.updatePagination(
                totalRows,
                pageCount,
                startIndex,
                visibleRows.length,
            );
        }


        renderHeader(thead, columns) {
            const headerRow =
                document.createElement("tr");

            const numberHeader =
                document.createElement("th");

            numberHeader.textContent =
                this.options.rowNumberHeader;
            numberHeader.classList.add(
                "row-number-column",
            );

            headerRow.appendChild(numberHeader);

            columns.forEach(
                (column) => {
                    const th =
                        document.createElement("th");

                    th.textContent = column;

                    if (this.options.sortable && !this.isActionColumn(column)) {
                        const { column: sorted, direction } =
                            this.state.sort;

                        th.dataset.sortColumn = column;
                        th.classList.add("sortable-column");

                        if (sorted === column && direction) {
                            th.classList.add(
                                direction > 0 ? "sort-asc" : "sort-desc",
                            );
                        }
                    }

                    headerRow.appendChild(th);
                },
            );

            if (this.options.commentsEnabled) {
                const commentHeader =
                    document.createElement("th");

                commentHeader.textContent =
                    this.options.commentHeader;
                commentHeader.classList.add(
                    "comment-column",
                );

                headerRow.appendChild(commentHeader);
            }

            thead.appendChild(headerRow);

            const filterRow =
                document.createElement("tr");

            filterRow.className =
                "table-filter-row";

            filterRow.appendChild(
                document.createElement("th"),
            );

            columns.forEach(
                (column) => {
                    const th =
                        document.createElement("th");

                    if (this.isActionColumn(column)) {
                        filterRow.appendChild(th);
                        return;
                    }

                    const wrapper =
                        document.createElement("div");

                    wrapper.className =
                        "column-filter-wrapper";

                    const input =
                        document.createElement("input");

                    input.className =
                        "form-control form-control-sm column-filter";

                    input.type = "search";
                    input.placeholder =
                        this.options.filterPlaceholder;
                    input.dataset.column =
                        column;
                    input.value =
                        this.state.columnFilters[column] || "";

                    const suggestions =
                        document.createElement("div");

                    suggestions.className =
                        `column-filter-suggestions ${this.options.hiddenClass}`;

                    wrapper.appendChild(input);
                    wrapper.appendChild(suggestions);
                    th.appendChild(wrapper);
                    filterRow.appendChild(th);
                },
            );

            if (this.options.commentsEnabled) {
                filterRow.appendChild(
                    document.createElement("th"),
                );
            }

            thead.appendChild(filterRow);
        }


        renderBody(tbody, columns, rows, startIndex) {
            rows.forEach(
                ({ row, index }, visibleIndex) => {
                    const tr =
                        document.createElement("tr");

                    const numberCell =
                        document.createElement("td");

                    numberCell.textContent =
                        formatNumber(
                            startIndex + visibleIndex + 1,
                        );
                    numberCell.classList.add(
                        "row-number-column",
                        "text-end",
                        "numeric-cell",
                    );

                    tr.appendChild(numberCell);

                    columns.forEach(
                        (column) => {
                            const td =
                                document.createElement("td");

                            this.applyCellFormat(
                                td,
                                row[column],
                                column,
                                row,
                            );

                            tr.appendChild(td);
                        },
                    );

                    if (this.options.commentsEnabled) {
                        tr.appendChild(
                            this.createCommentCell(row, index),
                        );
                    }

                    tbody.appendChild(tr);
                },
            );
        }


        applyCellFormat(td, value, column, row) {
            const formatter =
                this.options.cellFormatter;

            const formatted =
                typeof formatter === "function"
                    ? formatter(value, column, row)
                    : null;

            if (typeof formatted === "string") {
                td.textContent = formatted;
                return;
            }

            if (formatted?.node instanceof Node) {
                td.appendChild(formatted.node);
            } else {
                td.textContent =
                    formatted?.text ?? tableValue(value);
            }

            const classNames =
                formatted?.classNames || [];

            if (typeof classNames === "string") {
                classNames
                    .split(/\s+/)
                    .filter(Boolean)
                    .forEach(
                        (className) => td.classList.add(className),
                    );
                return;
            }

            asArray(classNames)
                .filter(Boolean)
                .forEach(
                    (className) => td.classList.add(className),
                );
        }


        createCommentCell(row, index) {
            const commentCell =
                document.createElement("td");

            commentCell.classList.add(
                "comment-column",
            );

            const commentInput =
                document.createElement("textarea");

            commentInput.className =
                "form-control form-control-sm row-comment";

            const rowId =
                this.getRowId(row, index);

            commentInput.rows = 1;
            commentInput.dataset.rowId = rowId;
            commentInput.value =
                this.state.rowComments[rowId] || "";

            commentCell.appendChild(commentInput);

            return commentCell;
        }


        handleTableChange(event) {
            const target = event.target;

            if (!target.classList.contains("column-filter")) {
                return;
            }

            this.applyColumnFilter(target);
        }


        handleTableInput(event) {
            const target = event.target;

            if (target.classList.contains("column-filter")) {
                this.showColumnFilterSuggestions(target);
                return;
            }

            if (!target.classList.contains("row-comment")) {
                return;
            }

            const rowId =
                target.dataset.rowId;

            if (!rowId) {
                return;
            }

            this.state.rowComments[rowId] =
                target.value;
        }


        handleTableFocus(event) {
            const target = event.target;

            if (!target.classList.contains("column-filter")) {
                return;
            }

            this.showColumnFilterSuggestions(target);
        }


        handleTableMousedown(event) {
            const option =
                event.target.closest(
                    ".column-filter-suggestion",
                );

            if (!option) {
                return;
            }

            event.preventDefault();

            const wrapper =
                option.closest(
                    ".column-filter-wrapper",
                );

            const input =
                wrapper?.querySelector(
                    ".column-filter",
                );

            if (!input) {
                return;
            }

            input.value =
                option.dataset.value || "";

            this.applyColumnFilter(input);
        }


        handleTableKeydown(event) {
            const target = event.target;

            if (
                event.key !== "Enter" ||
                !target.classList.contains("column-filter")
            ) {
                return;
            }

            event.preventDefault();
            this.applyColumnFilter(target);
        }


        isActionColumn(column) {
            return asArray(this.options.actionColumns).includes(column);
        }


        // ascending, descending, then back to the order of the data
        handleTableClick(event) {
            const th =
                event.target.closest("th[data-sort-column]");

            if (!th) {
                return;
            }

            const column =
                th.dataset.sortColumn;

            const { column: sorted, direction } =
                this.state.sort;

            const next =
                sorted !== column ? 1 : direction > 0 ? -1 : 0;

            this.state.sort = {
                column: next ? column : null,
                direction: next,
            };
            this.state.page = 1;
            this.render();
        }


        getColumnFilterValues(column) {
            if (this.state.filterValueCache.has(column)) {
                return this.state.filterValueCache.get(column);
            }

            const values = unique(
                asArray(this.state.rows)
                    .map((row) =>
                        tableValue(row[column]),
                    )
                    .filter((value) => value !== ""),
            ).sort(naturalCompare);

            this.state.filterValueCache.set(
                column,
                values,
            );

            return values;
        }


        showColumnFilterSuggestions(input) {
            this.hideColumnFilterSuggestions(input);

            const wrapper =
                input.closest(
                    ".column-filter-wrapper",
                );

            const suggestions =
                wrapper?.querySelector(
                    ".column-filter-suggestions",
                );

            const column =
                input.dataset.column;

            if (!suggestions || !column) {
                return;
            }

            const typed =
                input.value.trim().toLowerCase();

            const values =
                this.getColumnFilterValues(column)
                    .filter(
                        (value) =>
                            !typed ||
                            value
                                .toLowerCase()
                                .includes(typed),
                    )
                    .slice(0, this.options.filterSuggestionLimit);

            suggestions.innerHTML = "";

            if (!values.length) {
                suggestions.classList.add(
                    this.options.hiddenClass,
                );

                return;
            }

            values.forEach(
                (value) => {
                    const button =
                        document.createElement("button");

                    button.type = "button";
                    button.className =
                        "column-filter-suggestion";
                    button.dataset.value =
                        value;
                    button.textContent =
                        value;

                    suggestions.appendChild(button);
                },
            );

            suggestions.classList.remove(
                this.options.hiddenClass,
            );
        }


        hideColumnFilterSuggestions(exceptInput = null) {
            this.el.table
                .querySelectorAll(
                    ".column-filter-suggestions",
                )
                .forEach((suggestions) => {
                    if (
                        exceptInput &&
                        suggestions.parentElement?.contains(
                            exceptInput,
                        )
                    ) {
                        return;
                    }

                    suggestions.classList.add(
                        this.options.hiddenClass,
                    );
                });
        }


        applyColumnFilter(input) {
            const column =
                input.dataset.column;

            if (!column) {
                return;
            }

            const value =
                input.value.trim();

            if (value) {
                this.state.columnFilters[column] =
                    value;
            } else {
                delete this.state.columnFilters[column];
            }

            this.state.page = 1;
            this.hideColumnFilterSuggestions();
            this.render();
        }


        updatePagination(totalRows, pageCount, startIndex, visibleCount) {
            const hasRows =
                totalRows > 0;

            this.el.pagination?.classList.toggle(
                this.options.hiddenClass,
                !hasRows,
            );

            if (this.el.prevButton) {
                this.el.prevButton.disabled =
                    !hasRows ||
                    this.state.page <= 1;
            }

            if (this.el.nextButton) {
                this.el.nextButton.disabled =
                    !hasRows ||
                    this.state.page >= pageCount;
            }

            if (this.el.pageSizeSelect) {
                this.el.pageSizeSelect.value =
                    String(this.state.pageSize);
            }

            if (!this.el.pageInfo) {
                return;
            }

            if (!hasRows) {
                this.el.pageInfo.textContent =
                    "No rows";
                return;
            }

            const firstRow =
                startIndex + 1;

            const lastRow =
                startIndex + visibleCount;

            // shorter than the reference ("| page 1 of 152" dropped): the toolbar of a half-width
            // card keeps one line
            this.el.pageInfo.textContent =
                `${formatNumber(firstRow)}–${formatNumber(lastRow)} of ` +
                `${formatNumber(totalRows)}`;
        }


        setInfo(text) {
            if (this.el.info) {
                this.el.info.textContent = text;
            }
        }


        getRowId(row, index) {
            return String(
                this.options.rowId(row, index),
            );
        }


        getExportValue(value, column, row) {
            const formatter =
                this.options.exportValueFormatter;

            return typeof formatter === "function"
                ? formatter(value, column, row)
                : value;
        }


        warn(message) {
            if (typeof this.options.onWarning === "function") {
                this.options.onWarning(message);
            }
        }
    }


    function toElement(value) {
        if (!value) {
            return null;
        }

        if (typeof value === "string") {
            return document.querySelector(value);
        }

        return value;
    }


    function unique(values) {
        return [
            ...new Set(
                asArray(values).filter(
                    (value) =>
                        value !== null &&
                        value !== undefined,
                ),
            ),
        ];
    }


    function asArray(value) {
        return Array.isArray(value)
            ? value
            : [];
    }


    function tableValue(value) {
        if (
            value === null ||
            value === undefined
        ) {
            return "";
        }

        return String(value);
    }


    function naturalCompare(a, b) {
        return String(a).localeCompare(
            String(b),
            undefined,
            {
                numeric: true,
                sensitivity: "base",
            },
        );
    }


    function formatNumber(value, decimals = 0) {
        if (
            value === null ||
            value === undefined ||
            Number.isNaN(value)
        ) {
            return "-";
        }

        return new Intl.NumberFormat(
            "en-US",
            {
                maximumFractionDigits:
                    decimals,
            },
        ).format(value);
    }


    const XLSX_MIME_TYPE =
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    const XLSX_ROW_BATCH_SIZE = 200;

    const XLSX_MAX_DATA_ROWS = 1048575;

    const ZIP32_MAX_SIZE = 0xffffffff;


    function createXlsxBlob(columns, rows, sheetName, rowMapper = null) {
        const safeSheetName =
            String(sheetName || "Table")
                .slice(0, 31)
                .replace(/[\[\]:*?/\\]/g, " ");

        const sheetXml =
            createWorksheetChunks(
                columns,
                rows,
                rowMapper,
            );

        const files = [
            {
                name: "[Content_Types].xml",
                content:
                    xmlDeclaration() +
                    `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
                    `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
                    `<Default Extension="xml" ContentType="application/xml"/>` +
                    `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
                    `<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>` +
                    `</Types>`,
            },
            {
                name: "_rels/.rels",
                content:
                    xmlDeclaration() +
                    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
                    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
                    `</Relationships>`,
            },
            {
                name: "xl/workbook.xml",
                content:
                    xmlDeclaration() +
                    `<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ` +
                    `xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
                    `<sheets><sheet name="${xmlEscape(safeSheetName)}" sheetId="1" r:id="rId1"/></sheets>` +
                    `</workbook>`,
            },
            {
                name: "xl/_rels/workbook.xml.rels",
                content:
                    xmlDeclaration() +
                    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
                    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>` +
                    `</Relationships>`,
            },
            {
                name: "xl/worksheets/sheet1.xml",
                content:
                    sheetXml,
            },
        ];

        return createZipArchiveBlob(
            files,
            XLSX_MIME_TYPE,
        );
    }


    function createWorksheetChunks(columns, rows, rowMapper) {
        const chunks = [
            xmlDeclaration(),
            `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">`,
            `<sheetData>`,
            worksheetRow(columns, 1),
        ];

        let batch = [];

        asArray(rows).forEach((row, rowIndex) => {
            const values =
                typeof rowMapper === "function"
                    ? rowMapper(row, rowIndex)
                    : row;

            batch.push(
                worksheetRow(
                    values,
                    rowIndex + 2,
                ),
            );

            if (batch.length >= XLSX_ROW_BATCH_SIZE) {
                chunks.push(
                    batch.join(""),
                );
                batch = [];
            }
        });

        if (batch.length) {
            chunks.push(
                batch.join(""),
            );
        }

        chunks.push(
            `</sheetData>`,
            `</worksheet>`,
        );

        return chunks;
    }


    function worksheetRow(values, rowNumber) {
        const cells =
            asArray(values)
                .map(
                    (value, columnIndex) =>
                        worksheetCell(
                            value,
                            columnIndex,
                            rowNumber,
                        ),
                ).join("");

        return `<row r="${rowNumber}">${cells}</row>`;
    }


    function worksheetCell(value, columnIndex, rowNumber) {
        const cellRef =
            `${excelColumnName(columnIndex)}${rowNumber}`;

        if (typeof value === "number" && Number.isFinite(value)) {
            return `<c r="${cellRef}"><v>${value}</v></c>`;
        }

        return `<c r="${cellRef}" t="inlineStr"><is><t>${xmlEscape(tableValue(value))}</t></is></c>`;
    }


    function excelColumnName(index) {
        let name = "";
        let number = index + 1;

        while (number > 0) {
            const remainder =
                (number - 1) % 26;

            name =
                String.fromCharCode(65 + remainder) +
                name;

            number =
                Math.floor((number - 1) / 26);
        }

        return name;
    }


    function createZipArchiveBlob(files, mimeType) {
        const encoder =
            new TextEncoder();

        const zipParts = [];
        const centralParts = [];
        let offset = 0;

        files.forEach((file) => {
            const nameBytes =
                encoder.encode(file.name);

            const dataChunks =
                encodeContentChunks(
                    file.content,
                    encoder,
                );

            const dataLength =
                dataChunks.reduce(
                    (sum, chunk) =>
                        sum + chunk.length,
                    0,
                );

            if (dataLength > ZIP32_MAX_SIZE) {
                throw new RangeError(
                    "XLSX export is too large for this browser ZIP writer.",
                );
            }

            const crc =
                crc32Chunks(dataChunks);

            const localHeader =
                concatUint8Arrays([
                    uint32(0x04034b50),
                    uint16(20),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint32(crc),
                    uint32(dataLength),
                    uint32(dataLength),
                    uint16(nameBytes.length),
                    uint16(0),
                    nameBytes,
                ]);

            zipParts.push(
                localHeader,
                ...dataChunks,
            );

            centralParts.push(
                concatUint8Arrays([
                    uint32(0x02014b50),
                    uint16(20),
                    uint16(20),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint32(crc),
                    uint32(dataLength),
                    uint32(dataLength),
                    uint16(nameBytes.length),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint16(0),
                    uint32(0),
                    uint32(offset),
                    nameBytes,
                ]),
            );

            offset +=
                localHeader.length +
                dataLength;

            if (offset > ZIP32_MAX_SIZE) {
                throw new RangeError(
                    "XLSX export is too large for this browser ZIP writer.",
                );
            }
        });

        const centralDirectory =
            concatUint8Arrays(centralParts);

        const endOfCentralDirectory =
            concatUint8Arrays([
                uint32(0x06054b50),
                uint16(0),
                uint16(0),
                uint16(files.length),
                uint16(files.length),
                uint32(centralDirectory.length),
                uint32(offset),
                uint16(0),
            ]);

        return new Blob(
            [
                ...zipParts,
                centralDirectory,
                endOfCentralDirectory,
            ],
            {
                type: mimeType,
            },
        );
    }


    function encodeContentChunks(content, encoder) {
        const chunks =
            Array.isArray(content)
                ? content
                : [content];

        return chunks
            .map((chunk) => {
                if (chunk instanceof Uint8Array) {
                    return chunk;
                }

                return encoder.encode(
                    String(chunk),
                );
            })
            .filter((chunk) => chunk.length > 0);
    }


    function uint16(value) {
        const bytes =
            new Uint8Array(2);

        new DataView(bytes.buffer)
            .setUint16(0, value, true);

        return bytes;
    }


    function uint32(value) {
        const bytes =
            new Uint8Array(4);

        new DataView(bytes.buffer)
            .setUint32(0, value >>> 0, true);

        return bytes;
    }


    function concatUint8Arrays(parts) {
        const totalLength =
            parts.reduce(
                (sum, part) =>
                    sum + part.length,
                0,
            );

        const result =
            new Uint8Array(totalLength);

        let offset = 0;

        parts.forEach((part) => {
            result.set(part, offset);
            offset += part.length;
        });

        return result;
    }


    function crc32Chunks(chunks) {
        let crc = 0xffffffff;

        chunks.forEach((chunk) => {
            crc = crc32Update(
                crc,
                chunk,
            );
        });

        return (crc ^ 0xffffffff) >>> 0;
    }


    function crc32Update(crc, bytes) {
        bytes.forEach((byte) => {
            crc =
                CRC32_TABLE[
                    (crc ^ byte) & 0xff
                ] ^
                (crc >>> 8);
        });

        return crc;
    }


    const CRC32_TABLE = (() => {
        const table = [];

        for (let index = 0; index < 256; index += 1) {
            let crc = index;

            for (let bit = 0; bit < 8; bit += 1) {
                crc =
                    crc & 1
                        ? 0xedb88320 ^ (crc >>> 1)
                        : crc >>> 1;
            }

            table[index] =
                crc >>> 0;
        }

        return table;
    })();


    function xmlDeclaration() {
        return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`;
    }


    function xmlEscape(value) {
        return tableValue(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&apos;");
    }


    function timestampForFilename() {
        const now =
            new Date();

        return [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
            "_",
            String(now.getHours()).padStart(2, "0"),
            String(now.getMinutes()).padStart(2, "0"),
            String(now.getSeconds()).padStart(2, "0"),
        ].join("");
    }


    function downloadBlob(blob, filename) {
        const url =
            URL.createObjectURL(blob);

        const link =
            document.createElement("a");

        link.href = url;
        link.download = filename;

        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(
            () => URL.revokeObjectURL(url),
            1000,
        );
    }


    function debounce(func, wait) {
        if (!wait) {
            return func;
        }

        let timeout = null;

        return (...args) => {
            clearTimeout(timeout);

            timeout = setTimeout(
                () => func(...args),
                wait,
            );
        };
    }


    window.ReusableDataTable =
        ReusableDataTable;
})();
