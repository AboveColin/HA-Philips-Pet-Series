/**
 * Lovelace cards bundled with the Philips Pet Series integration.
 *
 * The integration serves this file and registers it as a Lovelace resource, so
 * no manual resource entry is needed.  Cards resolve their entities through the
 * `philips_pet_series/devices` websocket command rather than guessing entity
 * IDs, so renaming an entity does not break a dashboard.
 *
 * Everything above the `--- cards ---` marker is the shared house style: design
 * tokens, the hero header and the common building blocks.  A new card should
 * reuse `sharedStyles` and `renderHero` rather than inventing its own, so the
 * whole set stays recognisably one family.
 */

// Home Assistant ships its own Lit; borrowing it off an existing element keeps
// this file buildless and avoids loading a second copy of Lit into the page.
const HaPanel =
  customElements.get("ha-panel-lovelace") ||
  (await customElements.whenDefined("ha-panel-lovelace"),
  customElements.get("ha-panel-lovelace"));
const LitElement = Object.getPrototypeOf(HaPanel);
const { html, css } = LitElement.prototype;
// Lit's `nothing` sentinel is not reachable this way; an empty template renders
// the same and needs no import.
const nothing = html``;

// The Material Design "paw" glyph.  Used as the family mark: once at reading
// size in the hero, once oversized and faint as the hero's watermark.
const PAW_PATH =
  "M8.35,3C9.53,2.83 10.78,4.12 11.14,5.9C11.5,7.67 10.85,9.25 9.67,9.43C8.5," +
  "9.61 7.24,8.32 6.87,6.54C6.5,4.77 7.17,3.19 8.35,3M15.5,3C16.68,3.19 17.35," +
  "4.77 17,6.54C16.62,8.32 15.37,9.61 14.19,9.43C13,9.25 12.35,7.67 12.72,5.9C" +
  "13.08,4.12 14.33,2.83 15.5,3M3,7.6C4.14,7.11 5.69,8 6.5,9.55C7.26,11.13 7," +
  "12.79 5.87,13.28C4.74,13.77 3.2,12.89 2.41,11.32C1.62,9.75 1.9,8.08 3,7.6M" +
  "21,7.6C22.1,8.08 22.38,9.75 21.59,11.32C20.8,12.89 19.26,13.77 18.13,13.28C" +
  "17,12.79 16.74,11.13 17.5,9.55C18.31,8 19.86,7.11 21,7.6M19.33,18.38C19.37," +
  "19.32 18.65,20.36 17.79,20.75C16,21.57 13.88,19.87 11.89,19.87C9.9,19.87 " +
  "7.76,21.64 6,20.75C5,20.26 4.31,19 4.44,17.94C4.62,16.46 6.41,15.72 7.5," +
  "14.7C8.9,13.42 9.85,10.85 11.89,10.85C13.93,10.85 14.95,13.38 16.28,14.7C" +
  "17.4,15.81 19.26,16.75 19.33,18.38Z";

/**
 * The house colours, as the `[r, g, b]` a colour picker speaks.
 *
 * These mirror the fallbacks in the `:host` block immediately below, and exist
 * so the card editor can show a swatch of what the card actually looks like
 * rather than an empty box that renders as black.  Change one, change both.
 */
const DEFAULT_COLOURS = {
  hero_start: [14, 59, 71], // #0e3b47
  hero_end: [31, 122, 111], // #1f7a6f
  accent_start: [255, 157, 47], // #ff9d2f
  accent_end: [255, 95, 109], // #ff5f6d
};

/**
 * The house style.
 *
 * Every token is a `--pps-*` custom property with a fallback, so a user can
 * restyle the whole set from their theme without touching this file, and a new
 * card picks up their choices for free.
 */
