import React from 'react';
import { Box, Group, Text, Title } from '@mantine/core';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

/** Единый заголовок страницы кабинета: рубрика, название, пояснение и действия справа. */
export const PageHeader: React.FC<PageHeaderProps> = ({ eyebrow, title, description, actions }) => (
  <Group justify="space-between" align="flex-start" gap="md" className="page-head">
    <Box style={{ flex: 1, minWidth: 260 }}>
      {eyebrow && <span className="section-eyebrow">{eyebrow}</span>}
      <Title order={1} size="h2" mt={eyebrow ? 2 : 0}>
        {title}
      </Title>
      {description && (
        <Text size="sm" c="dimmed" mt={6} maw={760}>
          {description}
        </Text>
      )}
    </Box>
    {actions}
  </Group>
);
