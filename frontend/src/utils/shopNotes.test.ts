import { describe, it, expect } from 'vitest'
import { filterItems, partsForAssembly, defaultAssemblyForPart, itemLabel } from './shopNotes'
import type { ShopItem, ShopAssembly } from '../services/shopNotesApi'

const asm: ShopAssembly[] = [
  { id: 'A', item_number: 'wma20120', name: 'Frame weldment', is_top: false },
  { id: 'T', item_number: 'asm00100', name: 'Top assembly', is_top: true },
]

const parts: ShopItem[] = [
  { id: 'A', item_number: 'wma20120', name: 'Frame weldment', parent_ids: ['T'] },
  { id: 'p1', item_number: 'csp0030', name: 'Side plate', parent_ids: ['A'] },
  { id: 'p2', item_number: 'csp0031', name: 'Gusset', parent_ids: ['A'] },
  { id: 'p3', item_number: 'jbp00010', name: 'Bracket', parent_ids: ['T'] },
  { id: 'p4', item_number: 'mmc12345', name: 'Bolt', parent_ids: [] },
]

describe('filterItems', () => {
  it('returns the first items when the query is empty', () => {
    expect(filterItems(parts, '', 2).map(p => p.id)).toEqual(['A', 'p1'])
  })

  it('ranks item-number prefix matches before name matches', () => {
    const out = filterItems(parts, 'csp')
    expect(out.map(p => p.item_number)).toEqual(['csp0030', 'csp0031'])
  })

  it('matches on name, case-insensitively', () => {
    expect(filterItems(parts, 'GUSS').map(p => p.id)).toEqual(['p2'])
  })

  it('respects the limit', () => {
    expect(filterItems(parts, 'p', 2)).toHaveLength(2)
  })
})

describe('partsForAssembly', () => {
  it('returns everything when no assembly is chosen', () => {
    expect(partsForAssembly(parts, null)).toHaveLength(parts.length)
  })

  it('puts direct children first and excludes the assembly itself', () => {
    const out = partsForAssembly(parts, 'A').map(p => p.id)
    expect(out.slice(0, 2)).toEqual(['p1', 'p2'])
    expect(out).not.toContain('A')
    expect(out).toContain('p3')
  })
})

describe('defaultAssemblyForPart', () => {
  it('finds the parent weldment for a fab part', () => {
    expect(defaultAssemblyForPart(parts[1]!, asm)?.id).toBe('A')
  })

  it('returns null for a loose part', () => {
    expect(defaultAssemblyForPart(parts[4]!, asm)).toBeNull()
  })

  it('skips parents that are not known assemblies', () => {
    const p: ShopItem = { id: 'x', item_number: 'x', name: '', parent_ids: ['nope', 'T'] }
    expect(defaultAssemblyForPart(p, asm)?.id).toBe('T')
  })
})

describe('itemLabel', () => {
  it('formats number and name', () => {
    expect(itemLabel({ item_number: 'csp0030', name: 'Side plate' })).toBe('csp0030 — Side plate')
    expect(itemLabel({ item_number: 'csp0030', name: null })).toBe('csp0030')
    expect(itemLabel(null)).toBe('')
  })
})
