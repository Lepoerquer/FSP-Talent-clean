import React from 'react';
import { Modal, Text } from '@mantine/core';

interface AppModalProps {
  opened: boolean;
  onClose: () => void;
  title: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnClickOutside?: boolean;
  children: React.ReactNode;
}

/**
 * Модальное окно платформы. Отличия от стандартного Modal:
 *  - у кнопки закрытия есть подпись для программ экранного доступа;
 *  - заголовок окна — обычный блок, а не `header`: на странице остаётся один ориентир banner (шапка сайта).
 */
export const AppModal: React.FC<AppModalProps> = ({ opened, onClose, title, size = 'md', closeOnClickOutside = true, children }) => (
  <Modal.Root opened={opened} onClose={onClose} size={size} centered closeOnClickOutside={closeOnClickOutside} radius="md">
    <Modal.Overlay backgroundOpacity={0.45} blur={2} />
    <Modal.Content>
      <Modal.Header {...({ component: 'div' } as object)}>
        <Modal.Title>
          <Text component="span" fw={700}>
            {title}
          </Text>
        </Modal.Title>
        <Modal.CloseButton aria-label="Закрыть окно" />
      </Modal.Header>
      <Modal.Body>{children}</Modal.Body>
    </Modal.Content>
  </Modal.Root>
);
