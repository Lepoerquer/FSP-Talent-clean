import React, { useState } from 'react';
import { Box, Group, Paper, Stack, Text, ThemeIcon, Tooltip } from '@mantine/core';
import { IconAward, IconBrain, IconCode, IconUsers, IconBriefcase } from '@tabler/icons-react';

export interface RadarDimension {
  key: string;
  label: string;
  value: number; // 0..100
  targetValue?: number; // 0..100 (например, требование вакансии)
  icon?: React.ReactNode;
  hint?: string;
}

export interface CompetenceRadarChartProps {
  dimensions: RadarDimension[];
  size?: number;
  title?: string;
  subtitle?: string;
  candidateLabel?: string;
  targetLabel?: string;
  showLegend?: boolean;
}

/**
 * Интерактивный «Радар компетенций» (Spider / Radar Chart) на чистом SVG.
 * Не требует внешних тяжелых библиотек, рендерится мгновенно и адаптивно.
 * Отображает многомерный профиль соискателя (тест, ФСП, стек, опыт, soft skills).
 */
export const CompetenceRadarChart: React.FC<CompetenceRadarChartProps> = ({
  dimensions,
  size = 320,
  title,
  subtitle,
  candidateLabel = 'Профиль кандидата',
  targetLabel,
  showLegend = true,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const n = dimensions.length;
  if (n < 3) return null;

  // Фиксированное пропорциональное пространство координат SVG (внутренний холст)
  // Вся паутина и все подписи гарантированно умещаются с запасом >30px со всех 4 сторон
  const vbWidth = 380;
  const vbHeight = 260;
  const centerX = vbWidth / 2; // 190
  const centerY = 130;
  const radius = 64;
  const levels = [0.25, 0.5, 0.75, 1.0];

  // Угол в радианах для i-й вершины (начиная сверху, шаг по часовой стрелке)
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n;

  // Вычисление координат точки на окружности
  const getCoords = (val: number, i: number) => {
    const clamped = Math.max(0, Math.min(100, val));
    const r = (clamped / 100) * radius;
    const a = angle(i);
    return {
      x: centerX + r * Math.cos(a),
      y: centerY + r * Math.sin(a),
    };
  };

  // Координаты сетки для уровня L
  const getGridPoints = (level: number) => {
    return Array.from({ length: n })
      .map((_, i) => {
        const a = angle(i);
        const r = level * radius;
        return `${(centerX + r * Math.cos(a)).toFixed(1)},${(centerY + r * Math.sin(a)).toFixed(1)}`;
      })
      .join(' ');
  };

  // Точки полигона кандидата
  const candidatePolygon = dimensions
    .map((d, i) => {
      const pt = getCoords(d.value, i);
      return `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`;
    })
    .join(' ');

  // Точки полигона требований (если есть)
  const hasTarget = dimensions.some((d) => d.targetValue !== undefined);
  const targetPolygon = hasTarget
    ? dimensions
        .map((d, i) => {
          const pt = getCoords(d.targetValue ?? 0, i);
          return `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`;
        })
        .join(' ')
    : null;

  return (
    <Box>
      {(title || subtitle) && (
        <Box mb="xs">
          {title && (
            <Text fw={700} size="sm">
              {title}
            </Text>
          )}
          {subtitle && (
            <Text size="xs" c="dimmed">
              {subtitle}
            </Text>
          )}
        </Box>
      )}

      <Box style={{ position: 'relative', width: '100%', maxWidth: size, margin: '0 auto' }}>
        <svg
          viewBox={`0 0 ${vbWidth} ${vbHeight}`}
          width="100%"
          height="auto"
          preserveAspectRatio="xMidYMid meet"
          style={{ overflow: 'hidden', display: 'block' }}
        >
          <defs>
            {/* Фирменный градиент ФСП: Electric Blue (#402FFF) -> Digital Navy (#0A006B) */}
            <linearGradient id="fspRadarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#402FFF" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#0A006B" stopOpacity="0.25" />
            </linearGradient>
            <linearGradient id="fspTargetGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#EC1D35" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#EC1D35" stopOpacity="0.08" />
            </linearGradient>
            <filter id="radarGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#402FFF" floodOpacity="0.3" />
            </filter>
          </defs>

          {/* 1. Концентрические полигоны сетки (паутина) */}
          {levels.map((lvl) => (
            <polygon
              key={lvl}
              points={getGridPoints(lvl)}
              fill="none"
              stroke="var(--fsp-border, #E5E7EB)"
              strokeWidth={lvl === 1.0 ? '1.5' : '1'}
              strokeDasharray={lvl === 1.0 ? undefined : '3 3'}
              opacity={0.8}
            />
          ))}

          {/* 2. Радиальные оси */}
          {Array.from({ length: n }).map((_, i) => {
            const a = angle(i);
            const x2 = centerX + radius * Math.cos(a);
            const y2 = centerY + radius * Math.sin(a);
            return (
              <line
                key={i}
                x1={centerX}
                y1={centerY}
                x2={x2}
                y2={y2}
                stroke="var(--fsp-border, #E5E7EB)"
                strokeWidth="1"
                opacity={0.7}
              />
            );
          })}

          {/* 3. Полигон требований вакансии (если задан) */}
          {targetPolygon && (
            <polygon
              points={targetPolygon}
              fill="url(#fspTargetGradient)"
              stroke="#EC1D35"
              strokeWidth="1.8"
              strokeDasharray="4 3"
            />
          )}

          {/* 4. Полигон компетенций кандидата */}
          <polygon
            points={candidatePolygon}
            fill="url(#fspRadarGradient)"
            stroke="#402FFF"
            strokeWidth="2.5"
            filter="url(#radarGlow)"
          />

          {/* 5. Интерактивные точки на вершинах полигона кандидата */}
          {dimensions.map((d, i) => {
            const pt = getCoords(d.value, i);
            const isHovered = hoveredIdx === i;
            return (
              <g
                key={d.key}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  cx={pt.x}
                  cy={pt.y}
                  r={isHovered ? 7 : 4.5}
                  fill="#ffffff"
                  stroke="#402FFF"
                  strokeWidth={isHovered ? 3 : 2}
                  style={{ transition: 'all 0.2s ease' }}
                />
              </g>
            );
          })}

          {/* 6. Подписи вершин */}
          {dimensions.map((d, i) => {
            const a = angle(i);
            const offset = radius + 15;
            const lx = centerX + offset * Math.cos(a);
            const ly = centerY + offset * Math.sin(a);

            // Тонкое выравнивание текста по четвертям с безопасными отступами
            const cos = Math.cos(a);
            const sin = Math.sin(a);
            const anchor = cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle';
            const baseline = sin > 0.35 ? 'hanging' : sin < -0.35 ? 'auto' : 'middle';

            const isHovered = hoveredIdx === i;

            return (
              <text
                key={`lbl-${d.key}`}
                x={lx}
                y={ly}
                textAnchor={anchor}
                dominantBaseline={baseline}
                fontSize="10.5"
                fontWeight={isHovered ? '700' : '600'}
                fill={isHovered ? 'var(--fsp-primary)' : 'var(--fsp-radar-text, var(--fsp-ink))'}
                style={{
                  transition: 'fill 0.2s ease, font-weight 0.2s ease',
                  letterSpacing: '0.01em',
                  userSelect: 'none',
                }}
              >
                {d.label}
              </text>
            );
          })}
        </svg>
      </Box>

      {/* Легенда и детализация осей */}
      {showLegend && (
        <Stack gap={6} mt="xs">
          {hasTarget && (
            <Group justify="center" gap="md" mb={4}>
              <Group gap={6}>
                <Box w={12} h={12} style={{ background: '#402FFF', borderRadius: 2 }} />
                <Text size="xs" fw={600}>
                  {candidateLabel}
                </Text>
              </Group>
              <Group gap={6}>
                <Box w={12} h={12} style={{ border: '2px dashed #EC1D35', borderRadius: 2 }} />
                <Text size="xs" c="dimmed">
                  {targetLabel || 'Требования вакансии'}
                </Text>
              </Group>
            </Group>
          )}

          <Group justify="center" gap={6} wrap="wrap">
            {dimensions.map((d, i) => (
              <Tooltip key={d.key} label={d.hint || `${d.label}: ${Math.round(d.value)}% из 100%`} withArrow>
                <Paper
                  withBorder
                  px={8}
                  py={3}
                  radius="sm"
                  onMouseEnter={() => setHoveredIdx(i)}
                  onMouseLeave={() => setHoveredIdx(null)}
                  style={{
                    cursor: 'default',
                    borderColor: hoveredIdx === i ? 'var(--fsp-primary)' : 'var(--fsp-border)',
                    background: hoveredIdx === i ? 'var(--fsp-tint-accent)' : 'var(--fsp-card-bg)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <Group gap={4} wrap="nowrap">
                    <Text size="xs" c="dimmed">
                      {d.label}:
                    </Text>
                    <Text size="xs" fw={700} c={d.value >= 70 ? 'teal' : d.value >= 40 ? 'blue' : 'gray'}>
                      {Math.round(d.value)}%
                    </Text>
                  </Group>
                </Paper>
              </Tooltip>
            ))}
          </Group>
        </Stack>
      )}
    </Box>
  );
};