const sharedStyles = css`
  :host {
    --pps-hero-from: var(--pps-hero-start, #0e3b47);
    --pps-hero-to: var(--pps-hero-end, #1f7a6f);
    --pps-accent-from: var(--pps-accent-start, #ff9d2f);
    --pps-accent-to: var(--pps-accent-end, #ff5f6d);
    --pps-accent-solid: var(--pps-accent, #ff8347);
    --pps-online: var(--pps-online-color, #4ade80);
    --pps-offline: var(--pps-offline-color, #f87171);
    --pps-radius: var(--pps-card-radius, 18px);
    --pps-gap: 18px;
    --pps-hero-text: #ffffff;
  }

  ha-card {
    /* The hero bleeds to the card edge, so padding lives on the sections. */
    padding: 0;
    overflow: hidden;
    border-radius: var(--pps-radius);
  }

  /* --- hero ------------------------------------------------------------ */

  .hero {
    position: relative;
    overflow: hidden;
    padding: 16px 18px;
    background: linear-gradient(
      135deg,
      var(--pps-hero-from) 0%,
      var(--pps-hero-to) 100%
    );
    color: var(--pps-hero-text);
    display: flex;
    align-items: center;
    gap: 12px;
    transition: filter 0.3s ease;
  }
  /* An unreachable device should be obvious before you read a word of it. */
  .hero.offline {
    filter: saturate(0.3);
  }

  /* Oversized paw, mostly off-canvas: the family mark, quiet enough to read
     over.  Kept low and right of the status pill so the two never overlap. */
  .hero .watermark {
    position: absolute;
    right: -34px;
    bottom: -52px;
    width: 148px;
    height: 148px;
    opacity: 0.07;
    fill: currentColor;
    pointer-events: none;
  }

  /* Denser layouts drop decoration, never information: the watermark, the model
     line and slices of padding go, every number stays. */
  :host([layout="compact"]) .hero,
  :host([layout="slim"]) .hero {
    padding: 11px 14px;
  }
  :host([layout="compact"]) .hero .watermark,
  :host([layout="slim"]) .hero .watermark,
  :host([layout="compact"]) .hero .subtitle,
  :host([layout="slim"]) .hero .subtitle {
    display: none;
  }
  :host([layout="compact"]) .hero .mark,
  :host([layout="slim"]) .hero .mark {
    width: 30px;
    height: 30px;
    border-radius: 9px;
  }
  :host([layout="compact"]) .hero .mark svg,
  :host([layout="slim"]) .hero .mark svg {
    width: 18px;
    height: 18px;
  }
  :host([layout="compact"]) .section {
    padding: 13px var(--pps-gap);
  }
  :host([layout="slim"]) .hero .title {
    font-size: 1rem;
  }
  :host([layout="slim"]) .section {
    padding: 11px 14px;
  }

  .hero .mark {
    flex: none;
    width: 38px;
    height: 38px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.16);
    display: grid;
    place-items: center;
  }
  .hero .mark svg {
    width: 22px;
    height: 22px;
    fill: currentColor;
  }

  .hero .titles {
    min-width: 0;
    flex: 1;
  }
  .hero .title {
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hero .subtitle {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    opacity: 0.65;
    margin-top: 2px;
  }

  .pill {
    flex: none;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 11px 5px 9px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.18);
    font-size: 0.74rem;
    font-weight: 500;
    cursor: pointer;
    z-index: 1;
  }
  .pill .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--pps-offline);
    box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.22);
  }
  .pill.online .dot {
    background: var(--pps-online);
    box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.22);
  }

  /* --- sections -------------------------------------------------------- */

  .section {
    padding: var(--pps-gap);
  }
  .section + .section {
    border-top: 1px solid var(--divider-color);
  }

  .label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--secondary-text-color);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    padding: 3px 9px;
    border-radius: 999px;
    color: var(--secondary-text-color);
    background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
  }

  /* --- stat grid ------------------------------------------------------- */

  /* Small labelled readouts, used wherever a card has facts rather than
     controls.  Auto-fit means the same markup works in a wide column and in a
     narrow one without a second layout. */
  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
    gap: 10px;
  }
  .stat {
    padding: 10px 11px;
    border-radius: 11px;
    background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
    cursor: pointer;
    min-width: 0;
  }
  .stat .k {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--secondary-text-color);
  }
  .stat .k ha-icon {
    --mdc-icon-size: 14px;
  }
  .stat .v {
    margin-top: 3px;
    font-size: 0.98rem;
    color: var(--primary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .stat .v.good {
    color: var(--pps-online);
  }
  .stat .v.bad {
    color: var(--error-color);
  }

  /* --- toggle row ------------------------------------------------------- */

  /* Round icon toggles, lit in the accent when the thing is on. */
  .toggles {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .toggles .toggle {
    flex: none;
    width: 42px;
    height: 42px;
    border: none;
    border-radius: 50%;
    display: grid;
    place-items: center;
    cursor: pointer;
    color: var(--secondary-text-color);
    background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
    transition:
      background 0.18s ease,
      color 0.18s ease;
  }
  .toggles .toggle ha-icon {
    --mdc-icon-size: 21px;
  }
  .toggles .toggle.on {
    color: #fff;
    background: linear-gradient(
      120deg,
      var(--pps-accent-from) 0%,
      var(--pps-accent-to) 100%
    );
  }
  .toggles .toggle[disabled] {
    opacity: 0.45;
    cursor: default;
  }

  /* --- primary action -------------------------------------------------- */

  .cta {
    width: 100%;
    padding: 13px;
    border: 2px solid transparent;
    border-radius: 13px;
    background: linear-gradient(
      100deg,
      var(--pps-accent-from) 0%,
      var(--pps-accent-to) 100%
    );
    color: #fff;
    font-size: 0.98rem;
    font-weight: 600;
    font-family: inherit;
    letter-spacing: 0.01em;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    transition:
      filter 0.15s ease,
      transform 0.08s ease;
  }
  .cta svg {
    width: 19px;
    height: 19px;
    fill: currentColor;
  }
  .cta:hover {
    filter: brightness(1.07);
  }
  .cta:active {
    transform: scale(0.985);
  }
  /* Armed reads as an outline rather than a shade of the same fill, so the
     difference survives a glance and a colour-blind reader. */
  .cta.armed {
    background: transparent;
    border-color: var(--pps-accent-solid);
    color: var(--pps-accent-solid);
  }
  .cta[disabled] {
    opacity: 0.55;
    cursor: default;
  }

  /* --- problems -------------------------------------------------------- */

  .problems {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .problem {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 9px 11px;
    border-radius: 10px;
    border-left: 3px solid var(--error-color);
    background: color-mix(in srgb, var(--error-color) 12%, transparent);
    color: var(--primary-text-color);
    font-size: 0.87rem;
    cursor: pointer;
  }
  .problem ha-icon {
    --mdc-icon-size: 19px;
    color: var(--error-color);
  }

  .footer {
    padding: 11px var(--pps-gap);
    border-top: 1px solid var(--divider-color);
    font-size: 0.78rem;
    color: var(--secondary-text-color);
    display: flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
  }
  .footer ha-icon {
    --mdc-icon-size: 15px;
  }

  .placeholder {
    padding: var(--pps-gap);
    color: var(--secondary-text-color);
  }

  /* --- motion ----------------------------------------------------------- */

  /* Every animation is gated on the [animate] attribute, so switching them off
     removes them rather than running them at zero duration. */

  @keyframes pps-rise {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
  }
  @keyframes pps-fade-left {
    from {
      opacity: 0;
      transform: translateX(-6px);
    }
  }
  @keyframes pps-pulse-ring {
    70% {
      box-shadow: 0 0 0 7px rgba(248, 113, 113, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(248, 113, 113, 0);
    }
  }
  @keyframes pps-breathe {
    50% {
      opacity: 0.55;
    }
  }
  @keyframes pps-sweep {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(100%);
    }
  }

  :host([animate]) ha-card {
    animation: pps-rise 0.36s cubic-bezier(0.22, 1, 0.36, 1) both;
  }

  /* The schedule reads left to right, so it arrives that way. */
  :host([animate]) .chip {
    animation: pps-fade-left 0.3s ease-out both;
    animation-delay: calc(var(--i, 0) * 45ms + 120ms);
  }

  :host([animate]) .problem {
    animation: pps-fade-left 0.28s ease-out both;
  }

  /* Only the state worth looking at pulses.  A permanently throbbing "all is
     well" dot is just noise. */
  :host([animate]) .pill:not(.online) .dot {
    animation: pps-pulse-ring 1.9s ease-out infinite;
  }

  :host([animate]) .cta.armed {
    animation: pps-breathe 1.5s ease-in-out infinite;
  }

  /* A sweep across the button while the service call is in flight: it says
     "working" without claiming to know how far along it is. */
  :host([animate]) .cta.busy {
    position: relative;
    overflow: hidden;
  }
  :host([animate]) .cta.busy::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.28),
      transparent
    );
    animation: pps-sweep 1.1s linear infinite;
  }

  /* The operating system's preference outranks the card's setting. */
  @media (prefers-reduced-motion: reduce) {
    :host([animate]) *,
    :host([animate]) *::after,
    :host([animate]) *::before {
      animation: none !important;
      transition: none !important;
    }
  }
`;

/** The header every Philips Pet Series card wears. */
const renderHero = ({ title, subtitle, online, onStatusClick }) => html`
  <div class="hero ${online === false ? "offline" : ""}">
    <svg class="watermark" viewBox="0 0 24 24">
      <path d=${PAW_PATH}></path>
    </svg>
    <div class="mark">
      <svg viewBox="0 0 24 24"><path d=${PAW_PATH}></path></svg>
    </div>
    <div class="titles">
      <div class="title">${title}</div>
      ${subtitle ? html`<div class="subtitle">${subtitle}</div>` : nothing}
    </div>
    ${online === undefined
      ? nothing
      : html`<div
          class="pill ${online ? "online" : "offline"}"
          @click=${onStatusClick}
        >
          <span class="dot"></span>${online ? "Online" : "Offline"}
        </div>`}
  </div>
`;

/** Format a Date as a locale time, e.g. "22:00". */
const formatTime = (hass, date) =>
  date.toLocaleTimeString(hass.locale?.language || navigator.language, {
    hour: "2-digit",
    minute: "2-digit",
  });

/** Format a Date relative to now, e.g. "in 2 hours" / "4 hours ago". */
const formatRelative = (hass, date) => {
  const language = hass.locale?.language || navigator.language;
  const relative = new Intl.RelativeTimeFormat(language, { numeric: "auto" });
  const seconds = (date.getTime() - Date.now()) / 1000;
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ]) {
    if (Math.abs(seconds) >= size) {
      return relative.format(Math.round(seconds / size), unit);
    }
  }
  return relative.format(Math.round(seconds), "second");
};

/** Compact time-to-go for inside the ring, e.g. "1h 21m" or "45m". */
const formatCountdown = (date) => {
  const minutes = Math.max(0, Math.round((date.getTime() - Date.now()) / 60000));
  if (minutes >= 1440) return `${Math.round(minutes / 1440)}d`;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest ? `${hours}h ${rest}m` : `${hours}h`;
  }
  return `${minutes}m`;
};

/** Whether a state object holds a real value rather than unknown/unavailable. */
const hasValue = (state) =>
  state !== undefined &&
  state.state !== "unknown" &&
  state.state !== "unavailable";

/**
 * Card options that mean the same thing on every card in the set, so they are
 * handled once here rather than re-implemented per card.
 *
 * The colour keys map onto the house-style tokens.  A colour picker hands back
 * `[r, g, b]`; anything else (a theme variable name, a hex string) is passed
 * through untouched so a YAML user is not forced through the picker.
 */
/**
 * The layout scale, densest last.
 *
 * A card has to fit anything from a wide desktop column to one cell of a
 * sections grid, so the size is one choice on a scale rather than a pile of
 * independent switches.  `rows`/`columns` are what the sections view asks for
 * through `getGridOptions`, in its twelve-column grid.
 */
const LAYOUTS = {
  full: { rows: 6, min_rows: 4, columns: 12, min_columns: 6, size: 6 },
  compact: { rows: 5, min_rows: 3, columns: 12, min_columns: 6, size: 5 },
  slim: { rows: 3, min_rows: 2, columns: 12, min_columns: 6, size: 3 },
  tile: { rows: 1, min_rows: 1, columns: 6, min_columns: 3, size: 1 },
};

