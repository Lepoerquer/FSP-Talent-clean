import React from 'react';
import { Alert, Button, Group, Text } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { toApiError } from '../../api/http';

interface QueryErrorProps {
  error: unknown;
  onRetry: () => void;
  title?: string;
}

/** Состояние «не удалось загрузить» с возможностью повторить запрос: вместо бесконечной заглушки загрузки. */
export const QueryError: React.FC<QueryErrorProps> = ({ error, onRetry, title = 'Не удалось загрузить данные' }) => (
  <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} title={title} role="alert">
    <Group justify="space-between" align="center" gap="sm">
      <Text size="sm">{toApiError(error).message}</Text>
      <Button size="xs" variant="default" onClick={onRetry}>
        Повторить
      </Button>
    </Group>
  </Alert>
);
