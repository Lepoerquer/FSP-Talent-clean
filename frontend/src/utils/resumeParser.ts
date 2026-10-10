/**
 * Автоматическое распознавание резюме в формате PDF (п. 2.1 ТЗ): извлечение текста в браузере
 * (pdf.js, лицензия Apache-2.0) и разбор полей правилами. Файл не покидает устройство.
 * Результат — подсказка: кандидат проверяет и исправляет значения перед сохранением.
 */

export interface RecognizedResume {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  telegram?: string;
  city?: string;
  work_format?: 'REMOTE' | 'HYBRID' | 'OFFICE';
  about_me?: string;
  desired_salary_min?: number;
  experience_years?: number;
  stack: string[];
  soft_skills: string[];
  roles: string[];
  grade_hint?: 'INTERN' | 'JUNIOR' | 'MIDDLE' | 'SENIOR';
}

export const MAX_RESUME_BYTES = 8 * 1024 * 1024;

/** Извлекает текст из PDF. pdf.js загружается по требованию, чтобы не утяжелять основной бандл. */
export const extractPdfText = async (file: File): Promise<string> => {
  const pdfjs = await import('pdfjs-dist');
  try {
    const workerUrl = (await import('pdfjs-dist/build/pdf.worker.min.mjs?url')).default;
    pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  } catch (e) {
    console.warn('Worker import warning:', e);
  }

  const data = new Uint8Array(await file.arrayBuffer());
  
  let doc;
  try {
    const loadingTask = pdfjs.getDocument({
      data,
      cMapPacked: true,
      standardFontDataUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/standard_fonts/',
      cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/cmaps/',
    });
    doc = await loadingTask.promise;
  } catch (err) {
    console.warn('Primary PDF load failed, attempting fallback getDocument:', err);
    const fallbackTask = pdfjs.getDocument({
      data,
      isEvalSupported: false,
      useSystemFonts: true,
    });
    doc = await fallbackTask.promise;
  }

  const lines: string[] = [];
  for (let p = 1; p <= Math.min(doc.numPages, 6); p++) {
    const page = await doc.getPage(p);
    const content = await page.getTextContent();
    // строки восстанавливаются по вертикальной координате элементов
    let currentY: number | null = null;
    let line = '';
    for (const it of content.items) {
      if (!('str' in it)) continue;
      const y = Math.round(it.transform[5]);
      if (currentY !== null && Math.abs(y - currentY) > 3) {
        lines.push(line.trim());
        line = '';
      }
      currentY = y;
      line += (line && !line.endsWith(' ') && !it.str.startsWith(' ') ? ' ' : '') + it.str;
    }
    if (line.trim()) lines.push(line.trim());
  }
  return lines.filter(Boolean).join('\n');
};

const CITIES = [
  'Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань', 'Нижний Новгород', 'Челябинск', 'Самара', 'Омск',
  'Ростов-на-Дону', 'Уфа', 'Красноярск', 'Воронеж', 'Пермь', 'Волгоград', 'Краснодар', 'Саратов', 'Тюмень', 'Тольятти',
  'Ижевск', 'Барнаул', 'Ульяновск', 'Иркутск', 'Хабаровск', 'Ярославль', 'Владивосток', 'Махачкала', 'Томск', 'Оренбург',
  'Кемерово', 'Новокузнецк', 'Рязань', 'Тула', 'Калининград', 'Сочи', 'Innopolis', 'Иннополис',
];