const COLOUR_OPTIONS = {
  hero_start: "--pps-hero-start",
  hero_end: "--pps-hero-end",
  accent_start: "--pps-accent-start",
  accent_end: "--pps-accent-end",
};

const LAYOUT_LABELS = {
  full: "Full — everything, roomy",
  compact: "Compact — tighter, same content",
  slim: "Slim — controls on one row",
  tile: "Tile — one line, glance only",
};

/**
 * Shared appearance rows, so every card's editor offers the same ones.
 *
 * A card passes the sizes it actually implements: offering one that silently
 * falls back to a different size is worse than not offering it.
 */
const appearanceSchema = (layouts) => [
  {
    name: "",
    type: "expandable",
    title: "Appearance",
    icon: "mdi:palette",
    schema: [
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: layouts.map((value) => ({
              value,
              label: LAYOUT_LABELS[value],
            })),
          },
        },
      },
      { name: "animations", selector: { boolean: {} } },
      {
        name: "",
        type: "grid",
        schema: [
          { name: "hero_start", selector: { color_rgb: {} } },
          { name: "hero_end", selector: { color_rgb: {} } },
          { name: "accent_start", selector: { color_rgb: {} } },
          { name: "accent_end", selector: { color_rgb: {} } },
        ],
      },
    ],
  },
];

const SHARED_LABELS = {
  device_id: "Feeder",
  name: "Name (optional)",
  layout: "Size",
  animations: "Animations",
  hero_start: "Header gradient from",
  hero_end: "Header gradient to",
  accent_start: "Accent gradient from",
  accent_end: "Accent gradient to",
};

/**
 * Base class for the cards in this bundle.
 *
 * Carries the house style, the device lookup, the shared options and a slow
 * ticker, so a new card only has to implement `render`.
 */
class PhilipsPetSeriesCardBase extends LitElement {
  static get properties() {
    // `hass` is deliberately absent: these cards define their own setter so the
    // device is only re-resolved when the configured device actually changes.
    return {
      _config: { state: true },
      _device: { state: true },
      _error: { state: true },
      _tick: { state: true },
    };
  }

  constructor() {
    super();
    this._error = null;
    this._tick = 0;
  }

  static get styles() {
    return sharedStyles;
  }

  setConfig(config) {
    if (!config.device_id) {
      // A card that renders blank is unfixable from the UI; say what is missing.
      throw new Error(
        `${this.localName}: 'device_id' is required. Pick a feeder in the ` +
          "card editor, or set device_id to a Philips Pet Series device."
      );
    }
    this._config = config;
    this._device = undefined;
    this._loadedFor = undefined;
  }

  /** A section toggle: shown unless the config explicitly turns it off. */
  _shows(key) {
    return this._config?.[key] !== false;
  }

  /**
   * Sizes this card implements.  `tile` needs a purpose-built single-line
   * render, so a card only lists it once it has one.
   */
  static get supportedLayouts() {
    return ["full", "compact", "slim"];
  }

  /** The chosen layout, or `full` if the config asks for one this card lacks. */
  get _layout() {
    const chosen = this._config?.layout;
    return chosen && this.constructor.supportedLayouts.includes(chosen)
      ? chosen
      : "full";
  }

  /** Height in the masonry view. */
  getCardSize() {
    return LAYOUTS[this._layout].size;
  }

  /** Height and width in the sections view's twelve-column grid. */
  getGridOptions() {
    const { rows, min_rows, columns, min_columns } = LAYOUTS[this._layout];
    return { rows, min_rows, columns, min_columns };
  }

  willUpdate() {
    // Colour overrides are set on the host, not inside the shadow root: the
    // tokens are declared on :host, and a custom property that reads another
    // one resolves where it is *declared*, so overriding lower down would have
    // no effect.
    for (const [key, property] of Object.entries(COLOUR_OPTIONS)) {
      const value = this._config?.[key];
      if (Array.isArray(value)) {
        this.style.setProperty(property, `rgb(${value.join(",")})`);
      } else if (typeof value === "string" && value) {
        this.style.setProperty(property, value);
      } else {
        this.style.removeProperty(property);
      }
    }
    this.setAttribute("layout", this._layout);
    this.toggleAttribute("animate", this._config?.animations !== false);
  }

