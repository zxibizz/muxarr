import { Button, Modal, PasswordInput, Stack, Text } from '@mantine/core';
import { useState } from 'react';

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
      title="API token required"
      withCloseButton={false}
      centered
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(value.trim());
        }}
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            This muxarr instance is protected. Enter the value of{' '}
            <Text span fw={600}>
              MUXARR_TOKEN
            </Text>
            . It is kept in this browser only.
          </Text>
          <PasswordInput
            label="Token"
            value={value}
            onChange={(event) => setValue(event.currentTarget.value)}
            data-autofocus
          />
          <Button type="submit" disabled={value.trim().length === 0}>
            Connect
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
