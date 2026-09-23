import { Box, Burger, Group, Menu, Tabs, Text, VisuallyHidden } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { SECTIONS } from './fields';
import type { SectionId } from './fields';

interface NavProps {
  current: SectionId;
  onChange: (id: SectionId) => void;
  dirty: (id: SectionId) => boolean;
}

function UnsavedDot() {
  return (
    <>
      <Box
        component="span"
        w={7}
        h={7}
        bg="var(--mantine-primary-color-filled)"
        style={{ borderRadius: '50%', display: 'inline-block' }}
        aria-hidden
      />
      <VisuallyHidden>unsaved changes</VisuallyHidden>
    </>
  );
}

/** Must be rendered inside the page's `Tabs`. */
export function SectionTabs({ dirty }: Pick<NavProps, 'dirty'>) {
  return (
    <Tabs.List visibleFrom="md">
      {SECTIONS.map((section) => (
        <Tabs.Tab
          key={section.id}
          value={section.id}
          rightSection={dirty(section.id) ? <UnsavedDot /> : undefined}
        >
          {section.title}
        </Tabs.Tab>
      ))}
    </Tabs.List>
  );
}

export function SectionMenu({ current, onChange, dirty }: NavProps) {
  const [opened, { open, close }] = useDisclosure(false);
  const title = SECTIONS.find((section) => section.id === current)?.title;

  return (
    <Menu opened={opened} onOpen={open} onClose={close} position="bottom-start" width={260}>
      <Group gap="sm" hiddenFrom="md" wrap="nowrap">
        <Menu.Target>
          <Burger opened={opened} size="sm" aria-label="Settings sections" />
        </Menu.Target>
        <Text fw={600}>{title}</Text>
      </Group>
      <Menu.Dropdown>
        {SECTIONS.map((section) => (
          <Menu.Item
            key={section.id}
            onClick={() => onChange(section.id)}
            fw={section.id === current ? 600 : undefined}
            aria-current={section.id === current ? 'page' : undefined}
            rightSection={dirty(section.id) ? <UnsavedDot /> : undefined}
          >
            {section.title}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
