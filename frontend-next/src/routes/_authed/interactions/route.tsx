import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'
import { kindOptions } from '../../../interactions'

// Search, kind, and each panel's page, in the URL.
const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  kind: z
    .enum(kindOptions.map((o) => o.value) as [(typeof kindOptions)[number]['value'], ...(typeof kindOptions)[number]['value'][]])
    .optional()
    .catch(undefined),
  planned: z.number().int().min(2).optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/interactions')({
  validateSearch: searchSchema,
  component: Outlet,
})
