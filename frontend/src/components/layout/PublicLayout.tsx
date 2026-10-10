import React from 'react';
import { AppShell } from '@mantine/core';
import { Outlet } from 'react-router-dom';
import { AppHeader } from './AppHeader';

/** Каркас страниц без бокового меню: вход, регистрация, материалы для экспертов. */
export const PublicLayout: React.FC = () => (
  <AppShell header={{ height: 60 }} padding={{ base: 'sm', sm: 'md', md: 'lg' }} styles={{ main: { backgroundColor: 'var(--fsp-bg)' } }}>
    <AppShell.Header className="shell-header">
      <AppHeader />
    </AppShell.Header>
    <AppShell.Main>
      <Outlet />
    </AppShell.Main>
  </AppShell>
);
