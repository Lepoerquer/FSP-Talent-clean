// Подписи для кодов, которые возвращает API. Источник значений — модели и схемы бэкенда.

export const GRADE_LABELS: Record<string, string> = {
  INTERN: 'Стажёр',
  JUNIOR: 'Junior',
  MIDDLE: 'Middle',
  SENIOR: 'Senior',
  LEAD: 'Lead',
};

const SPEC_LABELS: Record<string, string> = {
  BACKEND: 'Backend',
  FRONTEND: 'Frontend',
  QA: 'QA',
  DATA_ML: 'Data / ML',
  DEVOPS: 'DevOps',
  MOBILE: 'Mobile',
};

const norm = (v?: string | null) => (v ?? '').trim().toUpperCase().replace(/[\s/-]+/g, '_');

export const gradeLabel = (code?: string | null): string => (code ? GRADE_LABELS[norm(code)] ?? code : '—');

/** Принимает и код (BACKEND), и название («Backend», «Data / ML»). */
export const specLabel = (value?: string | null): string => {
  if (!value) return '—';
  const key = norm(value);
  if (SPEC_LABELS[key]) return SPEC_LABELS[key];
  if (key.startsWith('DATA')) return SPEC_LABELS.DATA_ML;
  return value;
};

export const WORK_FORMAT_LABELS: Record<string, string> = {
  REMOTE: 'Удалённо',
  HYBRID: 'Гибрид',
  OFFICE: 'Офис',
};
/** Каноничный код специализации по коду или названию («Backend» и «BACKEND» → BACKEND, «Data / ML» → DATA_ML). */
export const specCode = (value?: string | null): string => {
  const key = norm(value);
  if (!key) return '';
  if (key.startsWith('DATA')) return 'DATA_ML';
  return key.replace(/_+/g, '_');
};

export const workFormatLabel = (v?: string | null) => (v ? WORK_FORMAT_LABELS[v] ?? v : '—');

export const PROFILE_STATUS_LABELS: Record<string, string> = {
  ACTIVELY_SEARCHING: 'Активно ищу работу',
  OPEN: 'Открыт к предложениям',
  HIDDEN: 'Скрыт от работодателей',
};

export const FSP_LEVEL_LABELS: Record<string, string> = {
  INTERNATIONAL: 'Международный',
  ALL_RUSSIAN: 'Всероссийский',
  INTERREGIONAL: 'Межрегиональный',
  REGIONAL: 'Региональный',
  LOCAL: 'Местный',
};
export const FSP_RESULT_LABELS: Record<string, string> = {
  WINNER: 'Победитель',
  PRIZE_WINNER: 'Призёр',
  FINALIST: 'Финалист',
  PARTICIPANT: 'Участник',
};
export const fspLevelLabel = (v?: string | null) => (v ? FSP_LEVEL_LABELS[norm(v)] ?? v : '—');
export const fspResultLabel = (v?: string | null) => (v ? FSP_RESULT_LABELS[norm(v)] ?? v : '—');

export type InvitationStatusCode =
  | 'SENT'
  | 'APPLIED'
  | 'VIEWED'
  | 'ACCEPTED'
  | 'DECLINED'
  | 'WITHDRAWN'
  | 'EXPIRED'
  | 'CONTACTS_REVOKED';

export const INVITATION_STATUS: Record<InvitationStatusCode, { label: string; color: string; variant: 'light' | 'filled' | 'outline' }> = {
  SENT: { label: 'Отправлено', color: 'blue', variant: 'light' },
  APPLIED: { label: 'Отклик кандидата', color: 'cyan', variant: 'light' },
  VIEWED: { label: 'Просмотрено', color: 'violet', variant: 'light' },
  ACCEPTED: { label: 'Принято', color: 'teal', variant: 'filled' },
  DECLINED: { label: 'Отклонено', color: 'gray', variant: 'outline' },
  WITHDRAWN: { label: 'Отозвано', color: 'gray', variant: 'outline' },
  EXPIRED: { label: 'Истёк срок', color: 'orange', variant: 'light' },
  CONTACTS_REVOKED: { label: 'Контакты скрыты', color: 'gray', variant: 'outline' },
};

export const DECLINE_REASON_LABELS: Record<string, string> = {
  SALARY: 'Уровень компенсации ниже ожиданий',
  TECH_STACK: 'Не подходит технологический стек',
  FORMAT: 'Не подходит формат работы',
  NOT_LOOKING: 'Временно не рассматриваю предложения',
  OTHER: 'Другая причина',
};

export const CONTACT_METHOD_LABELS: Record<string, string> = {
  TELEGRAM: 'Telegram',
  EMAIL: 'Эл. почта',
  PHONE: 'Телефон',
};

export const TOPIC_LEVEL_LABELS: Record<string, { label: string; color: string }> = {
  STRONG: { label: 'Сильная сторона', color: 'teal' },
  ON_LEVEL: { label: 'На уровне', color: 'blue' },
  GROWTH: { label: 'Зона роста', color: 'orange' },
};

export const RECOMMENDATION_LABELS: Record<string, string> = {
  CONFIRMED: 'Грейд подтверждён',
  OFFER_LOWER_GRADE: 'Предложен тест на грейд ниже',
  OFFER_HIGHER_GRADE: 'Предложен тест на грейд выше',
  KEEP_CURRENT: 'Текущая категория сохранена',
};

export const SCORE_COMPONENT_LABELS: Record<string, string> = {
  C: 'Категория',
  S: 'Стек',
  E: 'Описание',
  T: 'Тест',
  F: 'ФСП',
  A: 'Актуальность',
};
