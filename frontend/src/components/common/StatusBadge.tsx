import React from 'react';
import { Badge } from '@mantine/core';
import { IconCheck, IconClock, IconEye, IconEyeOff, IconSend, IconX } from '@tabler/icons-react';
import { INVITATION_STATUS, InvitationStatusCode } from '../../utils/labels';

const ICONS: Record<InvitationStatusCode, React.ReactNode> = {
  SENT: <IconClock size={12} />,
  APPLIED: <IconSend size={12} />,
  VIEWED: <IconEye size={12} />,
  ACCEPTED: <IconCheck size={12} />,
  DECLINED: <IconX size={12} />,
  WITHDRAWN: <IconX size={12} />,
  EXPIRED: <IconClock size={12} />,
  CONTACTS_REVOKED: <IconEyeOff size={12} />,
};

/** Статус приглашения: отправлено → просмотрено → принято / отклонено (п. 2.2 ТЗ). */
export const InvitationStatusBadge: React.FC<{ status: string; expired?: boolean }> = ({ status, expired }) => {
  const code = (expired && (status === 'SENT' || status === 'VIEWED') ? 'EXPIRED' : status) as InvitationStatusCode;
  const c = INVITATION_STATUS[code] ?? { label: status, color: 'gray', variant: 'outline' as const };
  return (
    <Badge color={c.color} variant={c.variant} leftSection={ICONS[code]}>
      {c.label}
    </Badge>
  );
};
