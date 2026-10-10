import React from 'react';
import { Box, Paper, Text, Title } from '@mantine/core';

interface AuthCardProps {
  title: string;
  description?: React.ReactNode;
  width?: number;
  children: React.ReactNode;
}

/** Карточка форм входа и регистрации. */
export const AuthCard: React.FC<AuthCardProps> = ({ title, description, width = 460, children }) => (
  <Box maw={width} mx="auto" mt={{ base: 'md', sm: 'xl' }}>
    <Paper withBorder p={{ base: 'md', sm: 'xl' }}>
      <Box className="page-head" mb="lg">
        <Title order={1} size="h2">{title}</Title>
        {description && (
          <Text size="sm" c="dimmed" mt={4}>
            {description}
          </Text>
        )}
      </Box>
      {children}
    </Paper>
  </Box>
);
