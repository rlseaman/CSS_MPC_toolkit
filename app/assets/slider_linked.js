/**
 * Linked range-slider movement for the Planetary Defense Dashboard.
 *
 * When a RangeSlider thumb is focused:
 *   Shift + ← / →   Slide the entire window (both endpoints move by ±1)
 *
 * Visual feedback: both thumbs show a highlight ring while Shift is
 * held on a focused thumb, indicating linked-movement mode.
 */
(function () {
    "use strict";

    // ── React-fiber bridge ──────────────────────────────────────────
    // Walk the React fiber tree from a DOM element to find the Dash
    // component's setProps method and current slider props.

    function getDashSlider(thumbEl) {
        var el = thumbEl;
        while (el && el !== document.body) {
            el = el.parentElement;
            if (!el) return null;

            // Look for a React fiber key on this element
            var fiberKey = null;
            var keys = Object.keys(el);
            for (var i = 0; i < keys.length; i++) {
                if (keys[i].indexOf("__reactFiber$") === 0 ||
                    keys[i].indexOf("__reactInternalInstance$") === 0) {
                    fiberKey = keys[i];
                    break;
                }
            }
            if (!fiberKey) continue;

            // Walk up the fiber tree to find the Dash component with setProps
            var fiber = el[fiberKey];
            while (fiber) {
                var p = fiber.memoizedProps;
                if (p && typeof p.setProps === "function" &&
                    Array.isArray(p.value) && p.value.length === 2) {
                    return {
                        wrapper: el,
                        setProps: p.setProps,
                        value:    p.value,
                        min:      p.min,
                        max:      p.max,
                        step:     p.step || 1
                    };
                }
                fiber = fiber.return;
            }
        }
        return null;
    }

    // ── Shift+Arrow: linked movement ────────────────────────────────
    // Registered at *capture* phase so it fires before the native
    // slider handler (which would move only one thumb).

    document.addEventListener("keydown", function (e) {
        var el = document.activeElement;
        if (!el || el.getAttribute("role") !== "slider") return;
        if (!e.shiftKey) return;
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        var info = getDashSlider(el);
        if (!info) return;

        var delta = (e.key === "ArrowRight" ? 1 : -1) * info.step;
        var newLow  = info.value[0] + delta;
        var newHigh = info.value[1] + delta;

        // Respect slider bounds
        if (newLow < info.min || newHigh > info.max) return;

        e.preventDefault();
        e.stopImmediatePropagation();

        info.setProps({ value: [newLow, newHigh] });
    }, true);  // capture phase

    // ── Visual feedback: linked-mode highlight ──────────────────────
    // Adds a CSS class to the slider wrapper so both thumbs can be
    // styled together (e.g. a subtle glow ring).

    var _shiftHeld = false;
    var _linkedWrapper = null;

    function setLinked(wrapper) {
        if (_linkedWrapper === wrapper) return;
        clearLinked();
        if (wrapper) {
            wrapper.classList.add("slider-linked");
            _linkedWrapper = wrapper;
        }
    }

    function clearLinked() {
        if (_linkedWrapper) {
            _linkedWrapper.classList.remove("slider-linked");
            _linkedWrapper = null;
        }
    }

    // Track Shift state globally so focus events can check it.
    document.addEventListener("keydown", function (e) {
        if (e.key !== "Shift") return;
        _shiftHeld = true;
        var el = document.activeElement;
        if (el && el.getAttribute("role") === "slider") {
            var info = getDashSlider(el);
            if (info) setLinked(info.wrapper);
        }
    });

    document.addEventListener("keyup", function (e) {
        if (e.key === "Shift") {
            _shiftHeld = false;
            clearLinked();
        }
    });

    // Clear Shift state if the window loses focus (user Alt-Tabs away)
    window.addEventListener("blur", function () {
        _shiftHeld = false;
        clearLinked();
    });

    // When a thumb gains focus while Shift is already held, activate
    document.addEventListener("focusin", function (e) {
        if (!_shiftHeld) return;
        var el = e.target;
        if (!el || el.getAttribute("role") !== "slider") return;
        var info = getDashSlider(el);
        if (info) setLinked(info.wrapper);
    });

    // When focus leaves a thumb, deactivate after a brief delay
    // (allows for focus moving between the two thumbs of the same slider)
    document.addEventListener("focusout", function (e) {
        if (!e.target || e.target.getAttribute("role") !== "slider") return;
        setTimeout(function () {
            var el = document.activeElement;
            if (!el || el.getAttribute("role") !== "slider") {
                clearLinked();
            }
        }, 50);
    });
})();
