import React from 'react';
import { Table } from '@mantine/core';

interface ScrollTableProps {
  minWidth: number;
  label: string;
  children: React.ReactNode;
}

/** Таблица с горизонтальной прокруткой внутри карточки. Область доступна с клавиатуры (Tab, стрелки). */
export const ScrollTable: React.FC<ScrollTableProps> = ({ minWidth, label, children }) => (
  <Table.ScrollContainer minWidth={minWidth} scrollAreaProps={{ viewportProps: { tabIndex: 0, role: 'region', 'aria-label': label } }}>
    {children}
  </Table.ScrollContainer>
);