  /**
   * Whether to run the scripted animations.
   *
   * CSS animations are gated by the `[animate]` attribute and the reduced-motion
   * media query.  Animations driven from JavaScript have to ask both questions
   * themselves, which is what this is for.
   */
  get _animates() {
    return (
      this._config?.animations !== false &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  /** Run a Web Animations keyframe set on one element inside the card. */
  _animate(selector, keyframes, options) {
    if (!this._animates) return;
    this.renderRoot?.querySelector(selector)?.animate(keyframes, options);
  }

  set hass(hass) {
    this._hass = hass;
    // Resolve the entity map once per configured device.  `hass` is reassigned
    // on every state change, so keying off the device rather than "do we have a
    // device yet" is what stops a failed lookup turning into a request storm.
    if (this._loadedFor !== this._config?.device_id) {
      this._loadedFor = this._config?.device_id;
      this._loadDevice();
    }
    this.requestUpdate();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    super.connectedCallback();
    // Countdowns and relative times are computed at render, so nothing would
    // move between state changes without a nudge.  Half a minute is finer than
    // anything these cards display.
    this._ticker = window.setInterval(() => {
      this._tick += 1;
    }, 30000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.clearInterval(this._ticker);
  }

  async _loadDevice() {
    if (!this._hass || !this._config?.device_id) return;
    const wanted = this._config.device_id;
    try {
      const { devices } = await this._hass.callWS({
        type: "philips_pet_series/devices",
      });
      this._device = devices.find((device) => device.device_id === wanted);
      this._error = this._device
        ? null
        : `No Philips Pet Series device with id ${wanted}. It may have been removed.`;
    } catch (err) {
      this._error = `Could not read the device list: ${err.message || err}`;
    }
  }

  /** State object for a role, or undefined when the entity does not exist. */
  _state(role) {
    const entityId = this._device?.entities?.[role];
    return entityId ? this._hass.states[entityId] : undefined;
  }

  /** Whether the feeder is reachable, by either of its two signals. */
  get _online() {
    // The connectivity sensor reads "on" when connected.
    return (
      this._state("connectivity")?.state === "on" ||
      this._state("cloud_connected")?.state === "on"
    );
  }

  _showMore(role) {
    const entityId = this._device?.entities?.[role];
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  /** Hero + placeholder shell used until the device map has arrived. */
  _renderLoading() {
    return html`<ha-card>
      <div class="placeholder">${this._error || "Loading…"}</div>
    </ha-card>`;
  }
}

/* --- cards ------------------------------------------------------------- */

const CARD_TYPE = "philips-feeder-card";
const DEFAULT_PORTIONS = 1;
// A feeder's own datapoint caps this, but a card must not render an unbounded
// stepper if the number entity is missing.  Twenty portions is well past any
// single sensible feeding; the real cap comes from the entity when present.
const FALLBACK_MAX_PORTIONS = 20;
// Geometry of the countdown ring.  r * 2π, precomputed as the dash length.
const RING_RADIUS = 30;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

// Sections a user can switch off.  All are on unless the config says otherwise.
const SECTION_KEYS = [
  "show_next_meal",
  "show_ring",
  "show_schedule",
  "show_feed",
  "show_problems",
  "show_last_dispensed",
];

// Everything the editor should show switched on when the config is silent, and
// strip again on save so an untouched switch is not written to YAML.
const ON_BY_DEFAULT = [...SECTION_KEYS, "animations"];

const PROBLEMS = [
  ["food_level_low", "Food level low", "mdi:package-variant"],
  ["food_outlet_stuck", "Food outlet stuck", "mdi:alert-octagon"],
  ["filter_replacement_due", "Filter replacement due", "mdi:air-filter"],
];

class PhilipsFeederCard extends PhilipsPetSeriesCardBase {
  static get supportedLayouts() {
    return ["full", "compact", "slim", "tile"];
  }

  static get properties() {
    return {
      ...super.properties,
      _portions: { state: true },
      _busy: { state: true },
      _armed: { state: true },
      _justFed: { state: true },
    };
  }

  constructor() {
    super();
    this._portions = DEFAULT_PORTIONS;
    this._busy = false;
    // Only used when the card is configured with `confirm: true`: the first tap
    // arms the button, the second dispenses.
    this._armed = false;
    // Briefly true after a successful dispense, so the button can confirm what
    // happened instead of silently snapping back to its resting state.
    this._justFed = false;
  }

  /** The ring draws itself once, on the card's first paint. */
  firstUpdated() {
    this._animate(
      ".ring .arc",
      [{ strokeDashoffset: RING_CIRCUMFERENCE }, {}],
      { duration: 900, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }
    );
  }

  updated(changed) {
    if (changed.has("_portions") && changed.get("_portions") !== undefined) {
      this._animate(".amount .value", [{ transform: "scale(1.22)" }, {}], {
        duration: 200,
        easing: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      });
    }
    if (changed.has("_justFed") && this._justFed) {
      // The confirmed state swaps the paw for a tick, so the hop has to target
      // whichever glyph is currently in the button.
      this._animate(
        ".cta ha-icon, .cta svg, .tile .feed svg",
        [
          { transform: "translateY(0)" },
          { transform: "translateY(-6px) rotate(-12deg)", offset: 0.4 },
          { transform: "translateY(0)" },
        ],
        { duration: 480, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)" }
      );
    }
  }

  static get styles() {
    return [
      sharedStyles,
      css`
        .next {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .ring {
          flex: none;
          position: relative;
          width: 74px;
          height: 74px;
        }
        .ring svg {
          width: 100%;
          height: 100%;
          transform: rotate(-90deg);
        }
        .ring .track {
          fill: none;
          stroke: color-mix(in srgb, var(--primary-text-color) 11%, transparent);
          stroke-width: 6;
        }
        .ring .arc {
          fill: none;
          stroke: url(#pps-ring-gradient);
          stroke-width: 6;
          stroke-linecap: round;
          transition: stroke-dashoffset 0.6s ease;
        }
        .ring .inner {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          font-size: 0.82rem;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          color: var(--primary-text-color);
        }

        .when {
          min-width: 0;
        }
        .clock {
          font-size: 2.1rem;
          font-weight: 300;
          line-height: 1.05;
          letter-spacing: -0.02em;
          font-variant-numeric: tabular-nums;
          color: var(--primary-text-color);
        }
        .meal {
          margin-top: 3px;
          font-size: 0.87rem;
          color: var(--secondary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .muted {
          font-size: 1.05rem;
          font-weight: 400;
          color: var(--secondary-text-color);
        }
        /* Stands in for the ring's countdown when the ring is switched off. */
        .relative {
          margin-left: 9px;
          font-size: 0.9rem;
          color: var(--secondary-text-color);
        }

        .schedule {
          margin-top: 14px;
        }

        .stepper {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 12px 0 14px;
        }
        .stepper ha-icon-button {
          flex: none;
          border-radius: 50%;
          color: var(--primary-text-color);
          background: color-mix(
            in srgb,
            var(--primary-text-color) 8%,
            transparent
          );
          --mdc-icon-button-size: 42px;
        }
        .amount {
          flex: 1;
          text-align: center;
          line-height: 1.15;
        }
        .amount .value {
          font-size: 1.9rem;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          color: var(--primary-text-color);
        }
        .amount .unit {
          font-size: 0.86rem;
          color: var(--secondary-text-color);
          margin-left: 5px;
        }
        .amount .grams {
          display: block;
          margin-top: 1px;
          font-size: 0.74rem;
          letter-spacing: 0.03em;
          color: var(--secondary-text-color);
          opacity: 0.85;
        }

        /* --- slim: the whole feed control collapses onto one row --------- */

        :host([layout="slim"]) .ring {
          width: 52px;
          height: 52px;
        }
        :host([layout="slim"]) .ring .inner {
          font-size: 0.7rem;
        }
        :host([layout="slim"]) .clock {
          font-size: 1.5rem;
        }
        :host([layout="slim"]) .next {
          gap: 12px;
        }
        :host([layout="slim"]) .schedule {
          margin-top: 9px;
        }
        :host([layout="slim"]) .section.feed {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        :host([layout="slim"]) .section.feed .label {
          display: none;
        }
        :host([layout="slim"]) .stepper {
          margin: 0;
          flex: none;
          gap: 6px;
        }
        :host([layout="slim"]) .stepper ha-icon-button {
          --mdc-icon-button-size: 34px;
        }
        :host([layout="slim"]) .amount {
          flex: none;
          min-width: 34px;
        }
        :host([layout="slim"]) .amount .value {
          font-size: 1.25rem;
        }
        :host([layout="slim"]) .amount .unit,
        :host([layout="slim"]) .amount .grams {
          display: none;
        }
        :host([layout="slim"]) .cta {
          flex: 1;
          padding: 10px;
          font-size: 0.9rem;
        }

        /* --- tile: one line, for a wall of feeders ----------------------- */

        .tile {
          display: flex;
          align-items: center;
          gap: 11px;
          padding: 10px 13px;
          background: linear-gradient(
            120deg,
            var(--pps-hero-from) 0%,
            var(--pps-hero-to) 100%
          );
          color: var(--pps-hero-text);
          cursor: pointer;
        }
        .tile.offline {
          filter: saturate(0.3);
        }
        .tile .mark {
          flex: none;
          width: 28px;
          height: 28px;
          border-radius: 9px;
          background: rgba(255, 255, 255, 0.16);
          display: grid;
          place-items: center;
        }
        .tile .mark svg {
          width: 17px;
          height: 17px;
          fill: currentColor;
        }
        .tile .name {
          flex: 1;
          min-width: 0;
          font-weight: 600;
          font-size: 0.95rem;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .tile .countdown {
          flex: none;
          font-size: 0.78rem;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          padding: 3px 9px;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.16);
        }
        .tile .feed {
          flex: none;
          width: 30px;
          height: 30px;
          border: none;
          border-radius: 50%;
          display: grid;
          place-items: center;
          cursor: pointer;
          color: #fff;
          background: linear-gradient(
            120deg,
            var(--pps-accent-from) 0%,
            var(--pps-accent-to) 100%
          );
        }
        .tile .feed.armed {
          background: transparent;
          box-shadow: inset 0 0 0 2px currentColor;
        }
        .tile .feed[disabled] {
          opacity: 0.55;
          cursor: default;
        }
        .tile .feed svg {
          width: 16px;
          height: 16px;
          fill: currentColor;
        }
        .tile .alert {
          flex: none;
          --mdc-icon-size: 18px;
          color: #fff;
        }
      `,
    ];
  }

  static getConfigElement() {
    return document.createElement(`${CARD_TYPE}-editor`);
  }

  static async getStubConfig(hass) {
    const { devices } = await hass.callWS({ type: "philips_pet_series/devices" });
    const feeder = devices.find((device) => device.entities.feed_button);
    return { type: `custom:${CARD_TYPE}`, device_id: feeder?.device_id };
  }

  setConfig(config) {
    super.setConfig(config);
    const requested = config.max_portions;
    if (requested !== undefined && !(Number(requested) >= 1)) {
      throw new Error(
        `${this.localName}: 'max_portions' must be at least 1, got ${requested}.`
      );
    }
    this._portions = this._clampPortions(
      Number(config.default_portions) || DEFAULT_PORTIONS
    );
  }

  /**
   * The largest number of portions the stepper will offer.
   *
   * The feeder's own datapoint is the real cap; `max_portions` can only lower
   * it, so a dashboard cannot be configured to ask the device for more than it
   * accepts.
   */
  get _maxPortions() {
    const number = this._state("feed_portions_now");
    const deviceMax = Number(number?.attributes?.max) || FALLBACK_MAX_PORTIONS;
    const configured = Number(this._config?.max_portions);
    return configured >= 1 ? Math.min(deviceMax, configured) : deviceMax;
  }

  _clampPortions(value) {
    return Math.min(Math.max(value, 1), this._maxPortions);
  }

  get _gramsPerPortion() {
    const portionSize = this._state("portion_size");
    return hasValue(portionSize) ? Number(portionSize.state) : null;
  }

  _step(delta) {
    this._portions = this._clampPortions(this._portions + delta);
    this._armed = false;
  }

  async _dispense() {
    if (this._config.confirm && !this._armed) {
      this._armed = true;
      return;
    }
    this._armed = false;
    this._busy = true;
    this._error = null;
    try {
      // One portion goes through the button, which picks the right datapoint
      // per feeder model; several portions go through the number, which is the
      // only entity that can ask for a count.
      if (this._portions === 1 && this._device.entities.feed_button) {
        await this._hass.callService("button", "press", undefined, {
          entity_id: this._device.entities.feed_button,
        });
      } else if (this._device.entities.feed_portions_now) {
        await this._hass.callService(
          "number",
          "set_value",
          { value: this._portions },
          { entity_id: this._device.entities.feed_portions_now }
        );
      } else {
        throw new Error(
          "this feeder exposes neither a feed button nor a portions number"
        );
      }
      this._justFed = true;
      window.clearTimeout(this._fedTimer);
      this._fedTimer = window.setTimeout(() => {
        this._justFed = false;
      }, 2200);
    } catch (err) {
      this._error = `Dispensing failed: ${err.message || err}`;
    } finally {
      this._busy = false;
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.clearTimeout(this._fedTimer);
  }

  render() {
    if (!this._hass || !this._config) return nothing;
    if (!this._device) return this._renderLoading();
    if (this._layout === "tile") return this._renderTile();

    return html`
      <ha-card>
        ${renderHero({
          title: this._config.name || this._device.name || "Feeder",
          subtitle: this._device.model,
          online: this._online,
          onStatusClick: () => this._showMore("connectivity"),
        })}
        ${this._shows("show_next_meal") ? this._renderNextMeal() : nothing}
        ${this._shows("show_feed") ? this._renderFeedNow() : nothing}
        ${this._shows("show_problems") ? this._renderProblems() : nothing}
        ${this._shows("show_last_dispensed") ? this._renderFooter() : nothing}
      </ha-card>
    `;
  }

  /**
   * One line: mark, name, countdown, and the feed button if it is wanted.
   *
   * At this size a stepper would be unusable, so the button dispenses the
   * card's configured portion count.  Tapping anywhere else opens more-info,
   * which is where the detail lives at a glance size.
   */
  _renderTile() {
    const nextMeal = this._state("next_meal");
    const problem = PROBLEMS.find(([role]) => this._state(role)?.state === "on");

    return html`
      <ha-card>
        <div
          class="tile ${this._online ? "" : "offline"}"
          @click=${() => this._showMore("next_meal")}
        >
          <div class="mark">
            <svg viewBox="0 0 24 24"><path d=${PAW_PATH}></path></svg>
          </div>
          <div class="name">
            ${this._config.name || this._device.name || "Feeder"}
          </div>
          ${problem && this._shows("show_problems")
            ? html`<ha-icon
                class="alert"
                .icon=${problem[2]}
                title=${problem[1]}
              ></ha-icon>`
            : nothing}
          ${hasValue(nextMeal)
            ? html`<span class="countdown"
                >${formatCountdown(new Date(nextMeal.state))}</span
              >`
            : nothing}
          ${this._shows("show_feed") ? this._renderTileButton() : nothing}
        </div>
      </ha-card>
    `;
  }

  _renderTileButton() {
    const canFeed =
      Boolean(this._device.entities.feed_button) ||
      Boolean(this._device.entities.feed_portions_now);
    if (!canFeed) return nothing;
    const label = this._armed
      ? "Tap again to confirm"
      : `Dispense ${this._portions} portion${this._portions === 1 ? "" : "s"}`;
    return html`<button
      class="feed ${this._armed ? "armed" : ""}"
      ?disabled=${this._busy}
      title=${label}
      aria-label=${label}
      @click=${(ev) => {
        ev.stopPropagation();
        this._dispense();
      }}
    >
      <svg viewBox="0 0 24 24"><path d=${PAW_PATH}></path></svg>
    </button>`;
  }

  /**
   * Progress towards the next meal, or null when it cannot be measured.
   *
   * The gap to the meal after next stands in for the feeding interval, which is
   * right for a repeating schedule and is the only interval the sensor gives
   * us.  With nothing to compare against, the ring shows no arc rather than a
   * made-up one.
   */
  _mealProgress(upcoming) {
    if (upcoming.length < 2) return null;
    const next = new Date(upcoming[0].start).getTime();
    const interval = new Date(upcoming[1].start).getTime() - next;
    if (!(interval > 0)) return null;
    const remaining = next - Date.now();
    return Math.min(Math.max(1 - remaining / interval, 0), 1);
  }

  _renderNextMeal() {
    const nextMeal = this._state("next_meal");
    if (!hasValue(nextMeal)) {
      return html`<div class="section">
        <div class="label">Next meal</div>
        <div class="clock muted" style="margin-top:6px">No meals scheduled</div>
      </div>`;
    }

    const when = new Date(nextMeal.state);
    const upcoming = nextMeal.attributes.upcoming || [];
    const progress = this._mealProgress(upcoming);
    const grams = this._gramsPerPortion;
    const portions = Number(nextMeal.attributes.portions) || null;
    const meal = [
      nextMeal.attributes.meal_name,
      portions
        ? `${portions} portion${portions === 1 ? "" : "s"}` +
          (grams ? ` · ${Math.round(portions * grams)} g` : "")
        : null,
    ]
      .filter(Boolean)
      .join(" · ");

    return html`
      <div class="section" @click=${() => this._showMore("next_meal")}>
        <div class="next">
          ${this._shows("show_ring") ? this._renderRing(when, progress) : nothing}
          <div class="when">
            <div class="label">Next meal</div>
            <div class="clock">
              ${formatTime(this._hass, when)}
              ${this._shows("show_ring")
                ? nothing
                : html`<span class="relative"
                    >${formatRelative(this._hass, when)}</span
                  >`}
            </div>
            <div class="meal">${meal || formatRelative(this._hass, when)}</div>
          </div>
        </div>
        ${this._shows("show_schedule") && upcoming.length > 1
          ? html`<div class="chips schedule">
              ${upcoming
                .slice(1, 6)
                .map(
                  (item, index) =>
                    html`<span class="chip" style="--i:${index}"
                      >${formatTime(this._hass, new Date(item.start))}</span
                    >`
                )}
            </div>`
          : nothing}
      </div>
    `;
  }

  /** The countdown ring: the arc is drawn only when progress is measurable. */
  _renderRing(when, progress) {
    return html`<div class="ring">
      <svg viewBox="0 0 74 74">
        <defs>
          <linearGradient id="pps-ring-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="var(--pps-accent-from)" />
            <stop offset="100%" stop-color="var(--pps-accent-to)" />
          </linearGradient>
        </defs>
        <circle class="track" cx="37" cy="37" r=${RING_RADIUS}></circle>
        <circle
          class="arc"
          cx="37"
          cy="37"
          r=${RING_RADIUS}
          stroke-dasharray=${RING_CIRCUMFERENCE}
          stroke-dashoffset=${RING_CIRCUMFERENCE * (1 - (progress ?? 0))}
        ></circle>
      </svg>
      <div class="inner">${formatCountdown(when)}</div>
    </div>`;
  }

  _renderFeedNow() {
    const canFeed =
      Boolean(this._device.entities.feed_button) ||
      Boolean(this._device.entities.feed_portions_now);
    if (!canFeed) return nothing;

    const grams = this._gramsPerPortion;
    const label = this._busy
      ? "Dispensing…"
      : this._justFed
        ? "Dispensed"
        : this._armed
          ? "Tap again to confirm"
          : "Dispense";

    return html`
      <div class="section feed">
        <div class="label">Feed now</div>
        <div class="stepper">
          <ha-icon-button
            .disabled=${this._portions <= 1 || this._busy}
            .path=${"M19,13H5V11H19V13Z"}
            label="One portion fewer"
            @click=${() => this._step(-1)}
          ></ha-icon-button>
          <div class="amount">
            <span class="value">${this._portions}</span
            ><span class="unit"
              >portion${this._portions === 1 ? "" : "s"}</span
            >
            ${grams
              ? html`<span class="grams"
                  >≈ ${Math.round(this._portions * grams)} g</span
                >`
              : nothing}
          </div>
          <ha-icon-button
            .disabled=${this._portions >= this._maxPortions || this._busy}
            .path=${"M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"}
            label="One portion more"
            @click=${() => this._step(1)}
          ></ha-icon-button>
        </div>
        <button
          class="cta ${this._armed ? "armed" : ""} ${this._busy ? "busy" : ""}"
          ?disabled=${this._busy}
          @click=${() => this._dispense()}
        >
          ${this._justFed
            ? html`<ha-icon icon="mdi:check-circle"></ha-icon>`
            : html`<svg viewBox="0 0 24 24">
                <path d=${PAW_PATH}></path>
              </svg>`}${label}
        </button>
      </div>
    `;
  }

  _renderProblems() {
    const active = PROBLEMS.filter(([role]) => this._state(role)?.state === "on");
    if (!active.length && !this._error) return nothing;
    return html`
      <div class="section problems">
        ${active.map(
          ([role, label, icon]) => html`
            <div class="problem" @click=${() => this._showMore(role)}>
              <ha-icon icon=${icon}></ha-icon>${label}
            </div>
          `
        )}
        ${this._error
          ? html`<div class="problem">
              <ha-icon icon="mdi:alert-circle"></ha-icon>${this._error}
            </div>`
          : nothing}
      </div>
    `;
  }

  _renderFooter() {
    const last = this._state("last_meal_dispensed");
    if (!hasValue(last)) return nothing;
    const when = new Date(last.state);
    return html`<div
      class="footer"
      @click=${() => this._showMore("last_meal_dispensed")}
    >
      <ha-icon icon="mdi:history"></ha-icon>Last dispensed
      ${formatTime(this._hass, when)} · ${formatRelative(this._hass, when)}
    </div>`;
  }
}

/**
 * Shared editor plumbing.
 *
 * A card subclass supplies `_cardType`, `_schema` and its own labels; the base
 * handles the two things every editor in the set needs to get right: showing
 * default-on switches as on, and not writing untouched defaults back to YAML.
 */
class PhilipsPetSeriesCardEditor extends LitElement {
  static get properties() {
    return { hass: { attribute: false }, _config: { state: true } };
  }

  setConfig(config) {
    this._config = config;
  }

  /** Keys that are on unless the config says otherwise. */
  get _onByDefault() {
    return ["animations"];
  }

  get _labels() {
    return SHARED_LABELS;
  }

  get _helpers() {
    return {};
  }

  /** Card-specific defaults, on top of the ones every card shares. */
  get _cardDefaults() {
    return {};
  }

  get _defaults() {
    const defaults = {
      ...DEFAULT_COLOURS,
      layout: "full",
      ...this._cardDefaults,
    };
    for (const key of this._onByDefault) defaults[key] = true;
    return defaults;
  }

  /**
   * What the form displays: the config, with every unset option filled in from
   * its default.
   *
   * `ha-form` draws a missing boolean as off and a missing dropdown as blank,
   * so without this a fresh card claims every section is hidden and no picture
   * mode is chosen.  `_valueChanged` strips the defaults again on the way out,
   * so the saved YAML still only records real choices.
   */
  get _data() {
    return { ...this._defaults, ...this._config };
  }

  _valueChanged(ev) {
    const config = { type: `custom:${this._cardType}`, ...ev.detail.value };
    for (const [key, fallback] of Object.entries(this._defaults)) {
      if (String(config[key]) === String(fallback)) delete config[key];
    }
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }

  render() {
    if (!this.hass || !this._config) return nothing;
    return html`<ha-form
      .hass=${this.hass}
      .data=${this._data}
      .schema=${this._schema}
      .computeLabel=${(schema) => this._labels[schema.name] || schema.name}
      .computeHelper=${(schema) => this._helpers[schema.name]}
      @value-changed=${this._valueChanged}
    ></ha-form>`;
  }
}

/** The device picker rows every card starts with. */
const deviceSchema = () => [
  {
    name: "device_id",
    required: true,
    selector: { device: { integration: "philips_pet_series" } },
  },
  { name: "name", selector: { text: {} } },
];

class PhilipsFeederCardEditor extends PhilipsPetSeriesCardEditor {
  get _cardType() {
    return CARD_TYPE;
  }

  get _layouts() {
    return PhilipsFeederCard.supportedLayouts;
  }

  get _onByDefault() {
    return ON_BY_DEFAULT;
  }

  get _schema() {
    return [
      ...deviceSchema(),
      {
        name: "",
        type: "expandable",
        title: "Feeding",
        icon: "mdi:food-drumstick",
        schema: [
          { name: "confirm", selector: { boolean: {} } },
          {
            name: "",
            type: "grid",
            schema: [
              {
                name: "default_portions",
                selector: { number: { min: 1, max: 20, mode: "box" } },
              },
              {
                name: "max_portions",
                selector: { number: { min: 1, max: 20, mode: "box" } },
              },
            ],
          },
        ],
      },
      {
        name: "",
        type: "expandable",
        title: "Sections",
        icon: "mdi:view-agenda",
        schema: SECTION_KEYS.map((name) => ({
          name,
          selector: { boolean: {} },
        })),
      },
      ...appearanceSchema(this._layouts),
    ];
  }

  get _labels() {
    return {
      ...SHARED_LABELS,
      confirm: "Ask for confirmation before dispensing",
      default_portions: "Portions preselected",
      max_portions: "Most portions per press",
      show_next_meal: "Next meal",
      show_ring: "Countdown ring",
      show_schedule: "Rest of the day\u2019s feeding times",
      show_feed: "Feed now controls",
      show_problems: "Food and filter warnings",
      show_last_dispensed: "Last dispensed",
    };
  }

  get _helpers() {
    return { max_portions: "Never more than the feeder itself allows." };
  }
}

/* --- camera card ------------------------------------------------------- */

const CAMERA_CARD_TYPE = "philips-camera-card";

// Switches offered as round toggles under the picture, in the order a user
// reaches for them.  Each is skipped when the feeder does not expose it.
const CAMERA_TOGGLES = [
  ["privacy_mode", "Privacy mode", "mdi:eye-off", "mdi:eye"],
  ["motion_alarm", "Motion detection", "mdi:motion-sensor", "mdi:motion-sensor-off"],
  ["pre_feed_snapshot", "Snapshot before feeding", "mdi:camera-timer", "mdi:camera-off"],
  ["video_osd", "On-screen display", "mdi:format-text", "mdi:format-text"],
];

const CAMERA_SECTION_KEYS = ["show_picture", "show_controls", "show_last_motion"];
const CAMERA_ON_BY_DEFAULT = [...CAMERA_SECTION_KEYS, "animations"];

class PhilipsCameraCard extends PhilipsPetSeriesCardBase {
  static get properties() {
    return { ...super.properties, _busy: { state: true } };
  }

  static get styles() {
    return [
      sharedStyles,
      css`
        .picture {
          position: relative;
          display: block;
          background: #000;
          cursor: pointer;
        }
        .picture hui-image,
        .picture img {
          display: block;
          width: 100%;
        }
        .picture img {
          aspect-ratio: 16 / 9;
          object-fit: cover;
        }
        /* Reading a caption over an unknown photo needs a scrim, not a guess
           about how bright the photo is. */
        .caption {
          position: absolute;
          left: 0;
          right: 0;
          bottom: 0;
          padding: 22px 13px 9px;
          display: flex;
          align-items: center;
          gap: 7px;
          font-size: 0.8rem;
          color: #fff;
          background: linear-gradient(transparent, rgba(0, 0, 0, 0.62));
          pointer-events: none;
        }
        .caption ha-icon {
          --mdc-icon-size: 16px;
        }
        /* Privacy mode means the lens is shut: say so over the frame rather
           than leaving a black rectangle to be interpreted. */
        .curtain {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          gap: 6px;
          align-content: center;
          background: rgba(10, 12, 14, 0.82);
          color: #fff;
          font-size: 0.85rem;
        }
        .curtain ha-icon {
          --mdc-icon-size: 28px;
          opacity: 0.85;
        }
        :host([layout="slim"]) .picture img {
          aspect-ratio: 21 / 9;
        }
        .live {
          margin-left: auto;
          font-size: 0.66rem;
          font-weight: 700;
          letter-spacing: 0.09em;
          padding: 2px 7px;
          border-radius: 999px;
          background: var(--pps-accent-solid);
        }
        .missing {
          padding: var(--pps-gap);
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }
      `,
    ];
  }

  static getConfigElement() {
    return document.createElement(`${CAMERA_CARD_TYPE}-editor`);
  }

  static async getStubConfig(hass) {
    const { devices } = await hass.callWS({ type: "philips_pet_series/devices" });
    const withCamera = devices.find((device) => device.entities.camera);
    return { type: `custom:${CAMERA_CARD_TYPE}`, device_id: withCamera?.device_id };
  }

  /**
   * Whether to stream.
   *
   * A camera card that shows a still is not really a camera card, so live is
   * the default.  The integration only holds the connection while something is
   * watching, so an off-screen card is not streaming.  `auto` is there for
   * anyone who would rather the feeder was left alone.
   */
  get _isLive() {
    return this._config.camera_view !== "auto";
  }

  /** A slimmer card gets a slimmer picture, or it is not actually slimmer. */
  get _aspectRatio() {
    return this._layout === "slim" ? "21:9" : "16:9";
  }

  get _privacyOn() {
    return this._state("privacy_mode")?.state === "on";
  }

  async _toggle(role) {
    const entityId = this._device?.entities?.[role];
    if (!entityId) return;
    this._busy = true;
    this._error = null;
    try {
      await this._hass.callService("switch", "toggle", undefined, {
        entity_id: entityId,
      });
    } catch (err) {
      this._error = `Could not switch that: ${err.message || err}`;
    } finally {
      this._busy = false;
    }
  }

  render() {
    if (!this._hass || !this._config) return nothing;
    if (!this._device) return this._renderLoading();

    return html`
      <ha-card>
        ${renderHero({
          title: this._config.name || this._device.name || "Camera",
          subtitle: this._device.model,
          online: this._online,
          onStatusClick: () => this._showMore("connectivity"),
        })}
        ${this._shows("show_picture") ? this._renderPicture() : nothing}
        ${this._shows("show_controls") ? this._renderControls() : nothing}
        ${this._error
          ? html`<div class="section problems">
              <div class="problem">
                <ha-icon icon="mdi:alert-circle"></ha-icon>${this._error}
              </div>
            </div>`
          : nothing}
        ${this._shows("show_last_motion") ? this._renderLastMotion() : nothing}
      </ha-card>
    `;
  }

  _renderPicture() {
    const camera = this._state("camera");
    const snapshot = this._state("last_motion_snapshot");
    if (!camera && !snapshot) {
      return html`<div class="missing">
        This feeder does not expose a camera.
      </div>`;
    }

    const live = this._isLive;

    return html`
      <div
        class="picture"
        @click=${() => this._showMore(camera ? "camera" : "last_motion_snapshot")}
      >
        ${this._renderFrame(live, camera, snapshot)}
        ${this._privacyOn
          ? html`<div class="curtain">
              <ha-icon icon="mdi:eye-off"></ha-icon>Privacy mode is on
            </div>`
          : this._renderCaption()}
      </div>
    `;
  }

  /**
   * The picture itself.
   *
   * `hui-image` is Home Assistant's own camera element and handles streaming,
   * proxying and refresh.  It is part of the Lovelace bundle rather than a
   * guaranteed global, so a plain proxied still is kept as a fallback instead
   * of rendering nothing if it is ever absent.
   */
  _renderFrame(live, camera, snapshot) {
    const cameraId = this._device.entities.camera;
    if (camera && cameraId && customElements.get("hui-image")) {
      return html`<hui-image
        .hass=${this._hass}
        .cameraImage=${cameraId}
        .cameraView=${live ? "live" : "auto"}
        .aspectRatio=${this._aspectRatio}
        .fitMode=${"cover"}
      ></hui-image>`;
    }
    // No camera, or no Lovelace image element: fall back to whatever proxied
    // still Home Assistant already has.
    const picture = (camera || snapshot)?.attributes?.entity_picture;
    return picture
      ? html`<img src=${picture} alt="Feeder camera" />`
      : html`<div class="missing">No picture available yet.</div>`;
  }

  /**
   * The strip along the bottom of the picture.
   *
   * The motion time only appears here when the footer is switched off: with
   * both on, the card printed the same sentence twice.
   */
  _renderCaption() {
    const live = this._isLive;
    const lastMotion = this._state("last_motion");
    const showMotion = !this._shows("show_last_motion") && hasValue(lastMotion);
    if (!live && !showMotion) return nothing;
    return html`<div class="caption">
      ${showMotion
        ? html`<ha-icon icon="mdi:motion-sensor"></ha-icon>Motion
            ${formatRelative(this._hass, new Date(lastMotion.state))}`
        : nothing}
      ${live ? html`<span class="live">LIVE</span>` : nothing}
    </div>`;
  }

  _renderControls() {
    const available = CAMERA_TOGGLES.filter(
      ([role]) => this._device.entities[role]
    );
    if (!available.length) return nothing;
    return html`
      <div class="section">
        <div class="label">Camera</div>
        <div class="toggles" style="margin-top:10px">
          ${available.map(([role, label, onIcon, offIcon]) => {
            const on = this._state(role)?.state === "on";
            return html`<button
              class="toggle ${on ? "on" : ""}"
              ?disabled=${this._busy}
              title=${label}
              aria-label=${label}
              aria-pressed=${on ? "true" : "false"}
              @click=${() => this._toggle(role)}
            >
              <ha-icon icon=${on ? onIcon : offIcon}></ha-icon>
            </button>`;
          })}
        </div>
      </div>
    `;
  }

  _renderLastMotion() {
    const lastMotion = this._state("last_motion");
    if (!hasValue(lastMotion)) return nothing;
    const when = new Date(lastMotion.state);
    return html`<div class="footer" @click=${() => this._showMore("last_motion")}>
      <ha-icon icon="mdi:motion-sensor"></ha-icon>Last motion
      ${formatTime(this._hass, when)} · ${formatRelative(this._hass, when)}
    </div>`;
  }
}

class PhilipsCameraCardEditor extends PhilipsPetSeriesCardEditor {
  get _cardType() {
    return CAMERA_CARD_TYPE;
  }

  get _layouts() {
    return PhilipsCameraCard.supportedLayouts;
  }

  get _onByDefault() {
    return CAMERA_ON_BY_DEFAULT;
  }

  get _schema() {
    return [
      ...deviceSchema(),
      {
        name: "camera_view",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "live", label: "Live stream" },
              { value: "auto", label: "Still image, refreshed" },
            ],
          },
        },
      },
      {
        name: "",
        type: "expandable",
        title: "Sections",
        icon: "mdi:view-agenda",
        schema: CAMERA_SECTION_KEYS.map((name) => ({
          name,
          selector: { boolean: {} },
        })),
      },
      ...appearanceSchema(this._layouts),
    ];
  }

  get _cardDefaults() {
    return { camera_view: "live" };
  }

  get _labels() {
    return {
      ...SHARED_LABELS,
      device_id: "Feeder",
      camera_view: "Picture",
      show_picture: "Picture",
      show_controls: "Camera switches",
      show_last_motion: "Last motion",
    };
  }

  get _helpers() {
    return {
      camera_view:
        "The feeder only allows a couple of connections at once, so a live stream can push the phone app off while you are watching. Switch to the still image to leave it alone.",
    };
  }
}

/* --- health card ------------------------------------------------------- */

const HEALTH_CARD_TYPE = "philips-health-card";
const HEALTH_SECTION_KEYS = ["show_stats", "show_problems", "show_actions"];
const HEALTH_ON_BY_DEFAULT = [...HEALTH_SECTION_KEYS, "animations"];

class PhilipsHealthCard extends PhilipsPetSeriesCardBase {
  static get properties() {
    return { ...super.properties, _busy: { state: true } };
  }

