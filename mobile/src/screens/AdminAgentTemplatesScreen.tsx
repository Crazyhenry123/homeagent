import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {AgentTemplate} from '../types';
import {
  createAgentTemplate,
  deleteAgentTemplate,
  listAgentTemplates,
  updateAgentTemplate,
} from '../services/api';
import {colors} from '../theme';

export function AdminAgentTemplatesScreen() {
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<AgentTemplate | null>(null);

  // Form fields
  const [name, setName] = useState('');
  const [agentType, setAgentType] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [availableToAll, setAvailableToAll] = useState(true);

  const loadTemplates = useCallback(async () => {
    try {
      const result = await listAgentTemplates();
      setTemplates(result.templates);
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const resetForm = () => {
    setName('');
    setAgentType('');
    setDescription('');
    setSystemPrompt('');
    setAvailableToAll(true);
    setEditing(null);
  };

  const openCreateModal = () => {
    resetForm();
    setModalVisible(true);
  };

  const openEditModal = (template: AgentTemplate) => {
    setEditing(template);
    setName(template.name);
    setAgentType(template.agent_type);
    setDescription(template.description);
    setSystemPrompt(template.system_prompt);
    setAvailableToAll(template.available_to === 'all');
    setModalVisible(true);
  };

  const handleSave = async () => {
    if (!name.trim() || !description.trim()) {
      Alert.alert('Error', 'Name and description are required');
      return;
    }

    try {
      if (editing) {
        await updateAgentTemplate(editing.template_id, {
          name: name.trim(),
          description: description.trim(),
          system_prompt: systemPrompt.trim(),
          available_to: availableToAll ? 'all' : [],
        });
      } else {
        if (!agentType.trim() || !systemPrompt.trim()) {
          Alert.alert('Error', 'Agent type slug and system prompt are required for new agents');
          return;
        }
        await createAgentTemplate({
          name: name.trim(),
          agent_type: agentType.trim().toLowerCase().replace(/\s+/g, '_'),
          description: description.trim(),
          system_prompt: systemPrompt.trim(),
          available_to: availableToAll ? 'all' : [],
        });
      }
      setModalVisible(false);
      resetForm();
      await loadTemplates();
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to save template');
    }
  };

  const handleDelete = (template: AgentTemplate) => {
    if (template.is_builtin) {
      Alert.alert('Error', 'Cannot delete built-in agent templates');
      return;
    }
    Alert.alert(
      'Delete Agent Template',
      `Delete "${template.name}"? This will also remove all member configurations for this agent.`,
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteAgentTemplate(template.template_id);
              await loadTemplates();
            } catch (err) {
              Alert.alert('Error', err instanceof Error ? err.message : 'Failed to delete');
            }
          },
        },
      ],
    );
  };

  const renderTemplate = ({item}: {item: AgentTemplate}) => (
    <TouchableOpacity style={styles.row} onPress={() => openEditModal(item)}>
      <View style={styles.rowHeader}>
        <Text style={styles.rowName}>{item.name}</Text>
        {item.is_builtin && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>Built-in</Text>
          </View>
        )}
      </View>
      <Text style={styles.rowSlug}>{item.agent_type}</Text>
      <Text style={styles.rowDescription} numberOfLines={2}>
        {item.description}
      </Text>
      <Text style={styles.rowAvailability}>
        Available to: {item.available_to === 'all' ? 'Everyone' : `${(item.available_to as string[]).length} members`}
      </Text>
      {!item.is_builtin && (
        <TouchableOpacity
          style={styles.deleteButton}
          onPress={() => handleDelete(item)}>
          <Text style={styles.deleteButtonText}>Delete</Text>
        </TouchableOpacity>
      )}
    </TouchableOpacity>
  );

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={templates}
        keyExtractor={item => item.template_id}
        renderItem={renderTemplate}
        ListEmptyComponent={
          <Text style={styles.emptyText}>No agent templates found</Text>
        }
      />

      <TouchableOpacity style={styles.addButton} onPress={openCreateModal}>
        <Text style={styles.addButtonText}>Add New Agent</Text>
      </TouchableOpacity>

      <Modal visible={modalVisible} animationType="slide" presentationStyle="pageSheet">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {setModalVisible(false); resetForm();}}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {editing ? 'Edit Agent' : 'New Agent'}
            </Text>
            <TouchableOpacity onPress={handleSave}>
              <Text style={styles.modalSave}>Save</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody}>
            <Text style={styles.fieldLabel}>Name</Text>
            <TextInput
              style={styles.input}
              value={name}
              onChangeText={setName}
              placeholder="e.g. Meal Planner"
              editable={!editing?.is_builtin}
            />

            <Text style={styles.fieldLabel}>Agent Type (slug)</Text>
            <TextInput
              style={[styles.input, editing ? styles.inputDisabled : null]}
              value={agentType}
              onChangeText={setAgentType}
              placeholder="e.g. meal_planner"
              autoCapitalize="none"
              editable={!editing}
            />

            <Text style={styles.fieldLabel}>Description</Text>
            <TextInput
              style={[styles.input, styles.multilineInput]}
              value={description}
              onChangeText={setDescription}
              placeholder="What does this agent do?"
              multiline
            />

            <Text style={styles.fieldLabel}>System Prompt</Text>
            <TextInput
              style={[styles.input, styles.promptInput]}
              value={systemPrompt}
              onChangeText={setSystemPrompt}
              placeholder="Instructions for the agent..."
              multiline
              editable={!editing?.is_builtin}
            />
            {editing?.is_builtin && (
              <Text style={styles.readOnlyNote}>
                System prompt is read-only for built-in agents
              </Text>
            )}

            <Text style={styles.fieldLabel}>Availability</Text>
            <TouchableOpacity
              style={styles.toggleRow}
              onPress={() => setAvailableToAll(!availableToAll)}>
              <Text style={styles.toggleLabel}>Available to all members</Text>
              <View style={[styles.toggle, availableToAll && styles.toggleActive]}>
                <View style={[styles.toggleKnob, availableToAll && styles.toggleKnobActive]} />
              </View>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  row: {
    backgroundColor: colors.surface,
    padding: 16,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 10,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  rowName: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.textPrimary,
    flex: 1,
  },
  badge: {
    backgroundColor: colors.badgeBackground,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  badgeText: {
    fontSize: 12,
    color: colors.badgeText,
    fontWeight: '500',
  },
  rowSlug: {
    fontSize: 13,
    color: colors.textTertiary,
    marginBottom: 4,
  },
  rowDescription: {
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  rowAvailability: {
    fontSize: 12,
    color: colors.textTertiary,
  },
  deleteButton: {
    marginTop: 8,
    alignSelf: 'flex-start',
  },
  deleteButtonText: {
    fontSize: 14,
    color: colors.destructive,
  },
  emptyText: {
    textAlign: 'center',
    color: colors.textTertiary,
    fontSize: 16,
    marginTop: 48,
  },
  addButton: {
    margin: 16,
    height: 48,
    borderRadius: 10,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  addButtonText: {
    color: colors.surface,
    fontSize: 17,
    fontWeight: '600',
  },
  modalContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    backgroundColor: colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  modalCancel: {
    fontSize: 17,
    color: colors.primary,
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
  },
  modalSave: {
    fontSize: 17,
    color: colors.primary,
    fontWeight: '600',
  },
  modalBody: {
    padding: 16,
  },
  fieldLabel: {
    fontSize: 13,
    color: colors.textTertiary,
    fontWeight: '500',
    marginTop: 16,
    marginBottom: 6,
    letterSpacing: 0.5,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    padding: 12,
    fontSize: 16,
    color: colors.textPrimary,
  },
  inputDisabled: {
    backgroundColor: colors.separator,
    color: colors.textTertiary,
  },
  multilineInput: {
    minHeight: 60,
    textAlignVertical: 'top',
  },
  promptInput: {
    minHeight: 120,
    textAlignVertical: 'top',
  },
  readOnlyNote: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 4,
    fontStyle: 'italic',
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 10,
    padding: 12,
  },
  toggleLabel: {
    fontSize: 16,
    color: colors.textPrimary,
  },
  toggle: {
    width: 51,
    height: 31,
    borderRadius: 16,
    backgroundColor: colors.separator,
    justifyContent: 'center',
    padding: 2,
  },
  toggleActive: {
    backgroundColor: colors.success,
  },
  toggleKnob: {
    width: 27,
    height: 27,
    borderRadius: 14,
    backgroundColor: colors.surface,
  },
  toggleKnobActive: {
    alignSelf: 'flex-end',
  },
});
