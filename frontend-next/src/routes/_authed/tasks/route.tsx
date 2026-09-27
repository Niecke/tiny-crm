import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'

// The list's search, the show-done switch and the page live in the URL,
// declared on the parent so the pages below can carry them back.
const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  done: z.boolean().optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/tasks')({
  validateSearch: searchSchema,
  component: Outlet,
})