  static get styles() {
    return [
      sharedStyles,
      css`
        .ok {
          display: flex;
          align-items: center;
          gap: 9px;
          padding: 9px 11px;
          border-radius: 10px;
          border-left: 3px solid var(--pps-online);
          background: color-mix(in srgb, var(--pps-online) 12%, transparent);
          font-size: 0.87rem;
          color: var(--primary-text-color);
        }
        .ok ha-icon {
          --mdc-icon-size: 19px;
          color: var(--pps-online);
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .action {
          flex: 1 1 auto;
          padding: 10px 14px;
          border: 1px solid var(--divider-color);
          border-radius: 11px;
          background: transparent;
          color: var(--primary-text-color);
          font-family: inherit;
          font-size: 0.9rem;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .action:hover {
          border-color: var(--pps-accent-solid);
          color: var(--pps-accent-solid);
        }
        .action[disabled] {
          opacity: 0.55;
          cursor: default;
        }
      `,
    ];
  }

  static getConfigElement() {
    return document.createElement(`${HEALTH_CARD_TYPE}-editor`);
  }

  static async getStubConfig(hass) {
    const { devices } = await hass.callWS({ type: "philips_pet_series/devices" });
    const feeder = devices.find((device) => device.entities.connectivity);
    return { type: `custom:${HEALTH_CARD_TYPE}`, device_id: feeder?.device_id };
  }

