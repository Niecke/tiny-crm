import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'
import { scopeOptions } from '../../../deals'

// View (board or list), scope, search and the list's page, in the URL.
const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  scope: z
    .string()
    .refine((v) => scopeOptions.some((o) => o.value === v))
    .optional()
    .catch(undefined),
  view: z.enum(['list']).optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/deals')({
  validateSearch: searchSchema,
  component: Outlet,
})
