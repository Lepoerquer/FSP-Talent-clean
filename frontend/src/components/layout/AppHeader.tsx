import React from 'react';
import { ActionIcon, Avatar, Box, Burger, Button, Group, Menu, Text, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconChevronDown, IconLogout, IconMoon, IconPresentation, IconSun, IconUserCircle } from '@tabler/icons-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { homePathForRole, useAuth } from '../../auth/AuthContext';
import { fullName, useCompany, useProfile } from '../../hooks/queries';
import { initials } from '../../utils/format';
import fspLogo from '../../assets/fsp-logo.svg';

interface AppHeaderProps {
  navbarOpened?: boolean;
  onToggleNavbar?: () => void;
}

export const AppHeader: React.FC<AppHeaderProps> = ({ navbarOpened = false, onToggleNavbar }) => {
  const { session, role, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: profile } = useProfile();
  const { data: company } = useCompany();

  const userName = role === 'EMPLOYER' ? company?.name ?? session?.user.email ?? '' : fullName(profile ?? { email: session?.user.email });
  const userRole = role === 'EMPLOYER' ? 'Работодатель' : 'Соискатель';
  const onExpertsPage = location.pathname === '/demo';

  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme('light', { getInitialValueInEffect: true });
  const toggleColorScheme = () => {
    setColorScheme(computedColorScheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <Box className="app-header">
      <Group h="100%" px={{ base: 10, sm: 16 }} justify="space-between" wrap="nowrap" gap="xs">
        <Group gap="xs" wrap="nowrap">
          {onToggleNavbar && (
            <Burger
              opened={navbarOpened}
              onClick={onToggleNavbar}
              hiddenFrom="md"
              size="sm"
              color="white"
              aria-label={navbarOpened ? 'Закрыть меню' : 'Открыть меню'}
              aria-expanded={navbarOpened}
            />
          )}
          <UnstyledButton onClick={() => navigate(session ? homePathForRole(role) : '/login')} aria-label="На главную страницу" className="brand">
            <Group gap="sm" wrap="nowrap">
              <img src={fspLogo} alt="ФСП" width={32} height={32} />
              <Box>
                <Text className="brand-title">ФСП Талант</Text>
                <Text className="brand-subtitle" visibleFrom="sm">
                  Платформа подбора ИТ-специалистов
                </Text>
              </Box>
            </Group>
          </UnstyledButton>
        </Group>

        <Group gap="xs" wrap="nowrap">
          <Button
            component={Link}
            to="/demo"
            visibleFrom="sm"
            variant={onExpertsPage ? 'white' : 'outline'}
            color={onExpertsPage ? 'dark' : 'gray.0'}
            className={onExpertsPage ? undefined : 'header-ghost'}
            size="xs"
            leftSection={<IconPresentation size={16} />}
          >
            Для экспертов
          </Button>

          <Tooltip
            label={computedColorScheme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
            withArrow
          >
            <ActionIcon
              variant="subtle"
              color="gray.0"
              size="lg"
              radius="sm"
              onClick={toggleColorScheme}
              aria-label={computedColorScheme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
              style={{ color: '#fff' }}
            >
              {computedColorScheme === 'dark' ? <IconSun size={18} stroke={1.8} /> : <IconMoon size={18} stroke={1.8} />}
            </ActionIcon>
          </Tooltip>

          {session ? (
            <Menu position="bottom-end" width={240} shadow="md">
              <Menu.Target>
                <UnstyledButton className="user-trigger" aria-label="Меню пользователя">
                  <Group gap="xs" wrap="nowrap">
                    <Avatar size={32} radius="xl" color="fspBlue" variant="filled">
                      {initials(userName, '·')}
                    </Avatar>
                    <Box visibleFrom="lg" style={{ lineHeight: 1.2, textAlign: 'left' }}>
                      <Text size="xs" fw={600} c="white" truncate maw={180}>
                        {userName}
                      </Text>
                      <Text size="xs" c="gray.4">
                        {userRole}
                      </Text>
                    </Box>
                    <IconChevronDown size={14} color="#c9ccd3" />
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>{session.user.email}</Menu.Label>
                <Menu.Item leftSection={<IconUserCircle size={16} />} onClick={() => navigate(homePathForRole(role))}>
                  Личный кабинет
                </Menu.Item>
                <Menu.Item leftSection={<IconPresentation size={16} />} onClick={() => navigate('/demo')} hiddenFrom="sm">
                  Для экспертов
                </Menu.Item>
                <Menu.Item
                  leftSection={computedColorScheme === 'dark' ? <IconSun size={16} /> : <IconMoon size={16} />}
                  onClick={toggleColorScheme}
                >
                  {computedColorScheme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                </Menu.Item>
                <Menu.Divider />
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={() => {
                    logout();
                    navigate('/login', { replace: true });
                  }}
                >
                  Выйти
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          ) : (
            <Group gap="xs" wrap="nowrap">
              <Button component={Link} to="/login" size="xs" variant="outline" className="header-ghost">
                Войти
              </Button>
              <Button component={Link} to="/register" size="xs">
                Регистрация
              </Button>
            </Group>
          )}
        </Group>
      </Group>
    </Box>
  );
};
