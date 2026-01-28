import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { supabase } from '../services/supabase'
import type { Item, FileInfo, BOMTreeNode, BOMEntry } from '../types'

export const useItemsStore = defineStore('items', () => {
  const items = ref<Item[]>([])
  const currentItem = ref<Item | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Filters
  const searchQuery = ref('')
  const lifecycleFilter = ref<string | null>(null)
  const projectFilter = ref<string | null>(null)

  const filteredItems = computed(() => {
    return items.value // Filtering is done in the view
  })

  async function fetchItems(params?: {
    q?: string
    lifecycle_state?: string
    project_id?: string
    limit?: number
    offset?: number
  }) {
    loading.value = true
    error.value = null

    try {
      let query = supabase
        .from('items')
        .select(`
          *,
          projects(name)
        `)
        .order('item_number', { ascending: true })

      if (params?.lifecycle_state) {
        query = query.eq('lifecycle_state', params.lifecycle_state)
      }

      if (params?.project_id) {
        query = query.eq('project_id', params.project_id)
      }

      if (params?.q) {
        query = query.or(`item_number.ilike.%${params.q}%,name.ilike.%${params.q}%,description.ilike.%${params.q}%`)
      }

      if (params?.limit) {
        query = query.limit(params.limit)
      }

      if (params?.offset) {
        query = query.range(params.offset, params.offset + (params.limit || 100) - 1)
      }

      const { data, error: queryError } = await query

      if (queryError) throw queryError

      // Map project name from joined table
      items.value = (data || []).map(item => ({
        ...item,
        project_name: item.projects?.name || null
      }))
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch items'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function fetchItem(itemNumber: string) {
    loading.value = true
    error.value = null

    try {
      // Fetch item with project info
      const { data: itemData, error: itemError } = await supabase
        .from('items')
        .select(`
          *,
          projects(name)
        `)
        .eq('item_number', itemNumber)
        .single()

      if (itemError) throw itemError

      // Fetch files for this item
      const { data: filesData, error: filesError } = await supabase
        .from('files')
        .select('*')
        .eq('item_id', itemData.id)
        .order('file_type', { ascending: true })

      if (filesError) throw filesError

      currentItem.value = {
        ...itemData,
        project_name: itemData.projects?.name || null,
        files: filesData || []
      }
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch item'
      currentItem.value = null
    } finally {
      loading.value = false
    }
  }

  async function createItem(item: Partial<Item>) {
    loading.value = true
    error.value = null

    try {
      const { data, error: insertError } = await supabase
        .from('items')
        .insert({
          item_number: item.item_number,
          name: item.name,
          description: item.description,
          revision: item.revision || 'A',
          iteration: item.iteration || 1,
          lifecycle_state: item.lifecycle_state || 'Design',
          project_id: item.project_id,
          material: item.material,
          mass: item.mass,
          thickness: item.thickness,
          cut_length: item.cut_length,
          is_supplier_part: item.is_supplier_part || false,
          supplier_name: item.supplier_name,
          supplier_pn: item.supplier_pn,
          unit_price: item.unit_price
        })
        .select()
        .single()

      if (insertError) throw insertError

      items.value.unshift(data)
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to create item'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateItem(itemNumber: string, updates: Partial<Item>) {
    loading.value = true
    error.value = null

    try {
      const { data, error: updateError } = await supabase
        .from('items')
        .update(updates)
        .eq('item_number', itemNumber)
        .select()
        .single()

      if (updateError) throw updateError

      // Update in list
      const index = items.value.findIndex(i => i.item_number === itemNumber)
      if (index !== -1) {
        items.value[index] = { ...items.value[index], ...data }
      }

      // Update current if viewing
      if (currentItem.value?.item_number === itemNumber) {
        currentItem.value = { ...currentItem.value, ...data }
      }

      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to update item'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteItem(itemNumber: string) {
    loading.value = true
    error.value = null

    try {
      const { error: deleteError } = await supabase
        .from('items')
        .delete()
        .eq('item_number', itemNumber)

      if (deleteError) throw deleteError

      items.value = items.value.filter(i => i.item_number !== itemNumber)

      if (currentItem.value?.item_number === itemNumber) {
        currentItem.value = null
      }
    } catch (e: any) {
      error.value = e.message || 'Failed to delete item'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function getBOMTree(itemNumber: string): Promise<BOMTreeNode> {
    // First get the item
    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('*')
      .eq('item_number', itemNumber)
      .single()

    if (itemError) throw itemError

    // Then get BOM entries
    const { data: bomEntries, error: bomError } = await supabase
      .from('bom')
      .select(`
        *,
        child:items!bom_child_item_id_fkey(*)
      `)
      .eq('parent_item_id', item.id)

    if (bomError) throw bomError

    const children: BOMTreeNode[] = (bomEntries || []).map(entry => ({
      item: entry.child,
      quantity: entry.quantity,
      children: [] // Could recursively load children if needed
    }))

    return {
      item,
      quantity: 1,
      children
    }
  }

  async function getWhereUsed(itemNumber: string): Promise<{ item: Item; quantity: number }[]> {
    // First get the item ID
    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('id')
      .eq('item_number', itemNumber)
      .single()

    if (itemError) throw itemError

    // Get BOM entries where this item is a child
    const { data: bomEntries, error: bomError } = await supabase
      .from('bom')
      .select(`
        quantity,
        parent:items!bom_parent_item_id_fkey(*)
      `)
      .eq('child_item_id', item.id)

    if (bomError) throw bomError

    return (bomEntries || []).map(entry => ({
      item: entry.parent,
      quantity: entry.quantity
    }))
  }

  async function getItemHistory(itemNumber: string) {
    // First get the item ID
    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('id')
      .eq('item_number', itemNumber)
      .single()

    if (itemError) throw itemError

    const { data, error: historyError } = await supabase
      .from('lifecycle_history')
      .select('*')
      .eq('item_id', item.id)
      .order('changed_at', { ascending: false })

    if (historyError) throw historyError

    return data || []
  }

  return {
    items,
    currentItem,
    loading,
    error,
    searchQuery,
    lifecycleFilter,
    projectFilter,
    filteredItems,
    fetchItems,
    fetchItem,
    createItem,
    updateItem,
    deleteItem,
    getBOMTree,
    getWhereUsed,
    getItemHistory,
  }
})
