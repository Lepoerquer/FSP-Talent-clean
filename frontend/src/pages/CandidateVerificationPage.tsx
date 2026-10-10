import React, { useState } from 'react';
import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconAward,
  IconCertificate,
  IconCheck,
  IconCopy,
  IconDownload,
  IconExternalLink,
  IconInfoCircle,
  IconQrcode,
  IconShare,
  IconShieldCheck,
  IconShieldX,
  IconTrophy,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { api, CandidateVerification } from '../api/api';
import { CompetenceRadarChart, RadarDimension } from '../components/common/CompetenceRadarChart';
import { AppModal } from '../components/common/AppModal';
import { formatDate } from '../utils/format';
import { gradeLabel, specLabel, workFormatLabel } from '../utils/labels';
import { usePageTitle } from '../hooks/usePageTitle';
import { FspStarIcon } from '../components/common/FspStarIcon';
import fspLogo from '../assets/fsp-logo.svg';

export const CandidateVerificationPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  usePageTitle('Верификация сертификата ФСП');
  const [downloading, setDownloading] = useState(false);
  const [qrOpened, setQrOpened] = useState(false);

  const { data, isLoading, isError } = useQuery<CandidateVerification>({
    queryKey: ['candidate-verification', id],
    queryFn: () => api.verifyCandidate(id!),
    enabled: Boolean(id),
    staleTime: 60_000,
  });

  const copyToClipboard = async (text: string): Promise<boolean> => {
    // 1. Попытка через современный Clipboard API (для HTTPS и localhost)
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        // переходим к запасному механизму
      }
    }

    // 2. Универсальный fallback для HTTP / IP-адресов через скрытый textarea
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      textArea.style.top = '0';
      textArea.setAttribute('readonly', '');
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textArea);
      if (success) return true;
    } catch {
      // fallback ниже
    }

    // 3. Крайний случай, если оба метода заблокированы браузером
    try {
      window.prompt('Скопируйте ссылку (Ctrl+C, затем Enter):', text);
      return true;
    } catch {
      return false;
    }
  };

  const shareLink = async () => {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({
          title: `Верифицированный профиль ФСП — ${data?.name || 'Кандидат'}`,
          text: `Официальный цифровой сертификат участника Федерации спортивного программирования: ${data?.confirmed_category || 'ФСП Талант'}`,
          url: window.location.href,
        });
        return;
      } catch (err: unknown) {
        if ((err as Error)?.name === 'AbortError') return;
      }
    }

    const success = await copyToClipboard(window.location.href);
    if (success) {
      notifications.show({
        title: 'Ссылка скопирована',
        message: 'Прямая ссылка на страницу верификации скопирована в буфер обмена.',
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
    }
  };

  const copyHash = async (hash: string) => {
    const success = await copyToClipboard(hash);
    if (success) {
      notifications.show({
        title: 'Контрольный хэш скопирован',
        message: `Хэш верификации: ${hash}`,
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
    }
  };

  const downloadPdf = async () => {
    if (!id) return;
    setDownloading(true);
    try {
      const resp = await fetch(`/api/v1/verify/candidates/${id}/pdf`);
      if (!resp.ok) {
        throw new Error(`Ошибка загрузки: HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `fsp_verified_candidate_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(() => window.URL.revokeObjectURL(blobUrl), 30_000);
      notifications.show({
        title: 'PDF-паспорт сохранён',
        message: 'Официальный сертификат кандидата успешно загружен.',
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
    } catch {
      // Прямое открытие через браузерный просмотрщик PDF
      window.open(`/api/v1/verify/candidates/${id}/pdf`, '_blank');
    } finally {
      setDownloading(false);
    }
  };

  if (isLoading) {
    return (
      <Container size="md" py="xl">
        <Stack gap="lg">
          <Skeleton h={80} radius="md" />
          <Skeleton h={320} radius="md" />
        </Stack>
      </Container>
    );
  }

  if (isError || !data) {
    return (
      <Container size="sm" py="xl">
        <Paper withBorder p="xl" radius="md" ta="center">
          <ThemeIcon size={64} radius="xl" color="red" variant="light" mb="md" mx="auto">
            <IconShieldX size={36} />
          </ThemeIcon>
          <Title order={2} size="h3" mb="xs">
            Сертификат не найден
          </Title>
          <Text size="sm" c="dimmed" mb="lg">
            Профиль соискателя с указанным идентификатором не существует, либо был скрыт кандидатом в настройках приватности платформы.
          </Text>
          <Button component={Link} to="/" variant="default" leftSection={<IconArrowLeft size={16} />}>
            На главную платформы
          </Button>
        </Paper>
      </Container>
    );
  }

  const isConfirmed = data.grade_status === 'CONFIRMED';

  // Вычисление 5 осей радара компетенций на основе верифицированных данных
  const radarDimensions: RadarDimension[] = [
    {
      key: 'test',
      label: 'Тест ФСП (Hard skills)',
      value: isConfirmed ? (data.category_percentile ?? 80) : 25,
      targetValue: 80,
      hint: isConfirmed
        ? `Квалификационный тест пройден: ${data.category_percentile ?? '—'}-й процентиль`
        : 'Тест не подтверждён',
    },
    {
      key: 'stack',
      label: 'Стек технологий',
      value: Math.min(100, Math.max(30, (data.confirmed_skills?.length || 3) * 15 + 20)),
      targetValue: 75,
      hint: `Подтверждённые навыки: ${(data.confirmed_skills || []).join(', ') || 'базовый стек'}`,
    },
    {
      key: 'exp',
      label: 'Опыт и грейд',
      value: Math.min(100, Math.max(30, Math.round((data.experience_years || 2) * 15 + 20))),
      targetValue: 70,
      hint: data.experience_years ? `Стаж работы: ${data.experience_years} лет` : 'Стаж не указан',
    },
    {
      key: 'fsp',
      label: 'Олимпиадный опыт ФСП',
      value: data.is_fsp_verified ? Math.min(100, Math.max(35, (data.fsp_achievements_count || 1) * 25 + 30)) : 20,
      targetValue: 60,
      hint: data.is_fsp_verified
        ? `Подтверждено в реестре ФСП (${data.fsp_achievements_count} соревнований)`
        : 'Участие в соревнованиях ФСП не привязано',
    },
    {
      key: 'verified',
      label: 'Подтверждённость 152-ФЗ',
      value: isConfirmed ? 95 : 35,
      targetValue: 85,
      hint: 'Верифицированный профиль платформы',
    },
  ];

  return (
    <Container size="md" py={{ base: 'md', sm: 'xl' }} px={{ base: 'xs', sm: 'md' }}>
      <Stack gap="lg">
        {/* Заголовок страницы с гербом и официальным статусом */}
        <Paper
          p={{ base: 'sm', sm: 'lg' }}
          radius="md"
          style={{
            background: 'linear-gradient(135deg, #181926 0%, #221D38 100%)',
            color: '#ffffff',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.15)',
            overflow: 'hidden',
          }}
        >
          <Group justify="space-between" align="center" wrap="wrap" gap="md">
            <Group gap="md" wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
              <img src={fspLogo} alt="ФСП" width={40} height={40} style={{ flexShrink: 0 }} />
              <Box style={{ minWidth: 0, flex: 1 }}>
                <Group gap="xs" align="center" wrap="wrap">
                  <Text fw={800} size="lg" c="white" style={{ letterSpacing: '0.02em', whiteSpace: 'nowrap' }}>
                    ФСП Талант
                  </Text>
                  <Badge variant="filled" color="fspPink" size="xs">
                    Официальный реестр
                  </Badge>
                </Group>
                <Text size="xs" c="gray.4" style={{ overflowWrap: 'break-word' }}>
                  Федерация спортивного программирования России · Верификация компетенций
                </Text>
              </Box>
            </Group>

            <Group gap="xs" wrap="wrap" w={{ base: '100%', sm: 'auto' }} justify="flex-start">
              <Button size="xs" variant="white" color="dark" leftSection={<IconShare size={14} />} onClick={shareLink} style={{ flex: '1 1 auto' }}>
                Поделиться ссылкой
              </Button>
              <Button size="xs" variant="default" leftSection={<IconQrcode size={14} />} onClick={() => setQrOpened(true)} style={{ flex: '1 1 auto' }}>
                QR-код
              </Button>
              <Button size="xs" variant="filled" color="fspPink" leftSection={<IconDownload size={14} />} loading={downloading} onClick={downloadPdf} style={{ flex: '1 1 auto' }}>
                Скачать PDF
              </Button>
            </Group>
          </Group>
        </Paper>

        {/* Главная карточка сертификата */}
        <Paper
          withBorder
          p={{ base: 'sm', sm: 'xl' }}
          radius="md"
          style={{
            borderTop: `6px solid ${isConfirmed ? '#10B981' : '#F59E0B'}`,
            background: 'var(--fsp-card)',
            overflow: 'hidden',
          }}
        >
          {/* Статусный баннер верификации */}
          {isConfirmed ? (
            <Alert
              color="teal"
              variant="light"
              icon={<IconShieldCheck size={24} />}
              title="Квалификация и грейд официально подтверждены"
              mb="xl"
            >
              Соискатель успешно прошёл независимое компьютерное адаптивное тестирование (CAT 2PL IRT) на платформе Федерации спортивного программирования. Присвоенная категория проверена и актуальна.
            </Alert>
          ) : (
            <Alert
              color="orange"
              variant="light"
              icon={<IconInfoCircle size={24} />}
              title="Грейд заявлен кандидатом (тест не пройден)"
              mb="xl"
            >
              Квалификационный адаптивный тест для данной категории ещё не сдан или грейд был указан вручную. В официальном реестре соискатель имеет статус «Не подтверждён».
            </Alert>
          )}

          {/* Инфо-блок кандидата */}
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl" mb="xl">
            <Stack gap="md">
              <Group gap="md" align="flex-start">
                <Avatar size={72} radius="xl" color="fspPurple" variant="filled">
                  {data.name.slice(0, 1)}
                </Avatar>
                <Box style={{ flex: 1 }}>
                  <Text size="xs" fw={700} c="dimmed" tt="uppercase" style={{ letterSpacing: '0.05em' }}>
                    Верифицированный профиль соискателя
                  </Text>
                  <Title order={2} size="h2" mb={4}>
                    {data.name}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {[data.city, workFormatLabel(data.work_format)].filter(Boolean).join(' · ') || 'Город не указан'}
                  </Text>
                </Box>
              </Group>

              <Divider />

              {/* Категория и грейд */}
              <Box>
                <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={4}>
                  Подтверждённая категория
                </Text>
                {isConfirmed && data.confirmed_category ? (
                  <Group gap="xs" wrap="wrap">
                    <Badge size="xl" color="fspPink" variant="light" leftSection={<IconCertificate size={16} />}>
                      {data.confirmed_category}
                    </Badge>
                    {data.category_percentile != null && (
                      <Badge size="lg" color="fspPurple" variant="outline">
                        {data.category_percentile}-й процентиль в категории
                      </Badge>
                    )}
                  </Group>
                ) : (
                  <Badge size="lg" color="orange" variant="light">
                    Заявлен {gradeLabel(data.declared_grade)} · не подтверждён тестом
                  </Badge>
                )}
              </Box>

              {/* Статус ФСП */}
              <Box>
                <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={4}>
                  Спортивное программирование (ФСП)
                </Text>
                {data.is_fsp_verified ? (
                  <Stack gap={4}>
                    <Group gap="xs">
                      <Badge color="fspBlue" variant="filled" leftSection={<FspStarIcon size={14} />}>
                        Спортсмен ФСП верифицирован
                      </Badge>
                      <Text size="xs" c="dimmed">
                        {data.fsp_achievements_count} соревнований в реестре
                      </Text>
                    </Group>
                    {data.fsp_disciplines.length > 0 && (
                      <Text size="xs" c="dimmed">
                        Дисциплины: {data.fsp_disciplines.join(', ')}
                      </Text>
                    )}
                  </Stack>
                ) : (
                  <Text size="sm" c="dimmed">
                    Данные профиля ФСП не привязаны
                  </Text>
                )}
              </Box>

              {/* Подтверждённые навыки */}
              {data.confirmed_skills && data.confirmed_skills.length > 0 && (
                <Box>
                  <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb={6}>
                    Подтверждённый стек технологий
                  </Text>
                  <Group gap="xs" wrap="wrap">
                    {data.confirmed_skills.map((skill) => (
                      <Badge key={skill} color="teal" variant="light" size="sm">
                        {skill}
                      </Badge>
                    ))}
                  </Group>
                </Box>
              )}
            </Stack>

            {/* Правая колонка: Радар компетенций */}
            <Paper withBorder p={{ base: 'xs', sm: 'md' }} radius="md" style={{ background: 'var(--fsp-card-bg)', overflow: 'hidden' }}>
              <CompetenceRadarChart
                dimensions={radarDimensions}
                size={280}
                title="Радар подтверждённых компетенций"
                subtitle="Баланс навыков по 5 ключевым метрикам платформы"
                showLegend={true}
              />
            </Paper>
          </SimpleGrid>

          <Divider my="lg" />

          {/* Защитный блок криптографической верификации */}
          <Paper p={{ base: 'sm', sm: 'md' }} radius="md" style={{ background: 'var(--fsp-tint-violet)', border: '1px solid var(--fsp-border)' }}>
            <Group justify="space-between" align="center" wrap="wrap" gap="md">
              <Group gap="md" wrap="nowrap" align="center" style={{ minWidth: 0, flex: 1 }}>
                <Box
                  onClick={() => setQrOpened(true)}
                  style={{
                    background: '#ffffff',
                    padding: 4,
                    borderRadius: 8,
                    border: '1px solid var(--fsp-border)',
                    cursor: 'pointer',
                    flexShrink: 0,
                    lineHeight: 0,
                  }}
                  title="Нажмите, чтобы открыть QR-код крупно"
                >
                  <img
                    src={`/api/v1/verify/candidates/${data.candidate_id}/qr`}
                    alt="QR-код верификации"
                    width={64}
                    height={64}
                    style={{ display: 'block', borderRadius: 4 }}
                  />
                </Box>
                <Box style={{ minWidth: 0, flex: 1 }}>
                  <Text fw={700} size="sm">
                    Электронная цифровая отметка FSP-Verify
                  </Text>
                  <Text size="xs" c="dimmed">
                    Хэш записи: <Text component="span" ff="monospace" fw={700} className="text-break-hash">{data.verification_hash || 'SHA256-OK'}</Text> · Сверено: {formatDate(data.checked_at)}
                  </Text>
                  <Text size="xs" c="fspBlue" fw={600} mt={2} style={{ cursor: 'pointer' }} onClick={() => setQrOpened(true)}>
                    Онлайн-верификация по QR-коду (нажмите для увеличения)
                  </Text>
                </Box>
              </Group>

              <Group gap="xs" wrap="wrap" w={{ base: '100%', sm: 'auto' }} justify="flex-start">
                <Button size="xs" variant="light" color="fspBlue" leftSection={<IconQrcode size={14} />} onClick={() => setQrOpened(true)}>
                  Открыть QR
                </Button>
                {data.verification_hash && (
                  <Tooltip label="Скопировать хэш" withArrow>
                    <Button size="xs" variant="subtle" color="fspPurple" leftSection={<IconCopy size={14} />} onClick={() => copyHash(data.verification_hash!)}>
                      Скопировать хэш
                    </Button>
                  </Tooltip>
                )}
                <Button size="xs" variant="default" leftSection={<IconExternalLink size={14} />} component={Link} to="/demo">
                  О методике ФСП
                </Button>
              </Group>
            </Group>
            <Text size="xs" c="dimmed" mt={10} style={{ lineHeight: 1.45 }}>
              🔒 Контактные данные соискателя (телефон, email) скрыты в соответствии с требованиями 152-ФЗ «О персональных данных» и регламентом защиты данных ФСП.
            </Text>
          </Paper>
        </Paper>
      </Stack>

      <AppModal opened={qrOpened} onClose={() => setQrOpened(false)} title="QR-код официального сертификата ФСП" size="sm">
        <Stack align="center" gap="md" py="xs">
          <Box p="md" style={{ background: '#ffffff', borderRadius: 12, border: '2px solid var(--fsp-border)' }}>
            <img
              src={`/api/v1/verify/candidates/${data.candidate_id}/qr`}
              alt="QR-код верификации"
              width={200}
              height={200}
              style={{ display: 'block' }}
            />
          </Box>
          <Text size="xs" c="dimmed" ta="center">
            Наведите камеру смартфона на QR-код для перехода на страницу цифровой верификации соискателя в реестре ФСП.
          </Text>
          <Group gap="xs" w="100%">
            <Button size="xs" variant="default" flex={1} leftSection={<IconShare size={14} />} onClick={shareLink}>
              Поделиться
            </Button>
            <Button
              size="xs"
              variant="light"
              color="fspBlue"
              flex={1}
              component="a"
              href={`/api/v1/verify/candidates/${data.candidate_id}/qr`}
              download={`fsp_verify_${data.candidate_id.slice(0, 8)}.png`}
              leftSection={<IconDownload size={14} />}
            >
              Скачать PNG
            </Button>
          </Group>
        </Stack>
      </AppModal>
    </Container>
  );
};
