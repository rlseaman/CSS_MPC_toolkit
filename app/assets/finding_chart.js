/**
 * Double-click reset for the finding-chart Center-RA spinner.
 *
 * The Center-RA input is a `dcc.Input(type='number')`.  Browsers don't
 * fire a useful dblclick on number inputs by default for "reset to
 * default", so we attach our own handler.  Resetting goes through the
 * React-controlled-input dance: use the prototype's value setter to
 * bypass React's internal value cache, then dispatch synthetic input/
 * change events so Dash's onChange handler fires and the new value
 * reaches the server.
 */
(function () {
    "use strict";

    function resetToZero(el) {
        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, "value").set;
        nativeSetter.call(el, "0");
        el.dispatchEvent(new Event("input",  { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        // Debounced dcc.Input flushes on blur — make sure we trigger
        // that path so the server callback fires even when the user
        // hadn't focused the field before double-clicking.
        el.blur();
    }

    function attach() {
        var el = document.getElementById("fc-center-ra");
        if (!el) { setTimeout(attach, 300); return; }
        if (el.dataset.fcDblclickAttached === "1") return;
        el.dataset.fcDblclickAttached = "1";
        el.addEventListener("dblclick", function (e) {
            e.preventDefault();
            e.stopPropagation();
            resetToZero(el);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", attach);
    } else {
        setTimeout(attach, 100);
    }
})();
