import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'

// The list's search lives in the URL and is declared here, on the parent, so
// every page below can carry it: back from a detail, the new form or the edit
// form lands on the same filtered list.
const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/organizations')({
  validateSearch: searchSchema,
  component: Outlet,
})
