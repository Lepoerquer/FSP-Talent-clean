import { useQuery } from '@tanstack/react-query';
import { api, CandidateProfile, Invitation } from '../api/api';
import { useAuth } from '../auth/AuthContext';

/** Ключи запросов: единое место для инвалидации кэша после изменений. */
export const keys = {
  profile: ['profile'] as const,
  grade: ['grade'] as const,
  consents: ['consents'] as const,
  company: ['company'] as const,
  candidateInvitations: ['invitations', 'candidate'] as const,
  companyInvitations: ['invitations', 'company'] as const,
  challenges: ['challenges'] as const,
  dictionaries: ['dictionaries'] as const,
};

/** Профиль с обязательными списками: в схеме API они помечены необязательными из-за значений по умолчанию. */
export type ProfileView = Omit<CandidateProfile, 'skills' | 'fsp_achievements'> & {
  skills: NonNullable<CandidateProfile['skills']>;
  fsp_achievements: NonNullable<CandidateProfile['fsp_achievements']>;
};

export const useProfile = () => {
  const { role } = useAuth();
  return useQuery({
    queryKey: keys.profile,
    queryFn: api.profile,
    enabled: role === 'CANDIDATE',
    select: (p): ProfileView => ({ ...p, skills: p.skills ?? [], fsp_achievements: p.fsp_achievements ?? [] }),
  });
};

export const useGradeStatus = () => {
  const { data: profile } = useProfile();
  return useQuery({
    queryKey: [...keys.grade, profile?.id],
    queryFn: () => api.gradeStatus(),
    enabled: Boolean(profile?.id),
  });
};

export const useConsents = () => {
  const { role } = useAuth();
  return useQuery({ queryKey: keys.consents, queryFn: api.consents, enabled: role === 'CANDIDATE' });
};

export const useCompany = () => {
  const { role } = useAuth();
  return useQuery({ queryKey: keys.company, queryFn: api.company, enabled: role === 'EMPLOYER' });
};

/** Незакрытые приглашения компании по id кандидата: повторно приглашать такого кандидата нельзя. */
export const useInvitedMap = () => {
  const { data = [] } = useCompanyInvitations();
  const map = new Map<string, { status: string; expired?: boolean }>();
  for (const inv of data) {
    const active = ['SENT', 'VIEWED', 'ACCEPTED'].includes(inv.status) && !inv.is_expired;
    if (active && !map.has(inv.candidate_profile_id)) map.set(inv.candidate_profile_id, { status: inv.status, expired: inv.is_expired });
  }
  return map;
};

export const useCandidateInvitations = () => {
  const { role } = useAuth();
  return useQuery({ queryKey: keys.candidateInvitations, queryFn: () => api.candidateInvitations(), enabled: role === 'CANDIDATE' });
};

export const useCompanyInvitations = () => {
  const { role } = useAuth();
  return useQuery({ queryKey: keys.companyInvitations, queryFn: () => api.companyInvitations(), enabled: role === 'EMPLOYER' });
};

export const useChallenges = () => {
  const { role } = useAuth();
  return useQuery({ queryKey: keys.challenges, queryFn: api.challenges, enabled: role === 'CANDIDATE' });
};

/** Справочники меняются редко: кэшируются на всё время сессии. */
export const useDictionaries = () =>
  useQuery({
    queryKey: keys.dictionaries,
    queryFn: async () => {
      const [directions, specializations, grades] = await Promise.all([api.directions(), api.specializations(), api.grades()]);
      return { directions, specializations, grades };
    },
    staleTime: Infinity,
  });

/** Приглашение ещё ждёт решения кандидата. */
export const isOpenInvitation = (inv: Invitation): boolean =>
  (inv.status === 'SENT' || inv.status === 'VIEWED') && !inv.is_expired;

export const fullName = (p?: { first_name?: string | null; last_name?: string | null; email?: string | null } | null): string => {
  const name = [p?.first_name, p?.last_name].filter(Boolean).join(' ').trim();
  return name || p?.email || 'Кандидат';
};
