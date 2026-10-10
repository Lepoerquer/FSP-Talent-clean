import { useState, useEffect, useRef } from 'react';
import { Modal, Stack, TextInput, Button, Paper, Text, Group, ScrollArea, Loader } from '@mantine/core';
import { IconSend } from '@tabler/icons-react';
import { api } from '../api/api';
import { useAuth } from '../auth/AuthContext';

interface PlatformChatModalProps {
  opened: boolean;
  onClose: () => void;
  receiverId: string;
  receiverName: string;
}

export function PlatformChatModal({ opened, onClose, receiverId, receiverName }: PlatformChatModalProps) {
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const { session } = useAuth();
  const user = session?.user;
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadMessages = async () => {
    try {
      const data = await api.getMessages(receiverId);
      setMessages(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (opened) {
      setLoading(true);
      loadMessages();
      const interval = setInterval(loadMessages, 5000);
      return () => clearInterval(interval);
    }
  }, [opened, receiverId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  const handleSend = async () => {
    if (!text.trim()) return;
    setSending(true);
    try {
      await api.sendMessage({ message: text, receiver_id: receiverId });
      setText('');
      await loadMessages();
    } catch (e) {
      console.error(e);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`Чат на платформе: ${receiverName}`} size="lg">
      <Stack h={400}>
        <ScrollArea
          flex={1}
          viewportRef={scrollRef}
          p="sm"
          style={{
            background: 'var(--fsp-tint-neutral)',
            borderRadius: 8,
            border: '1px solid var(--fsp-border)',
          }}
        >
          {loading && messages.length === 0 ? (
            <Group justify="center" h="100%"><Loader size="sm" /></Group>
          ) : messages.length === 0 ? (
            <Text c="dimmed" size="sm" ta="center" mt="xl">Нет сообщений. Напишите первым!</Text>
          ) : (
            <Stack gap="xs">
              {messages.map((m: any) => {
                const isMe = m.sender_id === user?.id;
                return (
                  <Group key={m.id} justify={isMe ? 'flex-end' : 'flex-start'} align="flex-end" gap="xs">
                    <Paper
                      p="xs"
                      px="md"
                      radius="xl"
                      style={{
                        background: isMe ? 'var(--fsp-primary)' : 'var(--fsp-surface)',
                        color: isMe ? '#ffffff' : 'var(--fsp-ink)',
                        maxWidth: '80%',
                        border: isMe ? 'none' : '1px solid var(--fsp-border)',
                      }}
                    >
                      <Text size="sm">{m.message}</Text>
                      <Text size="10px" c={isMe ? 'rgba(255,255,255,0.7)' : 'dimmed'} ta={isMe ? 'right' : 'left'} mt={4}>
                        {new Date(m.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                      </Text>
                    </Paper>
                  </Group>
                );
              })}
            </Stack>
          )}
        </ScrollArea>
        <Group>
          <TextInput
            flex={1}
            placeholder="Введите сообщение..."
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            disabled={sending}
          />
          <Button onClick={handleSend} loading={sending} color="var(--fsp-primary)">
            <IconSend size={18} />
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
