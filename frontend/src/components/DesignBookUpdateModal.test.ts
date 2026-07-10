// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DesignBookUpdateModal from './DesignBookUpdateModal.vue'
import type { CheckResult } from '../services/designBook'

function makeDiff(overrides: Partial<CheckResult> = {}): CheckResult {
  return {
    book_rev: 1,
    next_book_rev: 2,
    would_issue_notice: true,
    added: [
      { section_code: 'II-CSA00099', title: 'NEW SUB', old_rev: null, new_rev: 'A', last_rev: null, reasons: ['NEW'], page_count: null },
    ],
    changed: [
      { section_code: 'I-SAW-1', title: 'SAW', old_rev: 'A', new_rev: 'B', last_rev: null, reasons: ['MOVED D1->D2'], page_count: 5 },
      { section_code: '00-SPINE', title: 'MASTER CHECKLIST + TOC', old_rev: 'A', new_rev: 'B', last_rev: null, reasons: ['TOC/CHECKLIST UPDATED'], page_count: 5 },
    ],
    retired: [
      { section_code: 'I-HP-1', title: 'HOLE PUNCH', old_rev: null, new_rev: null, last_rev: 'A', reasons: ['RETIRED'], page_count: null },
    ],
    unchanged: ['II-REF', 'III-00'],
    warnings: [],
    ...overrides,
  }
}

describe('DesignBookUpdateModal', () => {
  it('renders the diff with action chips and rev arrows', () => {
    const w = mount(DesignBookUpdateModal, {
      props: { diff: makeDiff(), committing: false, firstGen: false },
    })
    const text = w.text()
    expect(text).toContain('REPLACE')
    expect(text).toContain('INSERT')
    expect(text).toContain('REMOVE')
    expect(text).toContain('I-SAW-1')
    expect(text).toContain('MOVED D1->D2')
    expect(text).toContain('2 sections unchanged')
    expect(text).toContain('CHANGE-NOTICE-rev002')
    expect(w.find('button.primary-btn').text()).toContain('Commit Update (4 sections)')
    expect(w.find('button.primary-btn').attributes('disabled')).toBeUndefined()
  })

  it('gates commit behind per-hole missing-print acknowledgment', async () => {
    const w = mount(DesignBookUpdateModal, {
      props: {
        diff: makeDiff({
          warnings: [
            { type: 'missing_print', section_code: 'I-SAW-1', item_number: 'csa000850' },
            { type: 'missing_print', section_code: 'II-CSA00085', item_number: 'csa00085' },
          ],
        }),
        committing: false,
        firstGen: false,
      },
    })
    const commit = () => w.find('button.primary-btn')
    expect(commit().attributes('disabled')).toBeDefined() // blocked until acked
    const boxes = w.findAll('input[type="checkbox"]')
    expect(boxes).toHaveLength(2)
    await boxes[0]!.setValue(true)
    expect(commit().attributes('disabled')).toBeDefined() // one hole still open
    await boxes[1]!.setValue(true)
    expect(commit().attributes('disabled')).toBeUndefined()
    await commit().trigger('click')
    expect(w.emitted('commit')).toHaveLength(1)
  })

  it('shows the no-changes state without a commit button', () => {
    const w = mount(DesignBookUpdateModal, {
      props: {
        diff: makeDiff({ added: [], changed: [], retired: [], next_book_rev: 1, would_issue_notice: false }),
        committing: false,
        firstGen: false,
      },
    })
    expect(w.text()).toContain('No changes')
    expect(w.find('button.primary-btn').exists()).toBe(false)
  })

  it('labels first generation appropriately', () => {
    const w = mount(DesignBookUpdateModal, {
      props: { diff: makeDiff({ book_rev: 0, next_book_rev: 1 }), committing: false, firstGen: true },
    })
    expect(w.text()).toContain('Generate Master Design Book')
    expect(w.text()).toContain('first generation')
    expect(w.find('button.primary-btn').text()).toContain('Generate Book')
  })

  it('emits close on cancel and overlay click', async () => {
    const w = mount(DesignBookUpdateModal, {
      props: { diff: makeDiff(), committing: false, firstGen: false },
    })
    await w.find('button.secondary-btn').trigger('click')
    await w.find('.modal-overlay').trigger('click')
    expect(w.emitted('close')?.length).toBe(2)
  })
})
