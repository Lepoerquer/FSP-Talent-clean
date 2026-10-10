import { useCallback, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useProfile } from './queries';

/**
 * Анкета кандидата: опыт, стек, soft-skills, роли, «о себе». Источник — профиль на сервере (его видит работодатель
 * и PDF-профиль; стек участвует в подборе как «заявлено кандидатом»). Копия в браузере нужна только для имени
 * загруженного файла резюме и для анкет, заполненных до того, как сервер начал хранить эти поля.
 */
export interface ProfileExtras {
  experience_years?: number;
  stack: string[];
  soft_skills: string[];
  roles: string[];
  about: string;
  resume_file?: string;
}

const EMPTY: ProfileExtras = { stack: [], soft_skills: [], roles: [], about: '' };
const keyFor = (userId: string) => `fsp_talent_extras_${userId}`;

/** Список из текстового поля профиля («Python, FastAPI» → ['Python', 'FastAPI']). */
export const splitList = (value?: string | null): string[] =>
  (value ?? '')
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);

const read = (userId: string): ProfileExtras => {
  try {
    const raw = localStorage.getItem(keyFor(userId));
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<ProfileExtras>) } : EMPTY;
  } catch {
    return EMPTY;
  }
};

export const useExtras = (): [ProfileExtras, (patch: Partial<ProfileExtras>) => void] => {
  const { session } = useAuth();
  const userId = session?.user.id ?? 'anon';
  const [local, setLocal] = useState<ProfileExtras>(() => read(userId));
  const { data: profile } = useProfile();

  const update = useCallback(
    (patch: Partial<ProfileExtras>) => {
      setLocal((prev) => {
        const next = { ...prev, ...patch };
        try {
          localStorage.setItem(keyFor(userId), JSON.stringify(next));
        } catch {
          /* хранилище недоступно: данные живут до перезагрузки */
        }
        return next;
      });
    },
    [userId]
  );

  const merged = useMemo<ProfileExtras>(() => {
    if (!profile) return local;
    const fromServer = (value: string | null | undefined, fallback: string[]) => (value != null ? splitList(value) : fallback);
    return {
      ...local,
      experience_years: profile.experience_years ?? local.experience_years,
      stack: fromServer(profile.stack, local.stack),
      soft_skills: fromServer(profile.soft_skills, local.soft_skills),
      roles: fromServer(profile.roles, local.roles),
      about: profile.about_me ?? local.about,
    };
  }, [profile, local]);

  return [merged, update];
};
