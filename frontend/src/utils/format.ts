// Общие функции форматирования и проверки значений интерфейса.

/** Доля чистой зарплаты после НДФЛ 13 %. */
export const NET_RATIO = 0.87;

export const formatMoney = (rub: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.round(rub)) + ' ₽';

export const netToGross = (net: number): number => Math.round(net / NET_RATIO);
export const grossToNet = (gross: number): number => Math.round(gross * NET_RATIO);

/** Склонение существительных: plural(5, ['год', 'года', 'лет']) → «лет». */
export const plural = (n: number, forms: [string, string, string]): string => {
  const abs = Math.abs(Math.trunc(n));
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
};

/** «3 года», «1 год», «3,5 года». Дробные значения всегда в родительном падеже единственного числа. */
export const formatYears = (years: number): string => {
  if (Number.isInteger(years)) return `${years} ${plural(years, ['год', 'года', 'лет'])}`;
  return `${String(years).replace('.', ',')} года`;
};

/** Для оборотов «опыт от 3 лет», «от 1 года», «от 2,5 лет». */
export const formatYearsFrom = (years: number): string => {
  if (!Number.isInteger(years)) return `${String(years).replace('.', ',')} лет`;
  const mod10 = years % 10;
  const mod100 = years % 100;
  return `${years} ${mod10 === 1 && mod100 !== 11 ? 'года' : 'лет'}`;
};

export const formatCount = (n: number, forms: [string, string, string]): string => `${n} ${plural(n, forms)}`;

/** Оценка способности θ со знаком: «θ = +1,42», «θ = −0,75». */
export const formatTheta = (theta: number): string => {
  const sign = theta < 0 ? '−' : '+';
  return `θ = ${sign}${Math.abs(theta).toFixed(2).replace('.', ',')}`;
};

export const formatDecimal = (value: number, digits = 2): string => value.toFixed(digits).replace('.', ',');

const LEGAL_FORMS = new Set(['ООО', 'АО', 'ПАО', 'ЗАО', 'ОАО', 'ИП', 'LLC', 'INC']);

/**
 * Имя кандидата для работодателя. Сервер отдаёт обезличенное «Кандидат #<начало id>»: у кандидатов с похожими
 * идентификаторами оно совпадает, поэтому подставляем хвост id, который различается.
 */
export const candidateDisplayName = (id: string, fullName?: string | null): string => {
  if (fullName && !fullName.startsWith('Кандидат #')) return fullName;
  return `Кандидат #${id.replace(/-/g, '').slice(-6).toUpperCase()}`;
};

export const initials = (fullName?: string, fallback = '—'): string => {
  const letters = (fullName ?? '')
    .replace(/\(.*?\)/g, '')
    .replace(/[^\p{L}\s-]/gu, ' ')
    .split(/[\s-]+/)
    .filter((part) => part && !LEGAL_FORMS.has(part.toUpperCase()))
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
  return letters || fallback;
};

/** «ВСЕРОССИЙСКИЙ» → «Всероссийский». */
export const sentenceCase = (value: string): string =>
  value ? value.charAt(0).toUpperCase() + value.slice(1).toLowerCase() : value;

/** API отдаёт время UTC, часто без суффикса «Z»: без него браузер сочтёт строку местным временем и сдвинет дату. */
export const parseApiDate = (iso: string): Date => new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);

export const formatDate = (iso: string): string => {
  const d = parseApiDate(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('ru-RU');
};

/** Контрольная сумма ИНН по алгоритму ФНС (10 цифр — юрлицо, 12 — ИП/физлицо). */
export const isValidInn = (inn: string): boolean => {
  if (!/^\d{10}$|^\d{12}$/.test(inn)) return false;
  const d = inn.split('').map(Number);
  const check = (weights: number[], index: number) =>
    (weights.reduce((sum, w, i) => sum + w * d[i], 0) % 11) % 10 === d[index];
  if (inn.length === 10) return check([2, 4, 10, 3, 5, 9, 4, 6, 8], 9);
  return check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 10) && check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8], 11);
};

/** Сколько полных суток осталось до даты (0, если дата пустая или прошла). */
export const daysUntil = (iso?: string | null): number => {
  if (!iso) return 0;
  const ms = parseApiDate(iso).getTime() - Date.now();
  return Number.isNaN(ms) || ms <= 0 ? 0 : Math.ceil(ms / 86400000);
};

export const formatDateTime = (iso?: string | null): string => {
  if (!iso) return '—';
  const d = parseApiDate(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
};
