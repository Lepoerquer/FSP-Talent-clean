import React from 'react';
import { Badge, Box, Group, Text } from '@mantine/core';
import { IconUserCircle, IconBrain, IconMailCheck, IconShieldCheck, IconTrophy, IconFileText } from '@tabler/icons-react';
import { FspStarIcon } from '../common/FspStarIcon';
import { PortalShell, PortalNavItem } from './PortalShell';
import { isOpenInvitation, useCandidateInvitations, useGradeStatus, useProfile } from '../../hooks/queries';
import { daysUntil } from '../../utils/format';
import { formatCount } from '../../utils/format';

export const CandidateLayout: React.FC = () => {
  const { data: profile } = useProfile();
  const { data: grade } = useGradeStatus();
  const { data: invitations = [] } = useCandidateInvitations();

  const openInvitations = invitations.filter(isOpenInvitation).length;
  const hasFsp = Boolean(profile?.is_fsp_verified);

  const navItems: PortalNavItem[] = [
    { label: 'Профиль и обзор', to: '/candidate', icon: IconUserCircle, end: true },
    { label: 'Анкета и резюме', to: '/candidate/onboarding', icon: IconFileText },
    { label: 'Квалификационный тест', to: '/candidate/assessment', icon: IconBrain },
    {
      label: 'Приглашения',
      to: '/candidate/invitations',
      icon: IconMailCheck,
      badge:
        openInvitations > 0 ? (
          <Badge size="sm" circle color="fspPink" variant="filled" aria-label={`Ожидают ответа: ${openInvitations}`}>
            {openInvitations}
          </Badge>
        ) : undefined,
    },
    {
      label: 'ФСП ID и достижения',
      to: '/candidate/fsp',
      icon: FspStarIcon,
      badge: (
        <Badge size="xs" variant="light" color={hasFsp ? 'teal' : 'gray'}>
          {hasFsp ? 'Привязан' : 'Не привязан'}
        </Badge>
      ),
    },
    { label: 'Приватность и согласия', to: '/candidate/vacancies', icon: IconMailCheck },
    { label: 'Настройки', to: '/candidate/settings', icon: IconShieldCheck },
  ];

  const days = daysUntil(grade?.next_grade_change_available_at);
  const attempt = grade?.regular_attempt;

  const footer = !profile ? undefined : (
    <Box className="side-widget">
      <Text className="side-widget-title">Смена грейда</Text>
      {!profile.is_grade_confirmed ? (
        <Text size="xs" c="dimmed">
          {attempt?.message ?? 'Грейд не подтверждён. Пройдите квалификационный тест.'}
        </Text>
      ) : days > 0 ? (
        <Text size="xs" c="dimmed">
          Повторный тест на смену грейда доступен через{' '}
          <Text span fw={700} c="var(--fsp-ink)">
            {formatCount(days, ['день', 'дня', 'дней'])}
          </Text>
          .
        </Text>
      ) : (
        <Group gap={6}>
          <Badge color="teal" variant="light" size="sm">
            Доступно
          </Badge>
          <Text size="xs" c="dimmed">
            Можно пройти тест на другой грейд
          </Text>
        </Group>
      )}
    </Box>
  );

  return <PortalShell sectionLabel="Кабинет кандидата" navItems={navItems} footer={footer} />;
};
