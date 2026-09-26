import { createFileRoute, Outlet } from '@tanstack/react-router'
import { z } from 'zod'
import { lifecycleOptions, relationOptions } from '../../../contacts'

// The list's search, filters and page live in the URL and are declared here,
// on the parent, so every page below can carry them: back from a detail, the
// new form or the edit form lands on the same filtered page.
const values = <T extends string>(options: { value: T }[]) => options.map((o) => o.value) as [T, ...T[]]

const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  status: z.enum(values(lifecycleOptions)).optional().catch(undefined),
  relation: z.enum(values(relationOptions)).optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/contacts')({
  validateSearch: searchSchema,
  component: Outlet,
})
