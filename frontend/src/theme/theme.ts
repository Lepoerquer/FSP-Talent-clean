import { createTheme, defaultVariantColorsResolver, MantineThemeOverride, parseThemeColor, VariantColorsResolver } from '@mantine/core';
import { fspBlue, fspRed, fspNavy, fspPink, fspPurple, fspDark, fspBrandColors, teal, orange, red, blue, gray } from './colors';

/**
 * Светлые варианты (бейджи, алерты) используют более тёмный оттенок текста:
 * контраст не ниже 4,5:1 (WCAG AA) на подкрашенном фоне.
 */
const variantColorResolver: VariantColorsResolver = (input) => {
  const base = defaultVariantColorsResolver(input);
  if (input.variant === 'light' || input.variant === 'subtle') {
    const parsed = parseThemeColor({ color: input.color, theme: input.theme });
    if (parsed.isThemeColor && parsed.shade === undefined && parsed.color !== 'gray' && parsed.color !== 'dark') {
      return {
        ...base,
        color: `light-dark(var(--mantine-color-${parsed.color}-8), var(--mantine-color-${parsed.color}-3))`,
      };
    }
  }
  return base;
};

// Фирменная типографика ФСП (стр. 21 брендбука):
// - Inter: основной интерфейсный шрифт (читаемость, компактность)
// - JetBrains Mono: заголовки, код, акценты (программистская идентичность бренда)
const bodyFontStack = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const headingFontStack = "'JetBrains Mono', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
const monoFontStack = "'JetBrains Mono', Consolas, 'SFMono-Regular', Menlo, monospace";

export const theme: MantineThemeOverride = createTheme({
  fontFamily: bodyFontStack,
  fontFamilyMonospace: monoFontStack,
  headings: {
    fontFamily: headingFontStack,
    fontWeight: '700',
    sizes: {
      h1: { fontSize: '1.875rem', lineHeight: '1.25' },
      h2: { fontSize: '1.5rem', lineHeight: '1.3' },
      h3: { fontSize: '1.25rem', lineHeight: '1.35' },
      h4: { fontSize: '1.0625rem', lineHeight: '1.4' },
      h5: { fontSize: '0.9375rem', lineHeight: '1.4' },
      h6: { fontSize: '0.8125rem', lineHeight: '1.4' },
    },
  },
  fontSizes: {
    xs: '0.75rem',
    sm: '0.875rem',
    md: '0.9375rem',
    lg: '1.0625rem',
    xl: '1.25rem',
  },
  colors: {
    fspBlue,
    fspRed,
    fspNavy,
    fspPink,
    fspPurple,
    fspDark,
    // Сдержанные версии встроенных палитр Mantine
    teal,
    orange,
    red,
    blue,
    gray,
    violet: fspNavy,
    indigo: fspBlue,
    yellow: orange,
    dark: fspDark,
  },
  primaryColor: 'fspBlue',
  primaryShade: 7, // #3020DB обеспечивает контраст > 5.2:1 с белым текстом на кнопках (WCAG AA)
  black: fspBrandColors.darkBlack,
  radius: { xs: '2px', sm: '4px', md: '6px', lg: '8px', xl: '12px' },
  defaultRadius: 'sm',
  cursorType: 'pointer',
  focusRing: 'auto',
  variantColorResolver,
  shadows: {
    xs: '0 1px 2px rgba(16, 18, 27, 0.06)',
    sm: '0 1px 3px rgba(16, 18, 27, 0.08)',
    md: '0 4px 12px rgba(16, 18, 27, 0.08)',
    lg: '0 8px 24px rgba(16, 18, 27, 0.10)',
    xl: '0 16px 40px rgba(16, 18, 27, 0.12)',
  },
  components: {
    Button: {
      defaultProps: { radius: 'sm', fw: 600 },
      styles: { root: { transition: 'background-color 0.12s ease, border-color 0.12s ease' } },
    },
    Card: {
      defaultProps: { radius: 'md', withBorder: true, padding: 'lg' },
    },
    Paper: {
      defaultProps: { radius: 'md' },
    },
    Badge: {
      defaultProps: { radius: 'sm', fw: 600 },
      styles: { label: { textTransform: 'none', letterSpacing: 0 } },
    },
    Modal: {
      defaultProps: { radius: 'md', overlayProps: { backgroundOpacity: 0.45, blur: 2 } },
      styles: { title: { fontWeight: 600 } },
    },
    Tabs: {
      styles: { tab: { fontWeight: 600 } },
    },
    NavLink: {
      styles: { label: { fontWeight: 500 } },
    },
    TextInput: { defaultProps: { radius: 'sm' } },
    Textarea: { defaultProps: { radius: 'sm' } },
    NumberInput: { defaultProps: { radius: 'sm' } },
    Select: { defaultProps: { radius: 'sm' } },
    MultiSelect: { defaultProps: { radius: 'sm' } },
    Anchor: { defaultProps: { underline: 'always' } },
    Table: { styles: { th: { fontWeight: 600, color: 'var(--fsp-text-muted)' } } },
  },
});

export { fspBrandColors };
