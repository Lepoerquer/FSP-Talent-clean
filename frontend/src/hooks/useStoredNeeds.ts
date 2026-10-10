import { useCallback, useState } from 'react';
import { useCompany } from './queries';

/**
 * Потребности (вакансии) компании, созданные с этого устройства. На сервере есть создание и подбор по потребности,
 * но нет списка потребностей компании, поэтому история хранится в браузере и позволяет вернуться к прежним подборкам.
 */
export interface StoredNeed {
  id: string;
  title: string;
  specialization: string;
  grade: string;
  skills: string[];
  salaryFrom?: number | null;
  salaryTo?: number | null;
  salaryType?: string | null;
  workFormat?: string | null;
  source: 'TEXT' | 'ATS';
  createdAt: string;
}

const MAX_STORED = 12;
const keyFor = (companyId: string) => `fsp_talent_needs_${companyId}`;

const read = (companyId?: string): StoredNeed[] => {
  if (!companyId) return [];
  try {
    return JSON.parse(localStorage.getItem(keyFor(companyId)) ?? '[]') as StoredNeed[];
  } catch {
    return [];
  }
};

export const useStoredNeeds = (): [StoredNeed[], (need: StoredNeed) => void] => {
  const { data: company } = useCompany();
  const companyId = company?.id;
  const [loadedFor, setLoadedFor] = useState<string | undefined>();
  const [needs, setNeeds] = useState<StoredNeed[]>([]);

  // Состояние подтягивается из хранилища, как только известна компания.
  if (companyId && loadedFor !== companyId) {
    setLoadedFor(companyId);
    setNeeds(read(companyId));
  }

  const add = useCallback(
    (need: StoredNeed) => {
      if (!companyId) return;
      setNeeds((prev) => {
        const next = [need, ...prev.filter((n) => n.id !== need.id)].slice(0, MAX_STORED);
        try {
          localStorage.setItem(keyFor(companyId), JSON.stringify(next));
        } catch {
          /* без хранилища история живёт до перезагрузки */
        }
        return next;
      });
    },
    [companyId]
  );

  return [needs, add];
};
