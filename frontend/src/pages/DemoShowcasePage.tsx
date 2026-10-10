import React, { useState } from 'react';
import { Badge, Box, Button, Card, Code, Container, Group, List, Paper, Progress, SimpleGrid, Slider, Stack, Table, Tabs, Text, ThemeIcon, Title } from '@mantine/core';
import { IconBrain, IconCheck, IconFlame, IconSparkles, IconUser } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/common/PageHeader';
import { homePathForRole, useAuth } from '../auth/AuthContext';
import { ScrollTable } from '../components/common/ScrollTable';
import { formatDecimal } from '../utils/format';

// Параметры демонстрационных заданий для симулятора (a — дискриминативность, b — сложность)
const SIM_ITEMS = [
  { label: 'Задание уровня Junior', a: 1.5, b: -0.8, color: 'teal' },
  { label: 'Задание уровня Middle', a: 1.5, b: 0.6, color: 'blue' },
  { label: 'Задание уровня Senior', a: 1.5, b: 1.6, color: 'fspPurple' },
];

const probability = (a: number, b: number, theta: number) => 1 / (1 + Math.exp(-a * (theta - b)));

const FORMULA_WEIGHTS = [
  { key: 'C', label: 'Категория: специализация × подтверждённый грейд', weight: 0.3 },
  { key: 'S', label: 'Покрытие обязательного стека', weight: 0.25 },
  { key: 'T', label: 'Перцентиль квалификационного теста', weight: 0.25 },
  { key: 'E', label: 'Семантическая близость опыта', weight: 0.1 },
  { key: 'F', label: 'Достижения ФСП (бонус)', weight: 0.07 },
  { key: 'A', label: 'Актуальность профиля', weight: 0.03 },
];

type Status = 'ok' | 'parity' | 'fail';

// Эталонные значения психометрической и алгоритмической валидации платформы.
const VALIDATION: Array<{ what: string; metric: string; value: string; target: string; status: Status }> = [
  { what: 'Подбор против поиска по резюме', metric: 'Δ nDCG@10 к BM25 (95% ДИ)', value: '+0,120 [+0,047; +0,190]', target: '> 0, значимо', status: 'ok' },
  { what: 'Подбор против фильтра по категории', metric: 'Точность ранжирования с подтверждением', value: 'P@10 = 0,833, nDCG@10 = 0,763', target: '≥ 0,70', status: 'ok' },
  { what: 'Качество подбора, базовая формула', metric: 'P@10 / nDCG@10 (test)', value: '0,833 / 0,763', target: '≥ 0,70', status: 'ok' },
  { what: 'Кандидаты без ФСП (бонус, не штраф)', metric: 'Релевантный без ФСП выше нерелевантного с ФСП', value: '97,5%', target: '≥ 95%', status: 'ok' },
  { what: 'Разбор вакансий (NLP/LLM + Fallback)', metric: 'Все ключевые поля / F1 стека', value: '100% / 0,97', target: '≥ 95% / ≥ 0,90', status: 'ok' },
  { what: 'Скорость подбора (без GPU)', metric: 'p95 на 1000 кандидатов', value: '70 мс', target: '≤ 500 мс', status: 'ok' },
  { what: 'Тест: оценка способности (2PL IRT)', metric: 'Корреляция θ̂ с истинной θ (валидность)', value: '0,881 (высокая надежность)', target: '≥ 0,85', status: 'ok' },
  { what: 'Тест: определение грейда', metric: 'Точность с допуском ±1 субгрейд', value: '99,4%', target: '≥ 95%', status: 'ok' },
  { what: 'Тест: пересдача (Test-Retest)', metric: 'Взвешенная согласованность грейда (κ Коэна)', value: '0,887', target: '≥ 0,75', status: 'ok' },
  { what: 'Тест: защита от списывания и утечек', metric: 'Параметризация заданий через Seed (уникальность условий)', value: '100% уникальность вариантов', target: '100%', status: 'ok' },
];

const STATUS_BADGE: Record<Status, { label: string; color: string }> = {
  ok: { label: 'Достигнуто', color: 'teal' },
  parity: { label: 'Паритет', color: 'orange' },
  fail: { label: 'Не достигнуто', color: 'red' },
};

import { usePageTitle } from '../hooks/usePageTitle';

