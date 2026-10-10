import type { components } from './schema';
import { http } from './http';

/**
 * Типизированный клиент REST API платформы.
 * Типы берутся из src/api/schema.d.ts, который генерируется из docs/openapi/openapi.json
 * (`npm run gen:api`), поэтому интерфейс и документация API не расходятся.
 */
type S = components['schemas'];

export type TokenResponse = S['TokenResponse'];
export type UserResponse = S['UserResponse'];
export type RegisterRequest = S['RegisterRequest'];
export type DirectionResponse = S['DirectionResponse'];
export type SpecializationResponse = S['SpecializationResponse'];
export type GradeResponse = S['GradeResponse'];
export type SkillSearchResponse = S['SkillSearchResponse'];
export type CandidateProfile = S['CandidateProfileResponse'];
export type CandidateProfileUpdate = S['CandidateProfileUpdateRequest'];
export type GradeStatus = S['GradeStatusResponse'];
export type ConsentStatus = S['ConsentStatusResponse'];
export type ConsentType = S['ConsentType'];
export type FSPLink = S['FSPLinkResponse'];
export type AssessmentStart = S['AssessmentStartResponse'];
export type AssessmentItem = S['SessionNextItemResponse'];
export type AssessmentAnswer = S['AssessmentAnswerResponse'];
export type AssessmentFinish = S['AssessmentFinishResponse'];
export type TopicProfileEntry = S['TopicProfileEntry'];
export type Company = S['CompanyResponse'];
export type CompanyUpdate = S['CompanyUpdateRequest'];
export type VerifyInn = S['CompanyVerifyINNResponse'];
export type NeedParse = S['NeedParseResponse'] & {
  parser_source?: 'gigachat' | 'rule_based';
  ai_available?: boolean;
  engine_badge?: string;
};
export type Need = S['NeedResponse'];
export type NeedCreate = S['NeedCreateRequest'];
export type Recommendations = S['RecommendationsResponse'];
export type RankedItem = S['RankedCandidateItem'];
export type ScoreComponents = S['ScoreComponents'];
export type Invitation = S['InvitationResponse'];
export type InvitationCreate = S['InvitationCreate'];
export type DeclineReason = S['DeclineReasonEnum'];
export type Challenge = S['EmployerChallengeItem'];
export type ChallengeCreate = S['EmployerChallengeCreateRequest'];
export type ChallengeSubmission = S['ChallengeSubmissionItem'];
export type CandidateSpecialization = S['CandidateSpecializationResponse'];
export type AtsSyncRequest = S['ATSVacancySyncRequest'];
export type AtsSyncResult = S['ATSVacancySyncResponse'];

/** Карточка кандидата без контактов: поля общие для подборки, поиска и приглашений. */
export type CandidateCard = Partial<S['CandidateAnonymizedCard']> & { id: string };

/** Элемент ответа GET /search/candidates (в схеме не описан, структура — как у подборки плюс веса). */
export interface SearchItem {
  candidate_id: string;
  rank: number;
  total_score: number;
  score_percent: number;
  is_grade_confirmed?: boolean;
  grade_status?: string;
  components: ScoreComponents;
  weights?: Record<string, number>;
  bullet_points: string[];
  fsp_badge: string;
  candidate_card: CandidateCard;
}

export interface SearchFilters {
  specialization?: string;
  grade?: string;
  skills?: string;
  work_format?: string;
  city?: string;
  salary_max?: number;
  has_fsp?: boolean;
  limit?: number;
}

const clean = <T extends object>(params: T): Partial<T> =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null)) as Partial<T>;

