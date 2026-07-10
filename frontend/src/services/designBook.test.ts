import { describe, it, expect } from 'vitest'
import { slugifyBookCode, isValidBookCode } from './designBook'

describe('book code helpers', () => {
  it('slugifies free text into a safe book code', () => {
    expect(slugifyBookCode('Standard Spa')).toBe('standard-spa')
    expect(slugifyBookCode('  Boiler  Model_2!! ')).toBe('boiler-model-2')
    expect(slugifyBookCode('spa-standard')).toBe('spa-standard')
    expect(slugifyBookCode('CSA00010 Book')).toBe('csa00010-book')
  })

  it('validates book codes', () => {
    expect(isValidBookCode('spa-standard')).toBe(true)
    expect(isValidBookCode('boiler2')).toBe(true)
    expect(isValidBookCode('a')).toBe(true)
    expect(isValidBookCode('Spa-Standard')).toBe(false) // uppercase
    expect(isValidBookCode('spa--standard')).toBe(false) // double hyphen
    expect(isValidBookCode('-spa')).toBe(false)
    expect(isValidBookCode('spa-')).toBe(false)
    expect(isValidBookCode('spa book')).toBe(false)
    expect(isValidBookCode('')).toBe(false)
  })

  it('slugify output always passes validation (or is empty)', () => {
    for (const input of ['Standard Spa!!', '  __  ', 'A B C', '天 spa 3']) {
      const slug = slugifyBookCode(input)
      if (slug) expect(isValidBookCode(slug)).toBe(true)
    }
  })
})
