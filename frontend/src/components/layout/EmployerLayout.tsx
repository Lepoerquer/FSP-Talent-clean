import React from 'react';
import { Badge, Box, Group, Text } from '@mantine/core';
import { IconSearch, IconSparkles, IconBuildingSkyscraper, IconSend, IconShieldCheck } from '@tabler/icons-react';
import { PortalShell, PortalNavItem } from './PortalShell';
import { useCompany, useCompanyInvitations } from '../../hooks/queries';

export const EmployerLayout: React.FC = () => {
  const { data: company } = useCompany();
  const { data: invitations = [] } = useCompanyInvitations();

  const accepted = invitations.filter((i) => i.status === 'ACCEPTED').length;

  const navItems: PortalNavItem[] = [
    { label: 'Подбор по потребности', to: '/employer/matching', icon: IconSparkles },
    { label: 'Банк кандидатов', to: '/employer/bank', icon: IconSearch },
    {
      label: 'Приглашения',
      to: '/employer/invitations',
      icon: IconSend,
      badge:
        invitations.length > 0 ? (
          <Badge size="sm" circle color="gray" variant="light" aria-label={`Отправлено: ${invitations.length}`}>
            {invitations.length}
          </Badge>
        ) : undefined,
    },
    { label: 'Профиль компании', to: '/employer/company', icon: IconBuildingSkyscraper },
  ];

  const footer = !company ? undefined : (
    <Box className="side-widget">
      <Text className="side-widget-title">Организация</Text>
      <Text size="xs" fw={600} mb={6} truncate>
        {company.name}
      </Text>
      <Group gap={6} mb={6}>
        <Badge
          size="sm"
          variant="light"
          color={company.is_verified ? 'teal' : 'orange'}
          leftSection={<IconShieldCheck size={12} />}
        >
          {company.is_verified ? 'ИНН проверен' : 'ИНН не проверен'}
        </Badge>
      </Group>
      <Text size="xs" c="dimmed">
        Приглашений принято: {accepted} из {invitations.length}
      </Text>
    </Box>
  );

  return <PortalShell sectionLabel="Кабинет работодателя" navItems={navItems} footer={footer} />;
};
