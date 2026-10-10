import React from 'react';
import { Box, Text } from '@mantine/core';
import { formatMoney, grossToNet, netToGross } from '../../utils/format';

interface SalaryRangeProps {
  from: number;
  to?: number;
  type?: string | null;
  size?: 'sm' | 'md' | 'lg';
  prefix?: string;
}

/** Зарплатная вилка в рублях с явной подписью «на руки» / «до вычета НДФЛ» и пересчётом во второй формат. */
export const SalaryRange: React.FC<SalaryRangeProps> = ({ from, to, type, size = 'md', prefix }) => {
  const isGross = type === 'GROSS';
  const amount = to !== undefined ? `${formatMoney(from)} – ${formatMoney(to)}` : formatMoney(from);
  const main = isGross ? 'до вычета НДФЛ' : 'на руки';
  const convert = (v: number) => (isGross ? grossToNet(v) : netToGross(v));
  const alt = to !== undefined ? `${formatMoney(convert(from))} – ${formatMoney(convert(to))}` : formatMoney(convert(from));
  const altLabel = isGross ? 'на руки' : 'до вычета НДФЛ';
  return (
    <Box>
      <Text fw={700} size={size === 'lg' ? 'xl' : size === 'md' ? 'md' : 'sm'}>
        {prefix}
        {amount}{' '}
        <Text span size="xs" fw={500} c="dimmed">
          {main}
        </Text>
      </Text>
      <Text size="xs" c="dimmed">
        ≈ {alt} {altLabel}
      </Text>
    </Box>
  );
};
