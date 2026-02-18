/**
 * Keyboard shortcuts for the Planetary Defense Dashboard — MPEC Browser tab.
 *
 * Shortcuts are active only when the MPEC Browser tab is selected and no
 * text input is focused.  List navigation writes to a hidden dcc.Input
 * (#mpec-kb-nav) which a server callback reads.
 *
 * Keys:
 *   ↑ / ↓          Step through MPEC list
 *   [ / ]           Jump to first / last MPEC (Mac Home/End alternative)
 *   Home / End      Jump to first / last MPEC
 *   F               Toggle Follow / Pin mode
 *   1-8             Toggle detail accordion sections
 *   O               Cycle observatory site forward
 *   ?               Show / hide keyboard shortcut overlay
 */

(function () {
    "use strict";

    // ── Helpers ──────────────────────────────────────────────────────

    function isMpecTab() {
        var tab = document.querySelector(".nav-tab--selected");
        return tab && tab.textContent.trim().startsWith("MPEC");
    }

    function isTyping() {
        var el = document.activeElement;
        if (!el) return false;
        var tag = el.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return true;
        if (el.isContentEditable) return true;
        if (el.getAttribute("role") === "slider") return true;
        if (el.classList && el.classList.contains("dash-slider-thumb")) return true;
        return false;
    }

    function getListItems() {
        var panel = document.getElementById("mpec-list-panel");
        if (!panel) return [];
        return Array.from(panel.querySelectorAll("[data-path]"));
    }

    // Track the last keyboard-navigated index so rapid keypresses
    // don't have to wait for the async Dash style update round-trip.
    var _kbIndex = -1;

    /** Find the currently selected item.  Checks the DOM style first
     *  (works after mouse clicks), falls back to _kbIndex (works during
     *  rapid keyboard nav before the server round-trip completes). */
    function selectedIndex(items) {
        // DOM check: selected item has "inset" in its boxShadow.
        // (Browsers normalize #5b8def → rgb(...) so we can't match hex.)
        for (var i = 0; i < items.length; i++) {
            var bs = items[i].style.boxShadow || "";
            if (bs.indexOf("inset") !== -1) return i;
        }
        // Fallback: use last keyboard-navigated index
        if (_kbIndex >= 0 && _kbIndex < items.length) return _kbIndex;
        return -1;
    }

    function scrollIntoView(el) {
        if (el && el.scrollIntoView) {
            el.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    }

    // ── Hidden-input bridge to Dash ──────────────────────────────────
    //
    // dcc.Input in Dash 4.0 renders an <input> inside a wrapper div.
    // We find the actual <input>, use the native HTMLInputElement value
    // setter (bypasses React's controlled-input guard), then dispatch
    // a native "input" event so React's onChange fires and Dash sees
    // the new value.

    var _nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value"
    ).set;

    /** Find the real <input> element for a Dash dcc.Input by id. */
    function findDashInput(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        if (el.tagName === "INPUT") return el;
        // dcc.Input wraps the <input> in a div
        return el.querySelector("input") || null;
    }

    /** Set a Dash dcc.Input's value and trigger its callback. */
    function setDashInputValue(id, value) {
        var input = findDashInput(id);
        if (!input) return false;
        _nativeSetter.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
    }

    /** Navigate the MPEC list to the item at `idx`. */
    function navigateTo(items, idx) {
        if (idx < 0 || idx >= items.length) return;
        var el = items[idx];
        var path = el.getAttribute("data-path");
        if (!path) return;
        _kbIndex = idx;
        // Append timestamp so repeated nav to the same item still
        // triggers a change (React deduplicates identical values).
        setDashInputValue("mpec-kb-nav", path + "|" + Date.now());
        scrollIntoView(el);
    }

    // ── Follow / Pin toggle ──────────────────────────────────────────

    function isAutoFollowing() {
        var label = document.getElementById("mpec-auto-label");
        return label && label.textContent.indexOf("Following") !== -1;
    }

    function toggleFollow() {
        if (isAutoFollowing()) {
            // Currently following — pin to current selection.
            // Arrow-down then arrow-up would also pin, but this is
            // more explicit.  Write a special command to the hidden
            // input; the server callback treats "PIN" as a no-path
            // auto-mode-off signal.
            setDashInputValue("mpec-kb-nav", "PIN|" + Date.now());
        } else {
            // Currently pinned — click "Follow latest" button
            var btn = document.getElementById("mpec-follow-btn");
            if (btn) btn.click();
        }
    }

    // ── Overlay ──────────────────────────────────────────────────────

    var OVERLAY_ID = "kb-shortcut-overlay";

    function buildOverlay() {
        var container = document.getElementById("page-container");
        var cs = container ? getComputedStyle(container) : null;
        var bgColor = cs
            ? cs.getPropertyValue("--paper-bg").trim() || "#1e1e1e"
            : "#1e1e1e";
        var fgColor = cs
            ? cs.getPropertyValue("color").trim() || "#e0e0e0"
            : "#e0e0e0";
        var borderColor = cs
            ? cs.getPropertyValue("--hr-color").trim() || "#444"
            : "#444";
        var subColor = cs
            ? cs.getPropertyValue("--subtext-color").trim() || "#888"
            : "#888";

        var overlay = document.createElement("div");
        overlay.id = OVERLAY_ID;
        overlay.style.cssText = [
            "position: fixed",
            "top: 50%",
            "left: 50%",
            "transform: translate(-50%, -50%)",
            "background: " + bgColor,
            "color: " + fgColor,
            "border: 1px solid " + borderColor,
            "border-radius: 10px",
            "padding: 28px 36px",
            "z-index: 10000",
            "font-family: sans-serif",
            "font-size: 14px",
            "box-shadow: 0 8px 32px rgba(0,0,0,0.4)",
            "min-width: 340px",
            "max-width: 440px",
        ].join("; ");

        var title = document.createElement("div");
        title.style.cssText =
            "font-size: 16px; font-weight: 700; margin-bottom: 16px; color: " + fgColor + ";";
        title.textContent = "Keyboard Shortcuts";
        overlay.appendChild(title);

        var shortcuts = [
            ["\u2190 / \u2192",    "Switch tabs"],
            ["\u2191 / \u2193",    "Step through MPEC list"],
            ["[ / ]",              "Jump to first / last MPEC"],
            ["F",                  "Toggle Follow / Pin mode"],
            ["1 \u2013 8",        "Toggle detail sections"],
            ["O",                  "Cycle observatory site"],
            ["?",                  "Show / hide this overlay"],
        ];

        var table = document.createElement("table");
        table.style.cssText = "width: 100%; border-collapse: collapse;";
        shortcuts.forEach(function (pair) {
            var tr = document.createElement("tr");
            var tdKey = document.createElement("td");
            tdKey.style.cssText =
                "padding: 5px 16px 5px 0; font-family: monospace; " +
                "font-weight: 600; white-space: nowrap; width: 110px; color: " + fgColor + ";";
            tdKey.textContent = pair[0];
            var tdDesc = document.createElement("td");
            tdDesc.style.cssText = "padding: 5px 0; color: " + fgColor + ";";
            tdDesc.textContent = pair[1];
            tr.appendChild(tdKey);
            tr.appendChild(tdDesc);
            table.appendChild(tr);
        });
        overlay.appendChild(table);

        var hint = document.createElement("div");
        hint.style.cssText =
            "margin-top: 16px; font-size: 12px; color: " + subColor + "; text-align: center;";
        hint.textContent = "Press ? or Escape to close";
        overlay.appendChild(hint);

        return overlay;
    }

    function toggleOverlay() {
        var existing = document.getElementById(OVERLAY_ID);
        if (existing) {
            existing.remove();
            return;
        }
        var container = document.getElementById("page-container") || document.body;
        container.appendChild(buildOverlay());
    }

    // ── Section state persistence ─────────────────────────────────────

    /** Read the current open/closed state of all 8 detail sections. */
    function readSectionState() {
        var state = {};
        for (var i = 0; i < 8; i++) {
            var el = document.getElementById("mpec-section-" + i);
            state[String(i)] = el ? el.open : false;
        }
        return state;
    }

    /** Write current section state to the hidden Dash input. */
    function persistSectionState() {
        var state = readSectionState();
        setDashInputValue(
            "mpec-section-state-input",
            JSON.stringify(state) + "|" + Date.now()
        );
    }

    /** Apply saved state from store to <details> elements. */
    function applySectionState() {
        // Read state from the hidden input (which mirrors the store).
        // The store value is set by the server callback; the hidden
        // input holds the latest JSON we wrote.  On first load, read
        // from sessionStorage directly (Dash stores use it).
        var stored = null;
        try {
            var raw = sessionStorage.getItem("mpec-section-state");
            if (raw) stored = JSON.parse(raw);
        } catch (e) { /* ignore */ }
        if (!stored) return;

        for (var i = 0; i < 8; i++) {
            var el = document.getElementById("mpec-section-" + i);
            if (el && stored.hasOwnProperty(String(i))) {
                el.open = stored[String(i)];
            }
        }
    }

    // Listen for toggle events on detail sections to persist state.
    // We use event delegation on the detail panel.
    document.addEventListener("toggle", function (e) {
        var target = e.target;
        if (target && target.tagName === "DETAILS" &&
            target.id && target.id.indexOf("mpec-section-") === 0) {
            persistSectionState();
        }
    }, true);  // useCapture — toggle doesn't bubble

    // MutationObserver: when Dash re-renders the detail panel (new MPEC
    // selected), the server-side callback already sets open= from the
    // store.  But as a safety net, also apply from sessionStorage after
    // the DOM updates.
    var _detailObserver = new MutationObserver(function (mutations) {
        // Check if any mutation added mpec-section-* elements
        for (var i = 0; i < mutations.length; i++) {
            var added = mutations[i].addedNodes;
            for (var j = 0; j < added.length; j++) {
                if (added[j].nodeType === 1) {
                    // A new element was added — likely a re-render
                    applySectionState();
                    return;
                }
            }
        }
    });

    // Start observing once the detail panel exists
    function startObserver() {
        var panel = document.getElementById("mpec-detail-panel");
        if (panel) {
            _detailObserver.observe(panel, { childList: true, subtree: true });
        } else {
            // Retry after a short delay (page may still be loading)
            setTimeout(startObserver, 500);
        }
    }
    startObserver();

    // ── Detail section toggle ────────────────────────────────────────

    function toggleSection(n) {
        var panel = document.getElementById("mpec-detail-panel");
        if (!panel) return;
        var idx = n - 1;
        var el = document.getElementById("mpec-section-" + idx);
        if (el) {
            el.open = !el.open;
            // toggle event fires automatically; persistence handled
            // by the toggle event listener above
        }
    }

    // ── Observatory site cycling ─────────────────────────────────────

    function cycleObsSite() {
        var buttons = document.querySelectorAll('[id*="obs-site-btn"]');
        if (!buttons.length) return;
        var arr = Array.from(buttons);
        var currentIdx = -1;
        arr.forEach(function (btn, i) {
            if (btn.style.fontWeight === "700") currentIdx = i;
        });
        var nextIdx = (currentIdx + 1) % arr.length;
        arr[nextIdx].click();
    }

    // ── Main keydown handler ─────────────────────────────────────────

    document.addEventListener("keydown", function (e) {
        if (e.key === "?" && !isTyping()) {
            e.preventDefault();
            toggleOverlay();
            return;
        }

        if (e.key === "Escape") {
            var ov = document.getElementById(OVERLAY_ID);
            if (ov) {
                ov.remove();
                e.preventDefault();
                return;
            }
        }

        // ── Left/Right arrows: switch tabs (all tabs, not just MPEC) ──
        if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !isTyping()
            && !e.ctrlKey && !e.metaKey && !e.altKey) {
            var tabs = Array.from(document.querySelectorAll(".nav-tab"));
            if (tabs.length > 1) {
                var curTab = -1;
                tabs.forEach(function (t, i) {
                    if (t.classList.contains("nav-tab--selected")) curTab = i;
                });
                var nextTab = curTab;
                if (e.key === "ArrowLeft" && curTab > 0) nextTab = curTab - 1;
                if (e.key === "ArrowRight" && curTab < tabs.length - 1) nextTab = curTab + 1;
                if (nextTab !== curTab) {
                    e.preventDefault();
                    tabs[nextTab].click();
                }
            }
            return;
        }

        if (!isMpecTab() || isTyping()) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        var items, cur, next;

        switch (e.key) {
            case "ArrowUp":
                e.preventDefault();
                items = getListItems();
                cur = selectedIndex(items);
                next = cur > 0 ? cur - 1 : 0;
                navigateTo(items, next);
                break;

            case "ArrowDown":
                e.preventDefault();
                items = getListItems();
                cur = selectedIndex(items);
                next = cur < items.length - 1 ? cur + 1 : items.length - 1;
                navigateTo(items, next);
                break;

            case "Home":
            case "[":
                e.preventDefault();
                items = getListItems();
                navigateTo(items, 0);
                break;

            case "End":
            case "]":
                e.preventDefault();
                items = getListItems();
                navigateTo(items, items.length - 1);
                break;

            case "f":
            case "F":
                e.preventDefault();
                toggleFollow();
                break;

            case "o":
            case "O":
                e.preventDefault();
                cycleObsSite();
                break;

            case "1":
            case "2":
            case "3":
            case "4":
            case "5":
            case "6":
            case "7":
            case "8":
                e.preventDefault();
                toggleSection(parseInt(e.key, 10));
                break;
        }
    });

    // ── Search box ────────────────────────────────────────────────────
    // Pure client-side search: on each keystroke, find the first list
    // item whose designation or MPEC ID matches and navigate to it
    // (equivalent to using arrow keys).

    /**
     * Convert an MPEC ID like "2026-C105" or "1996-W06" to an MPC archive path.
     * Returns "" if the input doesn't look like a valid MPEC ID.
     */
    function mpecIdToPath(id) {
        // Strip optional "MPEC " prefix
        id = id.replace(/^MPEC\s+/i, "").trim();
        var m = id.match(/^(\d{4})-([A-Z])(\d+)$/i);
        if (!m) return "";
        var year = parseInt(m[1], 10);
        var halfMonth = m[2].toUpperCase();
        var num = parseInt(m[3], 10);
        if (year < 1800 || year > 2099) return "";
        // Century letter: 1800→I, 1900→J, 2000→K
        var centuryLetter = String.fromCharCode(65 + Math.floor(year / 100) - 10);
        var yy = ("0" + (year % 100)).slice(-2);
        var packedYear = centuryLetter + yy;
        // Pack number: 1-99 → two digits, 100+ → letter+digit
        var packedNum;
        if (num <= 99) {
            packedNum = ("0" + num).slice(-2);
        } else {
            var hundreds = Math.floor((num - 100) / 10);
            var ones = num % 10;
            if (hundreds > 25) return "";  // beyond Z
            packedNum = String.fromCharCode(65 + hundreds) + ones;
        }
        var packed = packedYear + halfMonth + packedNum;
        return "/mpec/" + packedYear + "/" + packed + ".html";
    }

    function doSearch(query, submit) {
        if (!query) return;
        var q = query.trim().toUpperCase();
        if (!q) return;
        var items = getListItems();
        // First: scan list items for a text match
        for (var i = 0; i < items.length; i++) {
            var text = (items[i].textContent || "").toUpperCase();
            if (text.indexOf(q) !== -1) {
                navigateTo(items, i);
                return;
            }
        }
        // No list match — try interpreting query as an MPEC ID
        var path = mpecIdToPath(query.trim());
        if (path) {
            // Write directly to mpec-kb-nav to trigger the server callback
            // (same mechanism as navigateTo but without a list element)
            setDashInputValue("mpec-kb-nav", path + "|" + Date.now());
            return;
        }
        // Not an MPEC ID — send to server API for designation/name lookup
        // Only on Enter (submit=true) to avoid firing on every keystroke
        if (!submit) return;
        setDashInputValue("mpec-desig-search",
                          query.trim() + "|" + Date.now());
    }

    function initSearch() {
        var wrapper = document.getElementById("mpec-search");
        if (!wrapper) {
            setTimeout(initSearch, 500);
            return;
        }
        // dcc.Input renders a wrapper div; the actual <input> is inside
        var input = wrapper.querySelector("input") || wrapper;
        input.addEventListener("input", function () {
            doSearch(input.value, false);
        });
        input.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                input.value = "";
                input.blur();
                e.preventDefault();
            }
            // Enter: submit search (includes designation API lookup)
            if (e.key === "Enter") {
                e.preventDefault();
                doSearch(input.value, true);
            }
        });
    }
    initSearch();

    // ── MPEC navigation buttons ────────────────────────────────────────
    // Prev, Next, Earliest: write target path to mpec-kb-nav.
    // Most Recent: click "Follow latest" to restore auto mode.
    // If the target is in the visible list, scroll it into view.

    function navigateToPath(path) {
        if (!path) return;
        setDashInputValue("mpec-kb-nav", path + "|" + Date.now());
        // Scroll matching list item into view
        var items = getListItems();
        for (var i = 0; i < items.length; i++) {
            if (items[i].getAttribute("data-path") === path) {
                _kbIndex = i;
                scrollIntoView(items[i]);
                break;
            }
        }
    }

    document.addEventListener("click", function (e) {
        // Most Recent — re-engage auto mode via Follow latest button
        if (e.target.closest("#mpec-nav-latest")) {
            var btn = document.getElementById("mpec-follow-btn");
            if (btn) btn.click();
            // Scroll list to top
            var items = getListItems();
            if (items.length) {
                _kbIndex = 0;
                scrollIntoView(items[0]);
            }
            return;
        }
        // Random — generate a random MPEC path from entire history
        if (e.target.closest("#mpec-nav-random")) {
            // MPEC range: 1993-S01 through current date
            var now = new Date();
            var curYear = now.getFullYear();
            // Half-month letters: A(Jan 1-15)..Y(Dec 16-31), skip I
            var letters = "ABCDEFGHJKLMNOPQRSTUVWXY";
            // Current half-month index (0-based)
            var curMonth = now.getMonth();  // 0-11
            var curHalf = curMonth * 2 + (now.getDate() > 15 ? 1 : 0);
            // Total half-months since 1993-S (Sep 16-30 = index 17)
            var startHM = (1993 - 1993) * 24 + 17;  // = 17
            var endHM = (curYear - 1993) * 24 + curHalf;
            var randHM = startHM + Math.floor(Math.random() * (endHM - startHM + 1));
            var year = 1993 + Math.floor(randHM / 24);
            var hmIdx = randHM % 24;
            var halfMonth = letters[hmIdx];
            // Random number: 1-60 covers most half-months
            var num = 1 + Math.floor(Math.random() * 60);
            var id = year + "-" + halfMonth + num;
            var path = mpecIdToPath(id);
            if (path) navigateToPath(path);
            return;
        }
        // Prev, Next, Earliest — navigate by path
        var navBtn = e.target.closest(
            "#mpec-nav-prev, #mpec-nav-next, #mpec-nav-earliest");
        if (!navBtn) return;
        var path = navBtn.getAttribute("data-path");
        if (path) navigateToPath(path);
    });

    // Date picker: navigate to first MPEC of the selected date.
    // Uses event delegation on the detail panel since the date input
    // is recreated on each MPEC navigation.
    document.addEventListener("change", function(e) {
        if (!e.target || e.target.id !== "mpec-nav-date") return;
        var date = e.target.value;
        if (!date) return;
        var parts = date.split("-");
        var year = parseInt(parts[0], 10);
        var month = parseInt(parts[1], 10);
        var day = parseInt(parts[2], 10);
        var letters = "ABCDEFGHJKLMNOPQRSTUVWXY";
        var hmIdx = (month - 1) * 2 + (day > 15 ? 1 : 0);
        var halfMonth = letters[hmIdx];
        var id = year + "-" + halfMonth + "1";
        var path = mpecIdToPath(id);
        if (path) navigateToPath(path);
    });
})();
