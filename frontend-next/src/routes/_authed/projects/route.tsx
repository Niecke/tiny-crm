import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'

const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  // The archive instead of the list (#140).
  archived: z.boolean().optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/projects')({
  validateSearch: searchSchema,
  component: Outlet,
})
