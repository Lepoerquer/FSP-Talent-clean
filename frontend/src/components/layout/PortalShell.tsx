import React from 'react';
import { AppShell, Box, NavLink, ScrollArea, Stack, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { AppHeader } from './AppHeader';

export interface PortalNavItem {
  label: string;
  to: string;
  icon: React.ElementType;
  /** true — пункт активен только при точном совпадении пути */
  end?: boolean;
  badge?: React.ReactNode;
}

interface PortalShellProps {
  sectionLabel: string;
  navItems: PortalNavItem[];
  footer?: React.ReactNode;
}

/** Общий каркас кабинетов: тёмная шапка, боковое меню, адаптивное сворачивание на узких экранах. */
export const PortalShell: React.FC<PortalShellProps> = ({ sectionLabel, navItems, footer }) => {
  const location = useLocation();
  const [opened, { toggle, close }] = useDisclosure(false);

  const isActive = (item: PortalNavItem) =>
    item.end ? location.pathname === item.to : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 288, breakpoint: 'md', collapsed: { mobile: !opened } }}
      padding={{ base: 'sm', sm: 'md', md: 'lg' }}
      styles={{ main: { backgroundColor: 'var(--fsp-bg)' } }}
    >
      <AppShell.Header className="shell-header">
        <AppHeader navbarOpened={opened} onToggleNavbar={toggle} />
      </AppShell.Header>

      <AppShell.Navbar p="md" className="shell-navbar" aria-label="Основная навигация">
        <AppShell.Section grow component={ScrollArea}>
          <Text className="nav-section-label">{sectionLabel}</Text>
          <Stack gap={2}>
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                component={Link}
                to={item.to}
                className="nav-link"
                label={item.label}
                leftSection={<item.icon size={18} stroke={1.6} />}
                rightSection={item.badge}
                active={isActive(item)}
                onClick={close}
                aria-current={isActive(item) ? 'page' : undefined}
              />
            ))}
          </Stack>
        </AppShell.Section>

        {footer && (
          <AppShell.Section pt="md">
            <Box>{footer}</Box>
          </AppShell.Section>
        )}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
};
