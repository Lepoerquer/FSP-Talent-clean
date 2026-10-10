import { MantineColorsTuple } from '@mantine/core';

// Палитра построена строго по официальному брендбуку Федерации спортивного программирования (ФСП).
// Основные фирменные цвета (стр. 20 брендбука):
// - Electric Blue (Электрический синий): #402FFF (RGB 64, 47, 255, CMYK 77/72/0/0)
// - Sport Red (Спортивный красный): #EC1D35 (RGB 236, 29, 53, CMYK 0/97/83/0)
// - Digital Navy (Цифровой тёмно-синий): #0A006B (RGB 10, 0, 107, CMYK 100/98/14/18)
// - Dark Black (Чёрный/типографика): #1B1C21 (RGB 27, 28, 33, CMYK 76/67/60/76)
// - Серые оттенки: #2D2E37 (карточки/подложки), #3A3C46 (обводка), #EDEDED (белый логотип)

export const fspBlue: MantineColorsTuple = [
  '#eef0ff',
  '#dbe0ff',
  '#b8c2ff',
  '#909eff',
  '#6b7dff',
  '#5363ff',
  '#402fff', // Официальный акцентный цвет ФСП (Electric Blue)
  '#3020db', // Контрастный оттенок для кнопок с белым текстом (primaryShade = 7, WCAG AA > 5.2:1)
  '#1e12b0',
  '#0a006b', // Digital Navy (глубокий цвет цифровой среды)
];

export const fspRed: MantineColorsTuple = [
  '#ffe8ea',
  '#ffd0d5',
  '#faa0aa',
  '#f56e7c',
  '#f04455',
  '#ec283c',
  '#ec1d35', // Официальный красный ФСП (Sport Red)
  '#c71226',
  '#a30a1c',
  '#7a0311',
];

export const fspNavy: MantineColorsTuple = [
  '#ebedfa',
  '#c9ceea',
  '#9fa7d6',
  '#747ec2',
  '#4f59af',
  '#323ea1',
  '#1d2890',
  '#111a7c',
  '#0d1373',
  '#0a006b', // Digital Navy (глубокий синий)
];

export const fspDark: MantineColorsTuple = [
  '#f1f1f3',
  '#dedee2',
  '#bcbec4',
  '#9698a3',
  '#747683',
  '#575865',
  '#3a3c46', // Границы и разделители брендбука (#3A3C46)
  '#2d2e37', // Подложки и карточки брендбука (#2D2E37)
  '#1b1c21', // Тёмный цвет шапки и текста брендбука (#1B1C21)
  '#101114',
];

// Для полной обратной совместимости с существующими компонентами платформы:
// fspPink сопоставляется с официальным фирменным Electric Blue (#402FFF),
// а fspPurple — с официальным Digital Navy (#0A006B).
export const fspPink: MantineColorsTuple = fspBlue;
export const fspPurple: MantineColorsTuple = fspNavy;

// Переопределяем встроенные палитры Mantine в гармоничные сдержанные оттенки
export const teal: MantineColorsTuple = [
  '#eaf6f0', '#d3ebdd', '#a8d6bc', '#7bc09a', '#52ac7d', '#349b67', '#1e7a4f', '#176441', '#114f34', '#0b3a26',
];
export const orange: MantineColorsTuple = [
  '#fff6e5', '#ffeacc', '#ffd699', '#ffc166', '#f5a03a', '#e08414', '#b85c00', '#964a00', '#733a00', '#522900',
];
export const red: MantineColorsTuple = fspRed;
export const blue: MantineColorsTuple = fspBlue;
export const gray: MantineColorsTuple = [
  '#f6f7f9', '#eef0f4', '#e1e4ea', '#cbd0d9', '#a7aebb', '#7f8798', '#5f6677', '#3a3c46', '#2d2e37', '#1b1c21',
];

export const fspBrandColors = {
  // Официальные константы брендбука ФСП
  electricBlue: '#402FFF',
  sportRed: '#EC1D35',
  digitalNavy: '#0A006B',
  darkBlack: '#1B1C21',
  cardGray: '#2D2E37',
  borderGray: '#3A3C46',
  whiteLogo: '#EDEDED',
  pureWhite: '#FFFFFF',

  // Токены интерфейса
  primaryAccent: '#402FFF',
  primaryShade: '#3020DB',
  secondaryAccent: '#EC1D35',
  brandPink: '#402FFF', // обратная совместимость
  purpleDeep: '#0A006B',
  purpleDark: '#0A006B',
  darkBg: '#1B1C21',
  surfaceLight: '#F4F6FB',
  surfaceCard: '#FFFFFF',
  borderLight: '#DDE0E7',
  textSecondary: '#5F6677',
};
