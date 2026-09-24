import { Card, Center, Group, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';
import { LogoMark } from '../../components/LogoMark';

interface Props {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}

export function AuthScreen({ title, description, children }: Props) {
  return (
    <Center mih="100vh" p="md">
      <Card w="100%" maw={420} padding="xl">
        <Stack gap="lg">
          <Group gap="sm">
            <LogoMark size={32} />
            <Title order={1}>{title}</Title>
          </Group>
          {description && (
            <Text size="sm" c="dimmed">
              {description}
            </Text>
          )}
          {children}
        </Stack>
      </Card>
    </Center>
  );
}
