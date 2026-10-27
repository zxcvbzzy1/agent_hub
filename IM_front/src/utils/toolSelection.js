// CheckboxGroup emits only its registered options. Merge that group's changes
// into the full selection so collapsed and unrelated groups keep their values.
export function mergeToolGroupSelection(selected, groupNames, selectedInGroup) {
  const group = new Set(groupNames)
  return [...new Set([
    ...selected.filter(name => !group.has(name)),
    ...selectedInGroup.filter(name => group.has(name)),
  ])]
}