  /** The readouts worth a tile, skipping anything this feeder lacks. */
  get _stats() {
    const stats = [];
    const add = (role, key, icon, value, tone) => {
      if (value === null || value === undefined) return;
      stats.push({ role, key, icon, value, tone });
    };

    const cloud = this._state("cloud_connected");
    if (cloud) {
      const on = cloud.state === "on";
      add("cloud_connected", "Cloud", "mdi:cloud-outline", on ? "Connected" : "Offline", on ? "good" : "bad");
    }

    for (const [role, key] of [
      ["firmware_wifi", "WiFi firmware"],
      ["firmware_mcu", "MCU firmware"],
    ]) {
      const state = this._state(role);
      if (hasValue(state)) add(role, key, "mdi:chip", state.state);
    }

    const portion = this._state("portion_size");
    if (hasValue(portion)) {
      add("portion_size", "Portion size", "mdi:scale", `${portion.state} g`);
    }

    const fault = this._state("feeding_fault");
    if (hasValue(fault)) {
      const clear = Number(fault.state) === 0;
      add(
        "feeding_fault",
        "Feeding fault",
        "mdi:alert-circle-outline",
        clear ? "None" : `Code ${fault.state}`,
        clear ? "good" : "bad"
      );
    }

    return stats;
  }

  async _press(role) {
    const entityId = this._device?.entities?.[role];
    if (!entityId) return;
    this._busy = true;
    this._error = null;
    try {
      await this._hass.callService("button", "press", undefined, {
        entity_id: entityId,
      });
    } catch (err) {
      this._error = `That did not work: ${err.message || err}`;
    } finally {
      this._busy = false;
    }
  }