// Канонические названия совпадают со справочником навыков платформы.
const SKILLS: Array<[string, RegExp]> = [
  ['Python', /\bpython\b/i], ['Java', /\bjava\b(?!\s*script)/i], ['JavaScript', /\bjavascript\b|\bjs\b/i], ['TypeScript', /\btypescript\b|\bts\b/i],
  ['Go', /\bgolang\b|\bgo\b(?=[\s,;])/i], ['Kotlin', /\bkotlin\b/i], ['C#', /(?<![a-z0-9])c#|(?<![a-z0-9@/.])\.net(?![a-z0-9/])/i], ['C++', /c\+\+/i], ['PHP', /\bphp\b/i], ['Ruby', /\bruby\b/i],
  ['Rust', /\brust\b/i], ['Swift', /\bswift\b/i], ['SQL', /\bsql\b/i], ['PostgreSQL', /postgres(ql)?/i], ['MySQL', /\bmysql\b/i], ['MongoDB', /mongo(db)?/i],
  ['Redis', /\bredis\b/i], ['ClickHouse', /clickhouse/i], ['Kafka', /\bkafka\b/i], ['RabbitMQ', /rabbitmq/i], ['Docker', /\bdocker\b/i],
  ['Kubernetes', /kubernetes|\bk8s\b/i], ['Git', /\bgit\b/i], ['Linux', /\blinux\b/i], ['CI/CD', /ci\/cd|gitlab\s*ci|github\s*actions|jenkins/i],
  ['FastAPI', /fastapi/i], ['Django', /django/i], ['Flask', /\bflask\b/i], ['Spring', /\bspring\b/i], ['SQLAlchemy', /sqlalchemy/i],
  ['Asyncio', /asyncio/i], ['Celery', /\bcelery\b/i], ['REST', /\brest(ful)?\b/i], ['GraphQL', /graphql/i], ['gRPC', /grpc/i],
  ['React', /\breact(\.js)?\b/i], ['Next.js', /next\.?js/i], ['Vue', /\bvue(\.js)?\b/i], ['Angular', /\bangular\b/i], ['Redux', /\bredux\b/i],
  ['HTML', /\bhtml5?\b/i], ['CSS', /\bcss3?\b|\bsass\b|\bscss\b/i], ['Webpack', /webpack/i], ['Vite', /\bvite\b/i], ['Jest', /\bjest\b/i],
  ['Playwright', /playwright/i], ['Selenium', /selenium/i], ['Pytest', /pytest/i], ['Postman', /postman/i],
  ['Pandas', /pandas/i], ['NumPy', /numpy/i], ['Scikit-learn', /scikit|sklearn/i], ['PyTorch', /pytorch/i], ['TensorFlow', /tensorflow/i],
  ['Machine Learning', /machine learning|машинн\w+ обучен/i], ['NLP', /\bnlp\b/i], ['Airflow', /airflow/i], ['Spark', /\bspark\b/i],
  ['Terraform', /terraform/i], ['Ansible', /ansible/i], ['Nginx', /nginx/i], ['Prometheus', /prometheus/i], ['Grafana', /grafana/i],
  ['Figma', /\bfigma\b/i], ['Miro', /\bmiro\b/i], ['Adobe Photoshop', /adobe\s*photoshop|\bphotoshop\b/i],
  ['Adobe Illustrator', /adobe\s*illustrator|\billustrator\b/i], ['Sketch', /\bsketch\b/i], ['Adobe XD', /adobe\s*xd|\bxd\b/i],
  ['CJM', /\bcjm\b|customer\s*journey/i], ['UX-исследования', /ux[- ‑]исследован|исследования\s+пользовател/i],
  ['Прототипирование', /прототипирован/i], ['Дизайн-системы', /дизайн[- ‑]систем/i], ['A/B-тестирование', /a\/b[- ‑]тест/i],
];

const SOFT_SKILLS: Array<[string, RegExp]> = [
  ['Коммуникабельность', /коммуникабельн|навыки общения/i],
  ['Работа в команде', /работа в команде|командн\w+ работ|командный игрок/i],
  ['Лидерство', /лидерств|руководство командой|team\s*lead/i],
  ['Наставничество', /наставнич|менторинг|менторство|обучение коллег/i],
  ['Самообучаемость', /самообуч|быстро обуча/i],
  ['Ответственность', /ответственн/i],
  ['Тайм-менеджмент', /тайм-?менеджмент|планирование времени/i],
  ['Аналитическое мышление', /аналитическ\w+ мышлен|системное мышление|(?<![а-яёА-ЯЁa-zA-Z])аналитика(?![а-яёА-ЯЁa-zA-Z])/i],
  ['Стрессоустойчивость', /стрессоустойчив/i],
  ['Дизайн-мышление', /дизайн[- ‑]мышлен/i],
];

const ROLES: Array<[string, RegExp]> = [
  ['Backend-разработчик', /backend|бэкенд|бекенд/i],
  ['Frontend-разработчик', /frontend|фронтенд/i],
  ['Fullstack-разработчик', /full-?stack|фулстек|фуллстек/i],
  ['Mobile-разработчик', /мобильн\w+ разработчик|android|ios[- ]разработчик/i],
  ['Data Scientist', /data scientist|дата[- ]сайентист/i],
  ['ML-инженер', /ml[- ]engineer|ml[- ]инженер|инженер машинного обучения/i],
  ['Аналитик данных', /аналитик данных|data analyst/i],
  ['DevOps-инженер', /devops|\bsre\b/i],
  ['QA-инженер', /\bqa\b|тестировщик|инженер по тестированию/i],
  ['Тимлид', /team\s*lead|тимлид|руководитель (команды|группы)/i],
  ['Архитектор', /архитектор/i],
  ['Продуктовый дизайнер', /продуктов\w+\s+дизайн|дизайнер\s+продукта|product\s+design/i],
  ['UX/UI-дизайнер', /ux[\/ ]ui|ui[\/ ]ux/i],
  ['Дизайнер', /дизайнер|designer/i],
  ['Графический дизайнер', /графическ\w+\s+дизайн/i],
];

const SURNAME_END = /(ов|ова|ев|ева|ёв|ёва|ин|ина|ский|ская|цкий|цкая|ук|юк|ко|ян|ых|их|ой|ий)$/i;
const NON_NAMES = new Set(['Резюме', 'Портфолио', 'Кандидат', 'Контакты', 'Опыт', 'О себе', 'Навыки', 'Скилы', 'Образование', 'Умения', 'Языки']);

const normPhone = (raw: string): string => {
  const d = raw.replace(/[^\dХXхx]/g, '');
  const n = d.length === 11 ? d.slice(1) : d.slice(-10);
  if (n.length === 10) {
    return `+7 (${n.slice(0, 3)}) ${n.slice(3, 6)}-${n.slice(6, 8)}-${n.slice(8, 10)}`;
  }
  return raw.trim();
};

export const parseResumeText = (text: string): RecognizedResume => {
  const out: RecognizedResume = { stack: [], soft_skills: [], roles: [] };
  const cleaned = text.replace(/[\uE000-\uF8FF]/g, ' ').replace(/[‑–—]/g, '-');
  const flat = cleaned.replace(/[ \t]+/g, ' ');

  const email = flat.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
  if (email) out.email = email[0];

  const phone = cleaned.match(/(?:(?:\+?7|8))[\s\-()]*([\dХXхx]{3})[\s\-()]*([\dХXхx]{3})[\s\-()]*([\dХXхx]{2})[\s\-()]*([\dХXхx]{2})/);
  if (phone) {
    out.phone = `+7 (${phone[1]}) ${phone[2]}-${phone[3]}-${phone[4]}`;
  } else {
    const fallbackPhone = flat.match(/(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s-]*\d{2}[\s-]*\d{2}/);
    if (fallbackPhone) out.phone = normPhone(fallbackPhone[0]);
  }

  const withoutEmails = flat.replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, ' ');
  const tg = withoutEmails.match(/(?:t\.me\/|(?:telegram|tg)[:\s]+@?|@)([A-Za-z][A-Za-z0-9_]{3,31})/i);
  if (tg) out.telegram = `@${tg[1]}`;

  // ФИО: проверка одиночных строк и двух последовательных строк
  const rawLines = text
    .split('\n')
    .map((l) => l.replace(/[\uE000-\uF8FF]/g, '').trim())
    .filter(Boolean);

  // 1) Одной строкой (например, "Иван Иванов" или "Иванов Иван Иванович")
  for (const line of rawLines.slice(0, 10)) {
    const m = line.match(/^([А-ЯЁ][а-яё-]+)\s+([А-ЯЁ][а-яё-]+)(?:\s+([А-ЯЁ][а-яё]+))?$/);
    if (!m) continue;
    if (m[3]) {
      out.last_name = m[1];
      out.first_name = m[2];
    } else if (SURNAME_END.test(m[2]) && !SURNAME_END.test(m[1])) {
      out.first_name = m[1];
      out.last_name = m[2];
    } else {
      out.last_name = m[1];
      out.first_name = m[2];
    }
    break;
  }

  // 2) Двумя последовательными строками (например: строка 1 "Иван", строка 2 "Иванов")
  if (!out.first_name || !out.last_name) {
    for (let i = 0; i < Math.min(rawLines.length - 1, 8); i++) {
      const l1 = rawLines[i];
      const l2 = rawLines[i + 1];
      if (NON_NAMES.has(l1) || NON_NAMES.has(l2)) continue;
      const m1 = l1.match(/^([А-ЯЁ][а-яё-]+)$/);
      const m2 = l2.match(/^([А-ЯЁ][а-яё-]+)$/);
      if (m1 && m2) {
        if (SURNAME_END.test(m2[1]) && !SURNAME_END.test(m1[1])) {
          out.first_name = m1[1];
          out.last_name = m2[1];
        } else if (SURNAME_END.test(m1[1]) && !SURNAME_END.test(m2[1])) {
          out.last_name = m1[1];
          out.first_name = m2[1];
        } else {
          out.first_name = m1[1];
          out.last_name = m2[1];
        }
        break;
      }
    }
  }

  out.city = CITIES.find((c) => new RegExp(`\\b${c}\\b`, 'i').test(flat)) ?? CITIES.find((c) => new RegExp(c, 'i').test(flat));
  if (out.city === 'Innopolis') out.city = 'Иннополис';

  // Формат работы (Cyrillic-safe lookaround)
  if (/(?<![а-яёa-z])гибрид(?![а-яёa-z])|предпочтительн\w*\s+вариант[^\n,.]*гибрид/i.test(flat)) {
    out.work_format = 'HYBRID';
  } else if (/(?<![а-яёa-z])удален(?![а-яёa-z])|remote/i.test(flat)) {
    out.work_format = 'REMOTE';
  } else if (/(?<![а-яёa-z])офис(?![а-яёa-z])|office/i.test(flat)) {
    out.work_format = 'OFFICE';
  }

  // О себе
  const aboutMatch = cleaned.match(/(?:^|\n)\s*О себе\s*[:—\-]?\s*([\s\S]*?)(?=(?:\n\s*(?:Опыт|Образование|Скилы|Навыки|Языки|Умения|Портфолио)(?:\s+|[:—\-]|$)|$))/i);
  if (aboutMatch) {
    const rawAbout = aboutMatch[1].replace(/\s+/g, ' ').trim();
    if (rawAbout.length > 5) {
      out.about_me = rawAbout;
    }
  }

  // Опыт работы: из прямого указания или диапазона лет в блоке «Опыт»
  const exp =
    flat.match(/опыт[^.\n\d]{0,40}(\d+(?:[.,]\d)?)\s*(?:лет|года|год)/i) ??
    flat.match(/(\d+(?:[.,]\d)?)\s*(?:лет|года|год)\s*(?:коммерческого\s*)?опыта/i);
  if (exp) {
    out.experience_years = parseFloat(exp[1].replace(',', '.'));
  } else {
    const expBlock = cleaned.match(/(?:^|\n)\s*Опыт\s*[:—\-]?\s*([\s\S]*?)(?=(?:\n\s*(?:Образование|Скилы|Навыки|Языки|Умения)(?:\s+|[:—\-]|$)|$))/i);
    if (expBlock) {
      const years = Array.from(expBlock[1].matchAll(/\b(19\d\d|20\d\d)\b/g)).map((m) => parseInt(m[1], 10));
      if (years.length >= 2) {
        const minYear = Math.min(...years);
        const maxYear = Math.max(...years);
        if (maxYear > minYear && maxYear - minYear <= 50) {
          out.experience_years = maxYear - minYear;
        }
      }
    }
  }

  const salary = flat.match(/(?:зарплат\w*|ожидани\w*|оклад|доход)[^\d\n]{0,40}(\d[\d\s]{4,9})/i) ?? flat.match(/от\s+(\d{2,3}\s?\d{3})\s*(?:₽|руб|р\b)/i);
  if (salary) {
    const value = parseInt(salary[1].replace(/\s/g, ''), 10);
    if (value >= 20000 && value <= 2000000) out.desired_salary_min = value;
  }

  out.stack = SKILLS.filter(([, re]) => re.test(flat)).map(([name]) => name);
  out.soft_skills = SOFT_SKILLS.filter(([, re]) => re.test(flat)).map(([name]) => name);
  out.roles = ROLES.filter(([, re]) => re.test(flat)).map(([name]) => name);

  if (/senior|сеньор|ведущий разработчик|lead|руководитель/i.test(flat)) out.grade_hint = 'SENIOR';
  else if (/middle\+|мидл\+|middle\s*plus/i.test(flat)) out.grade_hint = 'MIDDLE';
  else if (/middle|мидл/i.test(flat)) out.grade_hint = 'MIDDLE';
  else if (/junior|джуниор/i.test(flat)) out.grade_hint = 'JUNIOR';
  else if (/стажёр|стажер|intern/i.test(flat)) out.grade_hint = 'INTERN';
  else if (out.experience_years !== undefined) {
    out.grade_hint = out.experience_years < 1 ? 'INTERN' : out.experience_years < 2.5 ? 'JUNIOR' : out.experience_years < 5 ? 'MIDDLE' : 'SENIOR';
  }
  return out;
};

/** Количество распознанных полей — для подсказки пользователю. */
export const recognizedCount = (r: RecognizedResume): number =>
  [r.first_name, r.last_name, r.phone, r.telegram, r.city, r.work_format, r.about_me, r.desired_salary_min, r.experience_years].filter((v) => v !== undefined).length +
  (r.stack.length ? 1 : 0) +
  (r.soft_skills.length ? 1 : 0) +
  (r.roles.length ? 1 : 0);