export const api = {
  // ---- Здоровье сервера ---------------------------------------------------
  /** Сервер доступен, если открытый справочник отвечает (проверка идёт тем же путём, что и остальные запросы). */
  async health(): Promise<boolean> {
    try {
      const res = await http.get('/dictionaries/overview', { timeout: 5000 });
      return res.status === 200;
    } catch {
      return false;
    }
  },

  // ---- Аутентификация -----------------------------------------------------
  login: async (email: string, password: string) =>
    (await http.post<TokenResponse>('/auth/login', { email, password })).data,
  register: async (body: RegisterRequest) => (await http.post<TokenResponse>('/auth/register', body)).data,
  verifyEmail: async (code: string) => (await http.post<UserResponse>('/auth/verify-email', { code })).data,
  me: async () => (await http.get<UserResponse>('/auth/me')).data,

  // ---- Справочники --------------------------------------------------------
  directions: async () => (await http.get<DirectionResponse[]>('/dictionaries/directions')).data,
  specializations: async () => (await http.get<SpecializationResponse[]>('/dictionaries/specializations')).data,
  grades: async () => (await http.get<GradeResponse[]>('/dictionaries/grades')).data,
  skills: async (q: string, limit = 20) =>
    (await http.get<SkillSearchResponse[]>('/dictionaries/skills', { params: { q, limit } })).data,

  // ---- Профиль кандидата --------------------------------------------------
  profile: async () => (await http.get<CandidateProfile>('/me/profile')).data,
  updateProfile: async (body: CandidateProfileUpdate) => (await http.put<CandidateProfile>('/me/profile', body)).data,
  gradeStatus: async () => (await http.get<GradeStatus>('/me/grade')).data,
  consents: async () => (await http.get<ConsentStatus>('/consents/status')).data,
  giveConsent: async (consent_type: ConsentType) => (await http.post('/consents/give', { consent_type })).data,
  revokeConsent: async (consent_type: ConsentType) => (await http.post('/consents/revoke', { consent_type })).data,
  linkFsp: async (fsp_id: string, consent_given: boolean) =>
    (await http.post<FSPLink>('/me/fsp/link', { fsp_id, consent_given })).data,
  /** PDF-профиль с QR-кодом (стандартизированный паспорт кандидата). */
  profilePdf: async () => (await http.get<Blob>('/me/pdf', { responseType: 'blob' })).data,

  // ---- Тестирование -------------------------------------------------------
  startAssessment: async (body: { candidate_profile_id?: string; specialization: string; target_grade: string; is_express?: boolean }) =>
    (await http.post<AssessmentStart>('/assessments/start', body)).data,
  /** Экспресс-тест без регистрации (для экспертов). */
  startDemoAssessment: async (body: { specialization: string; target_grade: string }) =>
    (await http.post<AssessmentStart>('/assessments/demo/start', body)).data,
  nextItem: async (sessionId: string) => (await http.get<AssessmentItem>(`/assessments/${sessionId}/next`)).data,
  answer: async (sessionId: string, body: { session_item_id: string; response: string; response_time_seconds?: number }) =>
    (await http.post<AssessmentAnswer>(`/assessments/${sessionId}/answer`, body)).data,
  finishAssessment: async (sessionId: string) =>
    (await http.post<AssessmentFinish>(`/assessments/${sessionId}/finish`)).data,

  // ---- Регулярные задания работодателей ----------------------------------
  challenges: async () => (await http.get<Challenge[]>('/candidates/me/challenges')).data,
  createEmployerChallenge: async (body: ChallengeCreate) => (await http.post<Challenge>('/challenges', body)).data,
  employerChallenges: async () => (await http.get<Challenge[]>('/employer/challenges')).data,
  challengeSubmissions: async (id: string) =>
    (await http.get<ChallengeSubmission[]>(`/employer/challenges/${id}/submissions`)).data,
  submitChallenge: async (id: string, solution_text: string) =>
    (await http.post<{ success: boolean; status: string; message: string }>(`/challenges/${id}/submit`, { solution_text })).data,

  // ---- Подбор (работодатель) ---------------------------------------------
  parseNeed: async (text: string, title?: string, provider?: 'auto' | 'gigachat' | 'rules') =>
    (await http.post<NeedParse>('/needs/parse', { text, title, provider: provider || 'auto' })).data,
  createNeed: async (body: NeedCreate) => (await http.post<Need>('/needs', body)).data,
  needs: async (params?: { company_id?: string; limit?: number; offset?: number }) => (await http.get<Need[]>('/needs', { params: clean(params || {}) })).data,
  updateNeed: async (id: string, body: any) => (await http.put<Need>(`/needs/${id}`, body)).data,
  recommendations: async (needId: string, params: { limit?: number; has_fsp?: boolean; save_snapshot?: boolean } = {}) =>
    (await http.get<Recommendations>(`/needs/${needId}/recommendations`, { params: clean(params) })).data,
  snapshots: async (needId: string) =>
    (await http.get<Array<{ id: string; created_at: string; total_found: number }>>(`/needs/${needId}/snapshots`)).data,
  searchCandidates: async (filters: SearchFilters) =>
    (await http.get<{ total_found: number; items: SearchItem[] }>('/search/candidates', { params: clean(filters) })).data,

  // ---- Приглашения --------------------------------------------------------
  createInvitation: async (body: InvitationCreate) => (await http.post<Invitation>('/invitations', body)).data,
  candidateInvitations: async () => (await http.get<Invitation[]>('/invitations/candidate')).data,
  companyInvitations: async (params?: { company_id?: string; status_filter?: string; need_id?: string }) => (await http.get<Invitation[]>('/invitations/company', { params: clean(params || {}) })).data,
  viewInvitation: async (id: string) => (await http.post<Invitation>(`/invitations/${id}/view`)).data,
  acceptInvitation: async (id: string) => (await http.post<Invitation>(`/invitations/${id}/accept`)).data,
  declineInvitation: async (id: string, decline_reason: DeclineReason, feedback?: string) =>
    (await http.post<Invitation>(`/invitations/${id}/decline`, { decline_reason, feedback })).data,
  withdrawInvitation: async (id: string) => (await http.post<Invitation>(`/invitations/${id}/withdraw`)).data,
  revokeContacts: async (id: string) => (await http.post<Invitation>(`/invitations/${id}/revoke-contacts`)).data,
  applyToNeed: async (needId: string) => (await http.post<{ success: boolean; message: string }>(`/needs/${needId}/apply`)).data,

  // ---- Интеграция с ATS (концепция, п. 2 ТЗ «Будет плюсом») ---
  atsSyncVacancy: async (body: AtsSyncRequest) => (await http.post<AtsSyncResult>('/ats/vacancies/sync', body)).data,

  // ---- Компания -----------------------------------------------------------
  company: async () => (await http.get<Company>('/companies/me')).data,
  updateCompany: async (body: CompanyUpdate) => (await http.put<Company>('/companies/me', body)).data,
  verifyInn: async (companyId: string, inn: string, ogrn?: string) =>
    (await http.post<VerifyInn>(`/companies/${companyId}/verify-inn`, { inn, ogrn: ogrn || null })).data,

  // ---- Чат (Bonus) --------------------------------------------------------
  sendMessage: async (body: { message: string; receiver_id: string }) =>
    (await http.post('/chat/messages', body)).data,
  getMessages: async (receiverId?: string) =>
    (await http.get('/chat/messages', { params: receiverId ? { receiver_id: receiverId } : undefined })).data,

  // ---- Несколько специализаций (Bonus) ------------------------------------
  addSpecialization: async (body: { specialization: string; grade: string }) =>
    (await http.post<S['CandidateSpecializationResponse']>('/me/specializations', body)).data,
  getSpecializations: async () =>
    (await http.get<S['CandidateSpecializationResponse'][]>('/me/specializations')).data,

  // ---- GigaChat AI (152-ФЗ) -----------------------------------------------
  aiPitch: async (body: { candidate_id: string; need_id?: string | null; score_percent?: number }) =>
    (await http.post<{ candidate_id: string; pitch: string; provider: string }>('/needs/ai/pitch', body)).data,
  aiInterviewQuestions: async (body: { specialization: string; grade: string; skills?: string[]; count?: number }) =>
    (await http.post<{ specialization: string; grade: string; questions: Array<{ topic: string; question: string; expected_answer: string }>; provider: string }>('/needs/ai/interview-questions', body)).data,
  aiCareerAdvice: async (body: {
    specialization?: string | null;
    grade?: string | null;
    skills?: string[];
    experience_years?: number | null;
    fsp_verified?: boolean;
    percentile?: number | null;
  }) => (await http.post<AICareerAdviceResult>('/needs/ai/career-advice', body)).data,

  // ---- Публичная верификация кандидата (QR-код) ----------------------------
  verifyCandidate: async (id: string) => (await http.get<CandidateVerification>(`/verify/candidates/${id}`)).data,
};

export interface CandidateVerification {
  candidate_id: string;
  name: string;
  confirmed_category?: string | null;
  grade_status: 'CONFIRMED' | 'UNCONFIRMED';
  is_fsp_verified: boolean;
  category_percentile?: number | null;
  confirmed_specialization?: string | null;
  confirmed_grade?: string | null;
  declared_grade?: string | null;
  city?: string | null;
  work_format?: string | null;
  experience_years?: number | null;
  confirmed_skills: string[];
  fsp_achievements_count: number;
  fsp_disciplines: string[];
  verification_hash?: string | null;
  checked_at: string;
}

export interface AICareerRoadmapStep {
  step: string;
  timeframe?: string | null;
  action: string;
}

export interface AICareerAdviceResult {
  specialization: string;
  grade: string;
  overall_summary: string;
  strengths: string[];
  growth_points: string[];
  recommended_fsp_discipline: string;
  fsp_boost_tip: string;
  career_roadmap?: AICareerRoadmapStep[];
  provider: string;
}