  render() {
    if (!this._hass || !this._config) return nothing;
    if (!this._device) return this._renderLoading();

    return html`
      <ha-card>
        ${renderHero({
          title: this._config.name || this._device.name || "Feeder",
          subtitle: this._device.model,
          online: this._online,
          onStatusClick: () => this._showMore("connectivity"),
        })}
        ${this._shows("show_problems") ? this._renderConditions() : nothing}
        ${this._shows("show_stats") ? this._renderStats() : nothing}
        ${this._shows("show_actions") ? this._renderActions() : nothing}
      </ha-card>
    `;
  }

  _renderConditions() {
    const active = PROBLEMS.filter(([role]) => this._state(role)?.state === "on");
    return html`
      <div class="section problems">
        ${active.length
          ? active.map(
              ([role, label, icon]) => html`
                <div class="problem" @click=${() => this._showMore(role)}>
                  <ha-icon icon=${icon}></ha-icon>${label}
                </div>
              `
            )
          : html`<div class="ok">
              <ha-icon icon="mdi:check-circle-outline"></ha-icon>Nothing needs
              attention
            </div>`}
        ${this._error
          ? html`<div class="problem">
              <ha-icon icon="mdi:alert-circle"></ha-icon>${this._error}
            </div>`
          : nothing}
      </div>
    `;
  }

