import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'
import { kindOptions } from '../../../watches'

const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  // Due now is the default and is left out of the URL.
  scope: z.enum(['active', 'all']).optional().catch(undefined),
  kind: z
    .enum(kindOptions.map((o) => o.value) as ['job_board', 'careers_page', 'tender_portal', 'other'])
    .optional()
    .catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/watches')({
  validateSearch: searchSchema,
  component: Outlet,
})