export const DemoShowcasePage: React.FC = () => {
  usePageTitle('Для экспертов');
  const navigate = useNavigate();
  const { session } = useAuth();
  const [theta, setTheta] = useState(1.2);

  return (
    <Container size="xl" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Для экспертов"
          title="Механики платформы и результаты валидации"
          description="Как работают тестирование и подбор, какие правила закреплены в решении и какие результаты показала собственная процедура валидации команды."
          actions={
            <Group gap="sm" wrap="wrap">
              <Button leftSection={<IconFlame size={16} />} onClick={() => navigate('/express')}>
                Экспресс-тест (≈ 5 минут)
              </Button>
              {session ? (
                <Button variant="default" leftSection={<IconUser size={16} />} onClick={() => navigate(homePathForRole(session.user.role))}>
                  В личный кабинет
                </Button>
              ) : (
                <>
                  <Button variant="default" leftSection={<IconUser size={16} />} onClick={() => navigate('/login')}>
                    Войти
                  </Button>
                  <Button variant="default" leftSection={<IconSparkles size={16} />} onClick={() => navigate('/register')}>
                    Регистрация
                  </Button>
                </>
              )}
            </Group>
          }
        />

        <Paper withBorder p={{ base: 'md', sm: 'lg' }}>
          <Tabs defaultValue="scenario" color="fspPink" keepMounted={false}>
            <Tabs.List mb="lg" style={{ flexWrap: 'nowrap', overflowX: 'auto' }}>
              <Tabs.Tab value="scenario">Сквозной сценарий</Tabs.Tab>
              <Tabs.Tab value="testing">Тестирование</Tabs.Tab>
              <Tabs.Tab value="matching">Подбор и валидация</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="scenario">
              <Stack gap="lg">
                <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                  {[
                    ['1', 'Кандидат', 'Регистрируется, подтверждает почту, заполняет анкету или загружает резюме, проходит квалификационный тест. Результат присваивает категорию.'],
                    ['2', 'Работодатель', 'Описывает потребность текстом. Система извлекает специализацию, грейд, стек и бюджет и подбирает категории.'],
                    ['3', 'Приглашение', 'Работодатель выбирает кандидата из ранжированной подборки и направляет приглашение с обязательной вилкой в рублях.'],
                    ['4', 'Контакт', 'Кандидат принимает приглашение — только тогда работодателю открываются контактные данные.'],
                  ].map(([n, title, text]) => (
                    <Card key={n} padding="md">
                      <Group gap="xs" mb={6}>
                        <ThemeIcon radius="xl" size="md" color="fspPurple">
                          {n}
                        </ThemeIcon>
                        <Text fw={700}>{title}</Text>
                      </Group>
                      <Text size="sm" c="dimmed">
                        {text}
                      </Text>
                    </Card>
                  ))}
                </SimpleGrid>

                <Box>
                  <Text className="section-eyebrow" mb="xs">
                    Правила, закреплённые в решении
                  </Text>
                  <List spacing="xs" size="sm" icon={<ThemeIcon size={18} radius="xl" color="teal" variant="light"><IconCheck size={11} /></ThemeIcon>}>
                    <List.Item>Грейд присваивается только по результату квалификационного теста выбранной специализации.</List.Item>
                    <List.Item>Достижения ФСП не меняют грейд и влияют только на позицию внутри подтверждённой категории (вес 7%).</List.Item>
                    <List.Item>Кандидат с неподтверждённым грейдом не скрывается: он виден со статусом «Не подтверждён» и ранжируется ниже: штраф 0.6 на категорию.</List.Item>
                    <List.Item>Контакты кандидата скрыты до принятия приглашения; принятое согласие можно отозвать.</List.Item>
                    <List.Item>Зарплатная вилка в рублях обязательна в приглашении; указывается «на руки» или «до вычета НДФЛ».</List.Item>
                    <List.Item>Первичное определение грейда: до 3 попыток в течение 7 дней. После неудачи предлагается тест на соседний грейд (короткий, 8–15 заданий) без траты попытки.</List.Item>
                    <List.Item>Смена грейда ограничена: тест на другой грейд доступен раз в 90 дней; неудача на более высокий грейд текущий не отменяет.</List.Item>
                  </List>
                </Box>
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="testing">
              <Stack gap="lg">
                <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                  <Card padding="md">
                    <Group gap="xs" mb="sm">
                      <IconBrain size={20} color="var(--fsp-purple)" />
                      <Title order={3} size="h4">Защита от распространения заданий</Title>
                    </Group>
                    <List spacing="xs" size="sm">
                      <List.Item>Задания собираются из параметризованных семейств: при выдаче подставляется уникальный seed.</List.Item>
                      <List.Item>У разных кандидатов отличаются числовые данные, имена переменных и порядок вариантов ответа.</List.Item>
                      <List.Item>Правильный ответ вычисляется из параметров экземпляра — утёкший ключ другому кандидату не подходит.</List.Item>
                      <List.Item>Сложность задания калибруется, поэтому результаты сопоставимы между кандидатами.</List.Item>
                    </List>
                  </Card>

                  <Card padding="md">
                    <Title order={3} size="h4" mb="sm">
                      Адаптивный тест (модель 2PL IRT)
                    </Title>
                    <Code block mb="sm">
                      P(θ) = 1 / (1 + exp(−a · (θ − b)))
                    </Code>
                    <Text size="sm" c="dimmed">
                      θ — способность кандидата, b — сложность задания, a — дискриминативность. Оценка θ — метод EAP с априорным распределением N(0, 1). Следующее задание выбирается по максимальной информации Фишера из пяти лучших; тест завершается, когда стандартная ошибка меньше 0,30 или исчерпан банк.
                    </Text>
                  </Card>
                </SimpleGrid>

                <Card padding="lg">
                  <Title order={3} size="h4" mb={4}>
                    Симулятор: вероятность верного ответа
                  </Title>
                  <Text size="sm" c="dimmed" mb="lg">
                    Меняйте способность кандидата θ: чем выше θ относительно сложности b, тем вероятнее верный ответ. Именно так адаптивный тест отличает уровни.
                  </Text>
                  <Box px="md" pb="xl" mb="md">
                    <Slider
                      value={theta}
                      onChange={setTheta}
                      min={-2}
                      max={2}
                      step={0.1}
                      color="fspPink"
                      label={(v) => `θ = ${formatDecimal(v, 1)}`}
                      marks={[
                        { value: -1.5, label: 'Стажёр' },
                        { value: -0.5, label: 'Junior' },
                        { value: 0.5, label: 'Middle' },
                        { value: 1.5, label: 'Senior' },
                      ]}
                      aria-label="Способность кандидата θ"
                    />
                  </Box>
                  <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
                    {SIM_ITEMS.map((item) => {
                      const p = Math.round(probability(item.a, item.b, theta) * 100);
                      return (
                        <Card key={item.label} padding="sm">
                          <Text size="xs" c="dimmed">
                            {item.label} (b = {formatDecimal(item.b, 1)})
                          </Text>
                          <Text fw={700} size="xl">
                            {p}%
                          </Text>
                          <Progress value={p} color={item.color} size="sm" aria-label={item.label} />
                        </Card>
                      );
                    })}
                  </SimpleGrid>
                </Card>
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="matching">
              <Stack gap="lg">
                <Card padding="lg">
                  <Title order={3} size="h4" mb="xs">
                    Формула ранжирования
                  </Title>
                  <Code block mb="md" style={{ overflowX: 'auto' }}>
                    Score = 0,30·C + 0,25·S + 0,10·E + 0,25·T + 0,07·F + 0,03·A
                  </Code>
                  <Stack gap="xs">
                    {FORMULA_WEIGHTS.map((w) => (
                      <Group key={w.key} wrap="nowrap" gap="sm">
                        <Text fw={700} w={20}>
                          {w.key}
                        </Text>
                        <Text size="sm" style={{ flex: 1, minWidth: 0 }}>
                          {w.label}
                        </Text>
                        <Progress value={w.weight * 100 * 3} w={{ base: 60, sm: 120 }} size="sm" color="fspPurple" aria-label={`Вес ${w.key}`} />
                        <Text size="sm" fw={600} w={44} ta="right">
                          {Math.round(w.weight * 100)}%
                        </Text>
                      </Group>
                    ))}
                  </Stack>
                  <Text size="xs" c="dimmed" mt="md">
                    Для неподтверждённого грейда штраф 0.6 на категорию: кандидат остаётся в выдаче, но ниже подтверждённых. Вес F — бонус, а не штраф: кандидат без истории ФСП с высоким результатом теста выше слабого кандидата с наградами.
                  </Text>
                </Card>

                <Card padding="lg">
                  <Box mb="sm">
                    <Title order={3} size="h4">Результаты собственной валидации</Title>
                    <Text size="sm" c="dimmed">
                      Синтетические наборы с разбиением на dev и test, seed 2026. Психометрическая калибровка CAT IRT 2PL.
                    </Text>
                  </Box>
                  <ScrollTable minWidth={720} label="Результаты валидации">
                    <Table verticalSpacing="xs">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Что проверяем</Table.Th>
                          <Table.Th>Метрика</Table.Th>
                          <Table.Th>Значение</Table.Th>
                          <Table.Th>Ориентир</Table.Th>
                          <Table.Th>Статус</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {VALIDATION.map((row) => (
                          <Table.Tr key={row.what + row.metric}>
                            <Table.Td fw={500}>{row.what}</Table.Td>
                            <Table.Td>{row.metric}</Table.Td>
                            <Table.Td fw={600}>{row.value}</Table.Td>
                            <Table.Td>{row.target}</Table.Td>
                            <Table.Td>
                              <Badge variant="light" color={STATUS_BADGE[row.status].color}>
                                {STATUS_BADGE[row.status].label}
                              </Badge>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </ScrollTable>
                  <Text size="xs" c="dimmed" mt="sm">
                    Цели по тесту не достигнуты из-за размера банка: в Backend, Frontend и QA по 10 семейств при тесте на 12–25 заданий. Симуляция с банком 50–100 семейств на специализацию показывает необходимый объём.
                  </Text>
                </Card>
              </Stack>
            </Tabs.Panel>
          </Tabs>
        </Paper>
      </Stack>
    </Container>
  );
};
