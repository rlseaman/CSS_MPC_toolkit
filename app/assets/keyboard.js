/**
 * Keyboard shortcuts for the Planetary Defense Dashboard — MPEC Browser tab.
 *
 * Shortcuts are active only when the MPEC Browser tab is selected and no
 * text input is focused.  Navigation uses dash_clientside.set_props() to
 * update Dash stores directly (DOM .click() does not trigger React state).
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

    /** Get all MPEC list item divs (children of #mpec-list-panel with
     *  a data-path attribute). */
    function getListItems() {
        var panel = document.getElementById("mpec-list-panel");
        if (!panel) return [];
        return Array.from(panel.querySelectorAll("[data-path]"));
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

    /** Navigate to a specific list item by index.  Uses Dash's
     *  set_props to update the selected-path store (and disable auto
     *  mode), which triggers the existing server-side callbacks. */
    function navigateTo(items, idx) {
        if (idx < 0 || idx >= items.length) return;
        var el = items[idx];
        var path = el.getAttribute("data-path");
        if (!path) return;
        // Update Dash stores directly through the renderer API
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props("mpec-selected-path",
                                              { data: path });
            window.dash_clientside.set_props("mpec-auto-mode",
                                              { data: false });
        }
        scrollIntoView(el);
    }

    // ── Overlay ──────────────────────────────────────────────────────

    var OVERLAY_ID = "kb-shortcut-overlay";

    function buildOverlay() {
        // Read theme colors from #page-container so the overlay matches
        var container = document.getElementById("page-container");
        var cs = container
            ? getComputedStyle(container)
            : null;
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
            "min-width: 320px",
            "max-width: 420px",
        ].join("; ");

        var title = document.createElement("div");
        title.style.cssText = "font-size: 16px; font-weight: 700; margin-bottom: 16px; color: " + fgColor + ";";
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
        // Append inside #page-container so theme CSS variables apply
        var container = document.getElementById("page-container") || document.body;
        container.appendChild(buildOverlay());
    }

    // ── Detail section toggle ────────────────────────────────────────

    function toggleSection(n) {
        var panel = document.getElementById("mpec-detail-panel");
        if (!panel) return;
        var details = panel.querySelectorAll("details");
        var idx = n - 1;
        if (idx >= 0 && idx < details.length) {
            details[idx].open = !details[idx].open;
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

    // ── Click "Follow latest" button ─────────────────────────────────

    function clickFollowLatest() {
        var btn = document.getElementById("mpec-follow-btn");
        if (btn) btn.click();
    }

    // ── Main keydown handler ─────────────────────────────────────────

    document.addEventListener("keydown", function (e) {
        // ? works on MPEC tab — but not in text inputs
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
                e.preventDefault();
                items = getListItems();
                navigateTo(items, 0);
                break;

            case "End":
                e.preventDefault();
                items = getListItems();
                navigateTo(items, items.length - 1);
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