  _renderStats() {
    const stats = this._stats;
    if (!stats.length) return nothing;
    return html`
      <div class="section">
        <div class="stats">
          ${stats.map(
            (stat) => html`
              <div class="stat" @click=${() => this._showMore(stat.role)}>
                <div class="k">
                  <ha-icon icon=${stat.icon}></ha-icon>${stat.key}
                </div>
                <div class="v ${stat.tone || ""}">${stat.value}</div>
              </div>
            `
          )}
        </div>
      </div>
    `;
  }

  _renderActions() {
    if (!this._device.entities.reset_filter) return nothing;
    return html`
      <div class="section actions">
        <button
          class="action"
          ?disabled=${this._busy}
          @click=${() => this._press("reset_filter")}
        >
          <ha-icon icon="mdi:filter-remove"></ha-icon>Reset filter
        </button>
      </div>
    `;
  }
}

class PhilipsHealthCardEditor extends PhilipsPetSeriesCardEditor {
  get _cardType() {
    return HEALTH_CARD_TYPE;
  }

  get _layouts() {
    return PhilipsHealthCard.supportedLayouts;
  }

  get _onByDefault() {
    return HEALTH_ON_BY_DEFAULT;
  }

  get _schema() {
    return [
      ...deviceSchema(),
      {
        name: "",
        type: "expandable",
        title: "Sections",
        icon: "mdi:view-agenda",
        schema: HEALTH_SECTION_KEYS.map((name) => ({
          name,
          selector: { boolean: {} },
        })),
      },
      ...appearanceSchema(this._layouts),
    ];
  }

  get _labels() {
    return {
      ...SHARED_LABELS,
      show_stats: "Readouts",
      show_problems: "Warnings",
      show_actions: "Maintenance buttons",
    };
  }
}

/* --- registration ------------------------------------------------------- */

const CARDS = [
  [
    CARD_TYPE,
    PhilipsFeederCard,
    PhilipsFeederCardEditor,
    "Philips Pet Series feeder",
    "Next meal, portion stepper and a dispense button for a Philips pet feeder.",
  ],
  [
    CAMERA_CARD_TYPE,
    PhilipsCameraCard,
    PhilipsCameraCardEditor,
    "Philips Pet Series camera",
    "The feeder's camera, with its privacy and motion switches.",
  ],
  [
    HEALTH_CARD_TYPE,
    PhilipsHealthCard,
    PhilipsHealthCardEditor,
    "Philips Pet Series health",
    "Connection, firmware and anything about the feeder that needs attention.",
  ],
];

for (const [type, card, editor, name, description] of CARDS) {
  if (customElements.get(type)) continue;
  customElements.define(type, card);
  customElements.define(`${type}-editor`, editor);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type,
    name,
    description,
    preview: true,
    // The README section, not a wiki page: this is the link behind
    // "documentation" in the card picker, and it has to resolve to something
    // that actually describes the cards.
    documentationURL:
      "https://github.com/AboveColin/HA-Philips-Pet-Series#the-dashboard-cards",
  });
}
