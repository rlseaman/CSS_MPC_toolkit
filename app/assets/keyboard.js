/**
 * Keyboard shortcuts for the Planetary Defense Dashboard — MPEC Browser tab.
 *
 * Shortcuts are active only when the MPEC Browser tab is selected and no
 * text input is focused.  All navigation writes to a hidden Dash store
 * (mpec-kb-action) which server-side callbacks read.
 *
 * Keys:
 *   ↑ / ↓          Step through MPEC list
 *   Home / End      Jump to first / last MPEC in list
 *   F               Toggle "Follow latest" mode
 *   1-5             Toggle detail accordion sections
 *   O               Cycle observatory site forward
 *   ?               Show / hide keyboard shortcut overlay
 */

(function () {
    "use strict";

    // ── Helpers ──────────────────────────────────────────────────────

    /** Is the MPEC Browser tab currently active? */
    function isMpecTab() {
        var tab = document.querySelector(".nav-tab--selected");
        return tab && tab.textContent.trim().startsWith("MPEC");
    }

    /** Is focus inside a text input, textarea, or contenteditable? */
    function isTyping() {
        var el = document.activeElement;
        if (!el) return false;
        var tag = el.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return true;
        if (el.isContentEditable) return true;
        return false;
    }

    /** Get all MPEC list item divs (direct children of #mpec-list-panel). */
    function getListItems() {
        var panel = document.getElementById("mpec-list-panel");
        if (!panel) return [];
        return Array.from(panel.children).filter(function (el) {
            return el.id && el.id.indexOf("mpec-item") !== -1;
        });
    }

    /** Find the index of the currently selected (blue-bordered) item. */
    function selectedIndex(items) {
        for (var i = 0; i < items.length; i++) {
            var bs = items[i].style.boxShadow || "";
            if (bs.indexOf("5b8def") !== -1) return i;
        }
        return -1;
    }

    /** Scroll an item into view within the list panel. */
    function scrollIntoView(el) {
        if (el && el.scrollIntoView) {
            el.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    }

    // ── Overlay ──────────────────────────────────────────────────────

    var OVERLAY_ID = "kb-shortcut-overlay";

    function buildOverlay() {
        var overlay = document.createElement("div");
        overlay.id = OVERLAY_ID;
        overlay.style.cssText = [
            "position: fixed",
            "top: 50%",
            "left: 50%",
            "transform: translate(-50%, -50%)",
            "background: var(--paper-bg, #1e1e1e)",
            "color: inherit",
            "border: 1px solid var(--hr-color, #444)",
            "border-radius: 10px",
            "padding: 28px 36px",
            "z-index: 10000",
            "font-family: sans-serif",
            "font-size: 14px",
            "box-shadow: 0 8px 32px rgba(0,0,0,0.4)",
            "min-width: 320px",
            "max-width: 420px",
        ].join("; ");

        var title = document.createElement("div");
        title.style.cssText = "font-size: 16px; font-weight: 700; margin-bottom: 16px;";
        title.textContent = "Keyboard Shortcuts";
        overlay.appendChild(title);

        var shortcuts = [
            ["\u2191 / \u2193", "Step through MPEC list"],
            ["Home / End", "Jump to first / last MPEC"],
            ["F", "Toggle \u201cFollow latest\u201d mode"],
            ["1 \u2013 5", "Toggle detail sections"],
            ["O", "Cycle observatory site"],
            ["?", "Show / hide this overlay"],
        ];

        var table = document.createElement("table");
        table.style.cssText = "width: 100%; border-collapse: collapse;";
        shortcuts.forEach(function (pair) {
            var tr = document.createElement("tr");
            var tdKey = document.createElement("td");
            tdKey.style.cssText =
                "padding: 5px 16px 5px 0; font-family: monospace; " +
                "font-weight: 600; white-space: nowrap; width: 110px;";
            tdKey.textContent = pair[0];
            var tdDesc = document.createElement("td");
            tdDesc.style.cssText = "padding: 5px 0;";
            tdDesc.textContent = pair[1];
            tr.appendChild(tdKey);
            tr.appendChild(tdDesc);
            table.appendChild(tr);
        });
        overlay.appendChild(table);

        var hint = document.createElement("div");
        hint.style.cssText =
            "margin-top: 16px; font-size: 12px; color: var(--subtext-color, #888); text-align: center;";
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
        document.body.appendChild(buildOverlay());
    }

    // ── Detail section toggle ────────────────────────────────────────

    function toggleSection(n) {
        // Sections are <details> elements inside #mpec-detail-panel
        var panel = document.getElementById("mpec-detail-panel");
        if (!panel) return;
        var details = panel.querySelectorAll("details");
        // n is 1-based; section 1 = first <details>
        var idx = n - 1;
        if (idx >= 0 && idx < details.length) {
            details[idx].open = !details[idx].open;
        }
    }

    // ── Observatory site cycling ─────────────────────────────────────

    function cycleObsSite() {
        // Find all obs-site-btn buttons inside the obs chart area
        var buttons = document.querySelectorAll('[id*="obs-site-btn"]');
        if (!buttons.length) return;
        var codes = [];
        var currentIdx = -1;
        buttons.forEach(function (btn, i) {
            codes.push(btn);
            // Active button has bold font weight
            if (btn.style.fontWeight === "700") currentIdx = i;
        });
        var nextIdx = (currentIdx + 1) % codes.length;
        codes[nextIdx].click();
    }

    // ── Click "Follow latest" button ─────────────────────────────────

    function clickFollowLatest() {
        var btn = document.getElementById("mpec-follow-btn");
        if (btn) btn.click();
    }

    // ── Main keydown handler ─────────────────────────────────────────

    document.addEventListener("keydown", function (e) {
        // ? works everywhere (toggle overlay) — but not in text inputs
        if (e.key === "?" && !isTyping()) {
            e.preventDefault();
            toggleOverlay();
            return;
        }

        // Escape closes overlay if open
        if (e.key === "Escape") {
            var ov = document.getElementById(OVERLAY_ID);
            if (ov) {
                ov.remove();
                e.preventDefault();
                return;
            }
        }

        // All other shortcuts require MPEC tab active and no typing
        if (!isMpecTab() || isTyping()) return;

        // Ignore when modifier keys are held (allow browser shortcuts)
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        var items, cur, next;

        switch (e.key) {
            case "ArrowUp":
                e.preventDefault();
                items = getListItems();
                cur = selectedIndex(items);
                next = cur > 0 ? cur - 1 : 0;
                if (items[next]) {
                    items[next].click();
                    scrollIntoView(items[next]);
                }
                break;

            case "ArrowDown":
                e.preventDefault();
                items = getListItems();
                cur = selectedIndex(items);
                next = cur < items.length - 1 ? cur + 1 : items.length - 1;
                if (items[next]) {
                    items[next].click();
                    scrollIntoView(items[next]);
                }
                break;

            case "Home":
                e.preventDefault();
                items = getListItems();
                if (items[0]) {
                    items[0].click();
                    scrollIntoView(items[0]);
                }
                break;

            case "End":
                e.preventDefault();
                items = getListItems();
                if (items.length) {
                    var last = items[items.length - 1];
                    last.click();
                    scrollIntoView(last);
                }
                break;

            case "f":
            case "F":
                e.preventDefault();
                clickFollowLatest();
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
                e.preventDefault();
                toggleSection(parseInt(e.key, 10));
                break;
        }
    });
})();
