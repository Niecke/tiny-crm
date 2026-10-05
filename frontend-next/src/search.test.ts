import { QueryClient } from '@tanstack/react-query'
import { describe, expect, test } from 'vitest'
import type { SearchHit } from './api/types'
import { hitLink, hitMeta, isSearchable, PAGE_SIZE, searchQuery } from './search'
import { http, server, testApi } from './test/server'

const hit = (fields: Partial<SearchHit> = {}): SearchHit => ({
  id: 'id-1',
  type: 'contacts',
  title: 'Jane Doe',
  subtitle: null,
  date: null,
  match: null,
  ...fields,
})

describe('hitLink', () => {
  test.each([
    ['contacts', '/contacts/$contactId', { contactId: 'id-1' }],
    ['organizations', '/organizations/$organizationId', { organizationId: 'id-1' }],
    ['deals', '/deals/$dealId', { dealId: 'id-1' }],
    ['tasks', '/tasks/$taskId', { taskId: 'id-1' }],
    ['interactions', '/interactions/$interactionId', { interactionId: 'id-1' }],
    ['projects', '/projects/$projectId', { projectId: 'id-1' }],
    ['documents', '/documents/$documentId', { documentId: 'id-1' }],
    ['watches', '/watches/$watchId', { watchId: 'id-1' }],
    // A capture opens where it is worked: the inbox's triage page.
    ['captures', '/inbox/$captureId', { captureId: 'id-1' }],
  ] as const)('%s opens %s', (type, to, params) => {
    expect(hitLink(hit({ type }))).toEqual({ to, params })
  })
})

describe('hitMeta', () => {
  test('says where a hit matched when its title does not show it', () => {
    expect(
      hitMeta(hit({ subtitle: 'CTO · ACME', match: { field: 'Phone', excerpt: '+43 664 123 45 67' } })),
    ).toBe('CTO · ACME · Phone: +43 664 123 45 67')
  })

  test('is empty when there is nothing to add', () => {
    expect(hitMeta(hit())).toBe('')
  })

  // The suite runs in America/New_York (vite.config.ts).
  test('shows a moment as the day it falls on here, not in UTC', () => {
    // 23:59 on 4 Oct in New York is 03:59 on the 5th in UTC.
    expect(hitMeta(hit({ type: 'tasks', date: { label: 'Due', at: '2026-10-05T03:59:00Z' } }))).toBe(
      'Due Oct 4, 2026',
    )
    expect(hitMeta(hit({ type: 'interactions', subtitle: 'Call', date: { at: '2026-10-05T03:59:00Z' } }))).toBe(
      'Call · Oct 4, 2026',
    )
  })

  test('shows a calendar day as that day, wherever it is read', () => {
    expect(hitMeta(hit({ type: 'projects', date: { label: 'Since', day: '2026-08-01' } }))).toBe('Since Aug 1, 2026')
  })
})

describe('isSearchable', () => {
  test.each([
    ['', false],
    ['a', false],
    [' a ', false],
    ['ab', true],
    [' ab ', true],
  ])('%j → %s', (q, expected) => {
    expect(isSearchable(q)).toBe(expected)
  })
})

describe('searchQuery', () => {
  test('is not sent for an empty query, or one character', () => {
    expect(searchQuery(testApi(), '  ').enabled).toBe(false)
    expect(searchQuery(testApi(), 'a').enabled).toBe(false)
    expect(searchQuery(testApi(), 'ab').enabled).toBe(true)
  })

  test('pages one type by skip', async () => {
    let seen: URLSearchParams | undefined
    server.use(
      http.get('/search/', ({ request, response }) => {
        seen = new URL(request.url).searchParams
        return response(200).json({ q: 'acme', groups: [] })
      }),
    )
    await new QueryClient().fetchQuery(searchQuery(testApi(), 'acme', { type: 'contacts', page: 3, limit: PAGE_SIZE }))
    expect(Object.fromEntries(seen!)).toEqual({ q: 'acme', type: 'contacts', limit: '25', skip: '50' })
  })

  test('asks for every type without paging', async () => {
    let seen: URLSearchParams | undefined
    server.use(
      http.get('/search/', ({ request, response }) => {
        seen = new URL(request.url).searchParams
        return response(200).json({ q: 'acme', groups: [] })
      }),
    )
    await new QueryClient().fetchQuery(searchQuery(testApi(), 'acme'))
    expect(Object.fromEntries(seen!)).toEqual({ q: 'acme', limit: '5' })
  })
})
