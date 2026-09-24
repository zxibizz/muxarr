import { Button, Code, Group, Modal, PasswordInput, Stack, Text, Title } from '@mantine/core';
import { IconKey } from '@tabler/icons-react';
import { useState } from 'react';
import { LogoMark } from '../components/LogoMark';

interface Props {
  opened: boolean;
  onSubmit: (token: string) => void;
}

export function TokenPrompt({ opened, onSubmit }: Props) {
  const [value, setValue] = useState('');

  return (
    <Modal
      opened={opened}
      onClose={() => undefined}
      withCloseButton={false}
      closeOnClickOutside={false}
      closeOnEscape={false}
      padding="xl"
      title={
        <Group gap="sm">
          <LogoMark size={28} />
          <Title order={2}>API token required</Title>
        </Group>
      }
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(value.trim());
        }}
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            This Muxarr instance is protected. Enter the value of <Code>MUXARR_TOKEN</Code>; it is
            kept in this browser only.
          </Text>
          <PasswordInput
            label="Token"
            leftSection={<IconKey size={16} />}
            value={value}
            onChange={(event) => setValue(event.currentTarget.value)}
            data-autofocus
          />
          <Button type="submit" disabled={value.trim().length === 0} fullWidth>
            Connect
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
