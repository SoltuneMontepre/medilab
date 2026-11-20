// The MediLab theme of the web, `sol_theme/static/src/scss/tokens.scss`, with the same names and values, so the phone
// and the web read as one product. A token changed on the web is changed here too.
export const colors = {
  primary: "#0a4d8c",
  primaryDark: "#083d70",
  primaryMid: "#0e5797",
  primaryLight: "#e6eff8",

  secondary: "#13294b",
  secondaryLight: "#e8ecf3",

  accent: "#0083ef",
  accentLight: "#5ab0f5",
  accentDark: "#0067bd",
  accentSoft: "#e6f3fe",

  bg: "#f2f5f9",
  surface: "#ffffff",
  border: "#dce3ec",
  borderStrong: "#c5d0de",
  borderControl: "#8794aa",

  text: "#16223a",
  textSecondary: "#33415a",
  textMuted: "#5b6880",
  textOnPrimary: "#ffffff",

  danger: "#c0392b",
  dangerSoft: "#fdecea",
  success: "#0b6e4f",
  successSoft: "#e6f4ef",
  warning: "#d97706",
  warningSoft: "#fff8e8",
  favorite: "#c9a227",
};

// The soft backgrounds of app tiles and avatars, in the web's order.
export const tints = ["#e6f3fe", "#e8ecf3", "#eeebfb", "#fdecea", "#e0f5f8", "#e8f5ef"];

export const radius = { sm: 6, md: 10, lg: 14, pill: 999 };

// The web's rem sizes at a 16px root.
export const fontSize = { xs: 12, sm: 13, base: 14, md: 16, lg: 18, xl: 22 };

export const letterSpacing = { heading: -0.2, label: 0.5 };

export const lineHeight = { tight: 1.3, body: 1.5 };

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const layout = {
  navbarHeight: 52,
  // The smallest target a finger hits reliably.
  touch: 48,
  // The widest a screen's content grows on a tablet; it stays centred.
  contentWidth: 720,
};

// Shadows by elevation on Android and by offset on iOS, as soft as the web's `$ml-shadow-*`.
export const shadow = {
  sm: {
    shadowColor: colors.secondary,
    shadowOpacity: 0.05,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  md: {
    shadowColor: colors.secondary,
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
};
