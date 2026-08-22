export const simpleAdminUiSections = ['Rules', 'Nodes', 'Users', 'AI Stats'] as const

export function isSimpleAdminUiSection(value: string): boolean {
  return (simpleAdminUiSections as readonly string[]).includes(value)
}

export const simpleAdminUiSectionsAreUnique = new Set(simpleAdminUiSections).size === simpleAdminUiSections.length
