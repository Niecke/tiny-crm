import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'

// Which list and what search, on the parent so the triage page can link back
// to the same view. "new" is the default and stays out of the URL.
const searchSchema = z.object({
  status: z.enum(['new', 'converted', 'dismissed']).optional().catch(undefined),
  q: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/inbox')({
  validateSearch: searchSchema,
  component: Outlet,
})
