import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'

const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/documents')({
  validateSearch: searchSchema,
  component: Outlet,
})
