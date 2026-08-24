import { useState, useRef, useEffect } from "react";
import { C, radius, shadow, type } from "../../theme";

/* The ⓘ affordance that lets a dashboard stay honest without being wordy.
 *
 * This project's rule is that a number is never shown without the context that
 * makes it readable — 46% means nothing without the 43.4% baseline beside it. The
 * dashboard obeyed that by printing the context as body text, and ended up reading
 * like a report: verdict banners, two-line chart captions, paragraph-length empty
 * states. All true, all competing with the data for the same space.
 *
 * So the caveats move here rather than being deleted. The delta chip on each card
 * keeps the comparison visible at a glance; this holds the sentence explaining it.
 * Full prose still lives on the Model page, which is for reading rather than
 * scanning.
 *
 * Opens on hover AND on focus/click — hover-only would make every caveat
 * unreachable by keyboard, and on a touch screen unreachable entirely. */
export default function InfoTip({ children, label = "More information", align = "left" }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    const onClick = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <span
      ref={wrap}
      style={{ position: "relative", display: "inline-flex", verticalAlign: "middle", marginLeft: 5 }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        style={{
          width: 14, height: 14, borderRadius: "50%", cursor: "help",
          border: `1px solid ${C.slate300}`, background: "transparent",
          color: C.slate400, fontSize: 9, fontWeight: 700, lineHeight: 1,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          padding: 0,
        }}
      >
        i
      </button>

      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute", top: "calc(100% + 6px)", zIndex: 40,
            [align]: 0,
            width: 260, padding: "10px 12px", textAlign: "left",
            background: C.white, color: C.slate600,
            border: `1px solid ${C.slate200}`, borderRadius: radius.md,
            boxShadow: shadow.md, ...type.body, fontWeight: 400,
            // Long explanations must not clip; the tooltip grows downward and the
            // card grid is `align-items: start` so it overlays rather than pushes.
            whiteSpace: "normal",
          }}
        >
          {children}
        </span>
      )}
    </span>
  );
}
