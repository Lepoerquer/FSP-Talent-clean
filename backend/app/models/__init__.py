try:
    from backend.app.models.assessment import (
        AssessmentSession,
        ItemFamily,
        SessionItem,
    )
    from backend.app.models.candidate import (
        CandidateProfile,
        CandidateSkill,
        CandidateSpecialization,
        FSPAchievement,
        GradeHistory,
    )
    from backend.app.models.company import (
        Company,
        EmployerMember,
        Need,
        SelectionSnapshot,
        ShortlistItem,
        Vacancy,
        EmployerChallenge,
        EmployerChallengeSubmission,
    )
    from backend.app.models.dictionary import (
        Category,
        Direction,
        Grade,
        Skill,
        SkillSynonym,
        Specialization,
    )
    from backend.app.models.invitation import (
        AuditLog,
        DeclineReason,
        Invitation,
        InvitationStatus,
    )
    from backend.app.models.user import Consent, User
    from backend.app.models.chat import ChatMessageModel
except ImportError:
    from app.models.assessment import (
        AssessmentSession,
        ItemFamily,
        SessionItem,
    )
    from app.models.candidate import (
        CandidateProfile,
        CandidateSkill,
        CandidateSpecialization,
        FSPAchievement,
        GradeHistory,
    )
    from app.models.company import (
        Company,
        EmployerMember,
        Need,
        SelectionSnapshot,
        ShortlistItem,
        Vacancy,
        EmployerChallenge,
        EmployerChallengeSubmission,
    )
    from app.models.dictionary import (
        Category,
        Direction,
        Grade,
        Skill,
        SkillSynonym,
        Specialization,
    )
    from app.models.invitation import (
        AuditLog,
        DeclineReason,
        Invitation,
        InvitationStatus,
    )
    from app.models.user import Consent, User
    from app.models.chat import ChatMessageModel

__all__ = [
    # User & Consent (152-FZ)
    "User",
    "Consent",
    # Candidate profile & records
    "CandidateProfile",
    "CandidateSkill",
    "CandidateSpecialization",
    "GradeHistory",
    "FSPAchievement",
    # Company, Employer & Vacancies
    "Company",
    "EmployerMember",
    "Need",
    "SelectionSnapshot",
    "ShortlistItem",
    "Vacancy",
    "EmployerChallenge",
    "EmployerChallengeSubmission",
    # Invitations & Auditing
    "Invitation",
    "InvitationStatus",
    "DeclineReason",
    "AuditLog",
    # Assessment & Testing (IRT 2PL / CAT)
    "ItemFamily",
    "AssessmentSession",
    "SessionItem",
    # Dictionaries
    "Direction",
    "Specialization",
    "Grade",
    "Category",
    "Skill",
    "SkillSynonym",
    "ChatMessageModel",
]
