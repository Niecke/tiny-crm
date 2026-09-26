import type { components } from './schema'

// Short names for generated schemas that a screen names explicitly (a prop, a
// mutation body). Aliases only — the shapes come from the backend; never add
// fields here. Most code needs none: query results are typed by the call.
type Schemas = components['schemas']

export type OrganizationRead = Schemas['OrganizationRead']
export type OrganizationCreate = Schemas['OrganizationCreate']
export type BriefingRead = Schemas['BriefingRead']
export type BriefingTask = Schemas['BriefingTask']
export type BriefingInteraction = Schemas['BriefingInteraction']
export type CaptureRead = Schemas['CaptureRead']
export type CaptureStatus = Schemas['CaptureRead']['status']
export type CaptureConvert = Schemas['CaptureConvert']
