import type { components } from './schema'

// Short names for generated schemas that a screen names explicitly (a prop, a
// mutation body). Aliases only — the shapes come from the backend; never add
// fields here. Most code needs none: query results are typed by the call.
type Schemas = components['schemas']

export type OrganizationRead = Schemas['OrganizationRead']
export type OrganizationCreate = Schemas['OrganizationCreate']
